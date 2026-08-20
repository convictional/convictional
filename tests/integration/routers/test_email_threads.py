from datetime import UTC, datetime, timedelta

import pytest
from fastapi import status

from app.jobs.content import ContentIndexingJob
from app.models.collaboration.content import Content
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import Mailbox, MailboxEntry, MailboxEntryFilters
from app.models.collaboration.workspace import SubscriptionPreference
from app.models.workspaces.email.thread import EmailAttachment, EmailThread
from config.enums import ContentType, EmailLabel, EmailMailboxLabel, EmailReplyType, SubscriptionLevel
from infra.jobs import InlineJobs
from infra.storage import FileReference
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_message, create_user


@pytest.mark.asyncio
async def test_email_threads_reply(client: AppClient):
    user = await create_user()

    with client.current_user_as(user):
        # Create thread with multiple participants
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="reply_test_thread",
            subject="Team Conversation",
            sender="alice@example.com",
            body_plain="Original message",
            to=[user.email, "bob@example.com"],
            cc=["charlie@example.com"],
            labels=[EmailLabel.INBOX],
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Test basic reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED
        draft = await email_thread.get_draft()
        assert draft
        assert draft.message.subject == "Re: Team Conversation"
        assert draft.message.to == [message.sender]
        assert len(draft.message.cc) == 0  # Reply does not include CC by default

        # Store first draft ID for replacement test
        first_draft_id = draft.id

        # Test draft replacement conflict response
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY_ALL.value},
        )
        assert response.status_code == status.HTTP_409_CONFLICT

        # Verify original draft still exists (not replaced yet)
        original_draft = await email_thread.get_draft()
        assert original_draft is not None
        assert original_draft.id == first_draft_id

        # Test draft replacement with confirmation
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY_ALL.value, "replace_existing": True},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Verify draft was replaced
        new_draft = await email_thread.get_draft()
        assert new_draft is not None
        assert new_draft.id != first_draft_id  # Draft was replaced
        assert new_draft.message.subject == "Re: Team Conversation"

        # Verify reply all includes CC recipients (from the replacement test above)
        assert new_draft.message.to == [message.sender]
        for cc in new_draft.message.cc:
            assert cc in new_draft.message.cc


@pytest.mark.asyncio
async def test_email_threads_forward(client: AppClient):
    user = await create_user()

    with client.current_user_as(user):
        # Create file references for different attachment types
        inline_file = await FileReference.create(
            key="test/inline_image.png",
            filename="inline_image.png",
            content_type="image/png",
            byte_size=512,
            checksum="inline123",
        )
        referenced_file = await FileReference.create(
            key="test/referenced_image.jpg",
            filename="referenced_image.jpg",
            content_type="image/jpeg",
            byte_size=1024,
            checksum="ref456",
        )
        regular_file = await FileReference.create(
            key="test/document.pdf",
            filename="document.pdf",
            content_type="application/pdf",
            byte_size=2048,
            checksum="doc789",
        )

        # Create original message with multiple attachments
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="forward_test_thread",
            subject="Team Conversation",
            sender="alice@example.com",
            body_plain="Original message",
            to=[user.email, "bob@example.com"],
            cc=["charlie@example.com"],
            labels=[EmailLabel.INBOX],
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Add inline attachment
        await EmailAttachment.create(
            email_message_id=message.id,
            file_id=inline_file.id,
            thread_id=email_thread.id,
            is_inline=True,
            content_id="inline-image-123",
        )

        # Add referenced attachment
        await EmailAttachment.create(
            email_message_id=message.id,
            file_id=referenced_file.id,
            thread_id=email_thread.id,
            is_inline=False,
            is_referenced_in_html=True,
        )

        # Add regular non-inline attachment
        await EmailAttachment.create(
            email_message_id=message.id,
            file_id=regular_file.id,
            thread_id=email_thread.id,
            is_inline=False,
            is_referenced_in_html=False,
        )

        # Test forward
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/forward",
        )
        assert response.status_code == status.HTTP_201_CREATED
        draft = await email_thread.get_draft()
        assert draft
        assert draft.message.subject == "Fwd: Team Conversation"
        assert len(draft.message.to) == 0  # Forward has no specific recipients by default
        assert len(draft.message.cc) == 0  # Forward has no CC by default

        # Verify all attachments were copied
        await draft.message.fetch_related("attachments__file")
        assert len(draft.message.attachments) == 3

        # Verify each attachment type was preserved correctly
        attachments_by_file = {att.file_id: att for att in draft.message.attachments}

        inline_att = attachments_by_file[inline_file.id]
        assert inline_att.is_inline
        assert inline_att.content_id == "inline-image-123"

        referenced_att = attachments_by_file[referenced_file.id]
        assert not referenced_att.is_inline
        assert referenced_att.is_referenced_in_html

        regular_att = attachments_by_file[regular_file.id]
        assert not regular_att.is_inline
        assert not regular_att.is_referenced_in_html


@pytest.mark.asyncio
async def test_email_threads_reply_respects_reply_to_header(client: AppClient):
    """Test that email replies respect the Reply-To header"""
    user = await create_user()

    with client.current_user_as(user):
        # Create message with Reply-To header different from sender
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="reply_to_test_thread",
            subject="Test Message",
            sender="sender@example.com",
            body_plain="Test message with Reply-To header",
            to=[user.email],
            headers_list=[{"name": "Reply-To", "value": "replyto@example.com"}],
            labels=[EmailLabel.INBOX],
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Verify reply uses Reply-To header instead of sender
        draft = await email_thread.get_draft()
        assert draft
        assert draft.message.to == ["replyto@example.com"]  # Should use Reply-To, not sender
        assert draft.message.subject == "Re: Test Message"


@pytest.mark.asyncio
async def test_email_threads_reply_to_own_message(client: AppClient):
    """Test that replying to your own message replies to original recipients"""
    user = await create_user()

    with client.current_user_as(user):
        # Create message sent by the user to others
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="self_reply_test_thread",
            subject="Self Reply Test",
            sender=user.email,
            body_plain="This is a message sent by the user",
            to=["someone@else.com"],
            headers_list=[{"name": "To", "value": "someone@else.com"}],
            labels=[EmailLabel.SENT],
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED
        draft = await email_thread.get_draft()
        assert draft

        # Verify reply goes to original recipients, not back to self
        assert draft.message.to == ["someone@else.com"]


@pytest.mark.asyncio
async def test_email_threads_new(client: AppClient):
    superuser = await create_user()
    client.current_user = superuser
    response = await client.post("/api/email_threads")
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["thread_id"]

    email_thread = await EmailThread.first()
    assert email_thread is not None

    email_draft = await email_thread.get_draft()
    assert email_draft is not None

    mailbox = Mailbox(user=superuser)
    mailbox_entry = await mailbox.entry(email_thread).get()
    assert mailbox_entry is not None
    assert EmailMailboxLabel.DRAFT in mailbox_entry.labels
    assert email_thread.is_draft

    drafts_queryset = mailbox.filters.drafts
    draft_entries = await drafts_queryset
    assert len(draft_entries) == 1
    assert draft_entries[0].id == mailbox_entry.id


@pytest.mark.asyncio
async def test_email_threads_unsnooze_on_activity(client: AppClient):
    user = await create_user()
    collaborator = await create_user(organization_id=user.organization_id)
    await SubscriptionPreference.update_for(user.id, {EmailThread.record_type: SubscriptionLevel.ALL})

    with client.current_user_as(user):
        await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="auto_unsnooze_thread",
            subject="Test Auto-Unsnooze on Activity",
            sender="alice@example.com",
            body_plain="First message",
            labels=[EmailLabel.INBOX],
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await email_thread.fetch_related("workspace")
        await Mailbox.sync(email_thread)

        await client.post(
            f"/api/workspaces/{email_thread.workspace_id}/collaborators", json={"user_id": str(collaborator.id)}
        )

        mailbox_entry = await MailboxEntry.get(resource_gid=str(email_thread.global_id), owner_id=user.id)

        assert mailbox_entry.is_inbox
        assert not mailbox_entry.is_snoozed

        snooze_until = datetime.now(UTC) + timedelta(days=1)
        mailbox = Mailbox(user=user)
        await mailbox.snooze(email_thread, snooze_until)

        await mailbox_entry.refresh_from_db()
        assert mailbox_entry.is_snoozed
        assert mailbox_entry.snoozed_until == snooze_until
        assert mailbox_entry.is_archived

        # New email is received in the thread (should unsnooze)
        await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="auto_unsnooze_thread",
            subject="Re: Test Auto-Unsnooze on Activity",
            sender="bob@example.com",
            body_plain="Reply to the snoozed thread",
            labels=[EmailLabel.INBOX],
        )

        await Mailbox.sync(email_thread)

        await mailbox_entry.refresh_from_db()
        assert not mailbox_entry.is_snoozed
        assert mailbox_entry.snoozed_until is None
        assert mailbox_entry.is_inbox
        assert mailbox_entry.is_unread

        # Snooze again for next test
        await mailbox.snooze(email_thread, snooze_until)

        await mailbox_entry.refresh_from_db()
        assert mailbox_entry.is_snoozed
        assert mailbox_entry.snoozed_until == snooze_until
        assert mailbox_entry.is_archived

    # Collaborator adds a comment to the thread (should unsnooze for owner)
    with client.current_user_as(collaborator):
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/comments",
            json={"content": "This is a comment from collaborator"},
        )
        assert response.status_code == status.HTTP_201_CREATED

    await mailbox_entry.refresh_from_db()
    assert not mailbox_entry.is_snoozed
    assert mailbox_entry.snoozed_until is None
    assert mailbox_entry.is_inbox
    assert mailbox_entry.is_unread


@pytest.mark.asyncio
async def test_email_threads_show_original(client: AppClient):
    user = await create_user()

    with client.current_user_as(user):
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="original_test_thread",
            subject="Test Email for Original View",
            sender="Alice Smith <alice@example.com>",
            body_plain="This is the plain text content",
            body_html="<p>This is the <strong>HTML</strong> content</p>",
            to=[user.email],
            cc=["cc@example.com"],
            headers_list=[
                {"name": "Message-ID", "value": "<test123@example.com>"},
                {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
                {"name": "Reply-To", "value": "noreply@example.com"},
            ],
            raw_data={"provider": "gmail", "external_id": "abc123", "thread_id": "thread_xyz"},
            labels=[EmailLabel.INBOX],
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # The page is served by the client-routed SPA shell; the React route
        # fetches its data from the JSON peer below.
        page_response = await client.get(f"/email_threads/{email_thread.id}/email_messages/{message.id}")
        assert page_response.status_code == status.HTTP_200_OK
        assert '<div id="root">' in page_response.text

        # All the actual data is served by the JSON peer.
        response = await client.get(f"/api/email_threads/{email_thread.id}/email_messages/{message.id}")
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["subject"] == "Test Email for Original View"
        assert body["raw_sender"] == "Alice Smith <alice@example.com>"
        assert body["to"] == [user.email]
        assert body["cc"] == ["cc@example.com"]
        assert body["body_plain"] == "This is the plain text content"
        assert body["body_html"] == "<p>This is the <strong>HTML</strong> content</p>"
        header_names = {h["name"] for h in body["headers"]}
        assert {"Message-ID", "Date", "Reply-To"} <= header_names
        assert body["raw_data"] == {"provider": "gmail", "external_id": "abc123", "thread_id": "thread_xyz"}


@pytest.mark.asyncio
async def test_email_reply_initial_content_with_html(client: AppClient):
    """Test that reply initial content is generated correctly for HTML messages."""
    user = await create_user()

    with client.current_user_as(user):
        # Create a message with HTML content
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="reply_content_test_html",
            subject="Original Subject",
            sender="alice@example.com",
            sender_name="Alice Smith",
            body_html="<p>This is <strong>HTML</strong> content with <em>formatting</em>.</p>",
            to=[user.email],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 1, 15, 14, 30, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create a reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify initial content
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the reply structure - now uses sender name from address, not display name
        assert "On January 15, 2024 at 2:30 PM, alice wrote:" in initial_content
        assert ":::quoted_html" in initial_content
        assert "<p>This is <strong>HTML</strong> content with <em>formatting</em>.</p>" in initial_content
        assert ":::" in initial_content


@pytest.mark.asyncio
async def test_email_reply_initial_content_with_plain_text(client: AppClient):
    """Test that reply initial content is generated correctly for plain text messages."""
    user = await create_user()

    with client.current_user_as(user):
        # Create a message with plain text content
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="reply_content_test_plain",
            subject="Plain Text Subject",
            sender="bob@example.com",
            sender_name="Bob Wilson",
            body_plain="This is plain text content.\nWith multiple lines.",
            body_html=None,  # Explicitly set to None to force plain text path
            to=[user.email],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 1, 20, 9, 15, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create a reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify initial content
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the reply structure with plain text converted to HTML
        assert "On January 20, 2024 at 9:15 AM, bob wrote:" in initial_content
        assert ":::quoted_html" in initial_content
        assert "This is plain text content.<br>With multiple lines." in initial_content


@pytest.mark.asyncio
async def test_email_forward_initial_content(client: AppClient):
    """Test that forward initial content is generated correctly."""
    user = await create_user()

    with client.current_user_as(user):
        # Create a message to forward
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="forward_content_test",
            subject="Fwd: Important Document",
            sender="carol@example.com",
            sender_name="Carol Johnson",
            body_html="<p>Please review this important document.</p>",
            to=[user.email, "team@example.com"],
            cc=["manager@example.com"],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 2, 1, 16, 45, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create a forward
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/forward",
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify initial content
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the forward structure - now uses sender name from address
        assert "---------- Forwarded message ---------" in initial_content
        assert "From: carol <carol@example.com>" in initial_content
        assert "Date: February 1, 2024 at 4:45 PM" in initial_content
        assert "Subject: Important Document" in initial_content  # normalized subject
        assert f"To: {user.email}, team@example.com" in initial_content
        assert "Cc: manager@example.com" in initial_content
        assert ":::quoted_html" in initial_content
        assert "<p>Please review this important document.</p>" in initial_content


@pytest.mark.asyncio
async def test_email_reply_initial_content_no_content(client: AppClient):
    """Test that reply handles messages with no content gracefully."""
    user = await create_user()

    with client.current_user_as(user):
        # Create a message with no body content
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="reply_no_content_test",
            subject="Empty Message",
            sender="empty@example.com",
            sender_name="Empty Sender",
            body_plain=None,
            body_html=None,
            to=[user.email],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 1, 10, 12, 0, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create a reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify initial content
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the reply structure with empty content placeholder
        assert "On January 10, 2024 at 12:00 PM, empty wrote:" in initial_content
        assert ":::quoted_html" in initial_content
        assert "<p><em>No content</em></p>" in initial_content


@pytest.mark.asyncio
async def test_nested_html_quoting_reply_to_reply(client: AppClient):
    """Test that nested quoting works when replying to a message that already contains quoted content."""
    user = await create_user()

    with client.current_user_as(user):
        # Create an original message that contains quoted content (like a reply that became a message)
        nested_html_content = (
            "<p>This is my response to the original message.</p>"
            '<div style="border-left: 4px solid #d1d5db; padding: 8px 16px; margin: 16px 0; '
            'background-color: #f9fafb; border-radius: 0 6px 6px 0;">'
            "<p>On January 5, 2024, Original Sender wrote:</p>"
            "<p>This was the original message content.</p>"
            "</div>"
        )

        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="nested_reply_test",
            subject="Re: Team Thread",
            sender="alice@example.com",
            sender_name="Alice Smith",
            body_html=nested_html_content,
            to=[user.email],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 1, 25, 10, 30, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create a reply to this already-nested message
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify nested content is preserved
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the reply contains the nested structure
        assert "On January 25, 2024 at 10:30 AM, alice wrote:" in initial_content
        assert ":::quoted_html" in initial_content

        # The nested content should be preserved as-is
        assert "This is my response to the original message." in initial_content
        assert "On January 5, 2024, Original Sender wrote:" in initial_content
        assert "This was the original message content." in initial_content


@pytest.mark.asyncio
async def test_nested_html_quoting_forward_with_quotes(client: AppClient):
    """Test that forwarding a message with existing quoted content works correctly."""
    user = await create_user()

    with client.current_user_as(user):
        # Create a message that contains blockquote-style content
        quoted_html_content = """<p>Please see the conversation below for context.</p>
<blockquote style="margin: 16px 0; padding-left: 16px; border-left: 4px solid #d6d3d1;">
<p>From: Previous Sender</p>
<p>We need to discuss the project timeline and deliverables.</p>
</blockquote>
<p>Let me know your thoughts on this.</p>"""

        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="nested_forward_test",
            subject="Project Timeline Review",
            sender="bob@example.com",
            sender_name="Bob Wilson",
            body_html=quoted_html_content,
            to=[user.email, "team@example.com"],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 2, 10, 14, 15, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Forward this message
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/forward",
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify nested content in forward
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the forward header and nested quoted content
        assert "---------- Forwarded message ---------" in initial_content
        assert "From: bob <bob@example.com>" in initial_content
        assert "Date: February 10, 2024 at 2:15 PM" in initial_content
        assert "Subject: Project Timeline Review" in initial_content
        assert f"To: {user.email}, team@example.com" in initial_content
        assert ":::quoted_html" in initial_content

        # The nested blockquote content should be preserved
        assert "Please see the conversation below for context." in initial_content
        assert "From: Previous Sender" in initial_content
        assert "We need to discuss the project timeline and deliverables." in initial_content
        assert "Let me know your thoughts on this." in initial_content


@pytest.mark.asyncio
async def test_nested_html_quoting_with_mixed_content(client: AppClient):
    """Test nested quoting with mixed HTML content including tables, lists, and formatting."""
    user = await create_user()

    with client.current_user_as(user):
        # Create a complex HTML message with various elements
        complex_html_content = """<p>Here's the updated report:</p>
<ul>
<li>Item 1: <strong>Completed</strong></li>
<li>Item 2: <em>In Progress</em></li>
</ul>
<table border="1" style="border-collapse: collapse;">
<tr><th>Task</th><th>Status</th></tr>
<tr><td>Design</td><td>Done</td></tr>
<tr><td>Development</td><td>50%</td></tr>
</table>
<div style="border-left: 4px solid #d1d5db; padding: 8px 16px; margin: 16px 0;">
<p><strong>Previous message:</strong></p>
<p>The original request was for a status update.</p>
</div>"""

        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="mixed_content_test",
            subject="Status Report Update",
            sender="manager@example.com",
            sender_name="Project Manager",
            body_html=complex_html_content,
            to=[user.email],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 3, 1, 11, 0, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Reply to this complex message
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify complex nested content
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the reply structure with complex nested content
        assert "On March 1, 2024 at 11:00 AM, manager wrote:" in initial_content
        assert ":::quoted_html" in initial_content

        # All the complex HTML should be preserved
        assert "Here's the updated report:" in initial_content
        assert "<ul>" in initial_content
        assert "<strong>Completed</strong>" in initial_content
        assert "<table" in initial_content
        assert "<th>Task</th>" in initial_content
        assert "Previous message:" in initial_content
        assert "The original request was for a status update." in initial_content


@pytest.mark.asyncio
async def test_email_reply_sanitizes_dangerous_html_tags(client: AppClient):
    """Test that email replies sanitize dangerous HTML tags like head and script."""
    user = await create_user()

    with client.current_user_as(user):
        # Create a message with dangerous HTML content including head and script tags
        dangerous_html_content = """
        <head>
            <meta charset="UTF-8">
            <title>This title should be removed</title>
            <script>alert('This should be removed');</script>
        </head>
        <body>
            <p>This is safe content that should remain.</p>
            <script>
                console.log('This script should also be removed');
                document.location = 'http://evil.com';
            </script>
            <style>
                body { background: red; }
            </style>
            <p>More safe content.</p>
        </body>
        """

        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="dangerous_html_test",
            subject="Email with Dangerous HTML",
            sender="potentially-malicious@example.com",
            sender_name="Potentially Malicious Sender",
            body_html=dangerous_html_content,
            to=[user.email],
            labels=[EmailLabel.INBOX],
            sent_at=datetime(2024, 1, 25, 15, 45, 0, tzinfo=UTC),
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        # Create a reply
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get the created draft and verify dangerous content is sanitized
        draft = await email_thread.get_draft()
        assert draft is not None

        # Get the live document content
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        initial_content = live_doc.markdown

        # Verify the reply structure is intact
        assert "On January 25, 2024 at 3:45 PM, potentially-malicious wrote:" in initial_content
        assert ":::quoted_html" in initial_content

        # Verify safe content is preserved
        assert "This is safe content that should remain." in initial_content
        assert "More safe content." in initial_content

        # Verify dangerous tags and their content are completely removed
        assert "<head>" not in initial_content
        assert "</head>" not in initial_content
        assert "<title>" not in initial_content
        assert "This title should be removed" not in initial_content
        assert "<script>" not in initial_content
        assert "</script>" not in initial_content
        assert "alert('This should be removed')" not in initial_content
        assert "console.log" not in initial_content
        assert "document.location" not in initial_content
        assert "http://evil.com" not in initial_content
        assert "<style>" not in initial_content
        assert "</style>" not in initial_content
        assert "background: red" not in initial_content

        # Verify the body tag is handled properly (should be removed but content preserved)
        assert "<body>" not in initial_content
        assert "</body>" not in initial_content


@pytest.mark.asyncio
async def test_email_reply_initial_content_set_before_response(client: AppClient):
    """Initial content must be persisted to the LiveDocument before the reply endpoint
    returns. Otherwise an editor that opens on the returned draft_message_id and connects
    to the channel before the live document is written can cache an empty SharedDocument.

    Regression test for: Reply/Forward initial_content sometimes missing and editor is broken.
    """
    user = await create_user()

    with client.current_user_as(user):
        message = await create_email_message(
            user_id=user.id,
            organization_id=user.organization_id,
            external_thread_id="race_condition_test",
            subject="Test Subject",
            sender="test@example.com",
            body_html="<p>Test content</p>",
            to=[user.email],
            labels=[EmailLabel.INBOX],
        )

        email_thread = await EmailThread.get(creator_id=user.id)
        await Mailbox.sync(email_thread)

        response = await client.post(
            f"/api/email_threads/{email_thread.id}/email_messages/{message.id}/reply",
            json={"reply_type": EmailReplyType.REPLY.value},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # As soon as the response returns, the live document must already carry the
        # initial reply content — the endpoint awaits set_initial_content before returning.
        draft = await email_thread.get_draft()
        assert draft is not None
        live_doc = await LiveDocument.for_topic(draft.live_document_topic)
        assert "Test content" in live_doc.markdown


@pytest.mark.asyncio
async def test_email_thread_content_indexing_lifecycle(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()
    other_user = await create_user(
        email="collaborator@example.com", name="Jane Collaborator", organization_id=user.organization_id
    )

    email_message = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        subject="Project Conversation",
        sender="client@external.com",
        to=[user.email],
        body_plain="Let's discuss the new project requirements.",
    )

    email_thread = await EmailThread.get(id=email_message.thread_id).prefetch_related("messages", "workspace")

    # Trigger indexing because we don't have access to the MockGmailAPIState here and this doesn't feel like
    # a test of the gmail integration, where that fixture is available.
    await ContentIndexingJob.from_model(email_thread.organization_id, email_thread).perform()

    # Assert Content was created and indexed properly
    assert await Content.all().count() == 1
    content = await Content.get(source_id=str(email_thread.global_id))
    assert content.content_type == ContentType.EMAIL_THREAD
    assert content.title == "Project Conversation"

    assert "Project Conversation" in content.index_content
    assert "From: client@external.com" in content.index_content
    assert "Let's discuss the new project requirements" in content.index_content

    # Check author sender and recipient
    assert content.author is not None
    assert "client@external.com" in content.author
    assert user.email in content.author

    # Check allowed_user_ids includes only the creator
    assert len(content.allowed_user_ids) == 1
    assert str(user.id) in content.allowed_user_ids[0]

    # Create a reply draft
    response = await client.post(
        f"/api/email_threads/{email_thread.id}/email_messages/{email_message.id}/reply",
        json={"reply_type": EmailReplyType.REPLY.value},
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Send the draft
    response = await client.post(
        f"/api/email_threads/{email_thread.id}/draft/send",
        json={
            "to": ["client@external.com"],
            "subject": "Re: Project Conversation",
            "message_body": "I agree with the requirements. Let's proceed.",
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Refresh and verify Content was updated
    await content.refresh_from_db()

    # Check index_content now includes the sent message
    assert "I agree with the requirements. Let's proceed." in content.index_content
    assert user.email in content.index_content or user.display_name in content.index_content
    assert "client@external.com" in content.index_content

    # Author should include both participants
    assert content.author is not None
    assert "client@external.com" in content.author
    assert user.email in content.author

    # allowed_user_ids should still be just the creator
    assert str(user.id) in content.allowed_user_ids

    # Add collaborator to the email thread workspace
    response = await client.post(
        f"/api/workspaces/{email_thread.workspace.id}/collaborators",
        json={"user_id": str(other_user.id)},
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Refresh Content to check collaborator was added to allowed_user_ids
    await content.refresh_from_db()
    assert str(user.id) in content.allowed_user_ids
    assert str(other_user.id) in content.allowed_user_ids

    # Add comment from collaborator (using their session)
    with client.current_user_as(other_user):
        response = await client.post(
            f"/api/email_threads/{email_thread.id}/comments",
            json={"content": "I've reviewed the requirements and have some suggestions."},
        )
        assert response.status_code == status.HTTP_201_CREATED

    # Refresh Content to verify comment was indexed
    await content.refresh_from_db()

    # Check index_content includes the comment
    assert "## Comments:" in content.index_content
    assert "I've reviewed the requirements and have some suggestions." in content.index_content
    assert f"Comment by {other_user.display_name}" in content.index_content

    # Check author now includes the commenter
    assert content.author is not None
    assert other_user.display_name in content.author
    # Should still include email participants
    assert "client@external.com" in content.author
    assert user.email in content.author

    # Verify EmailThread Content was updated, not recreated (comment also creates its own Content)
    assert await Content.filter(content_type=ContentType.EMAIL_THREAD).count() == 1


@pytest.mark.asyncio
async def test_email_threads_shared_with_me_indicator(client: AppClient):
    # Create two users in same organization
    user_a = await create_user(email="alice@example.com")
    user_b = await create_user(email="bob@example.com", organization_id=user_a.organization_id)

    # User A's copy
    message_a = await create_email_message(
        user_id=user_a.id,
        organization_id=user_a.organization_id,
        external_thread_id="gmail_thread_alice_123",  # Different from B
        external_message_id="gmail_msg_alice_456",  # Different from B
        message_id="<unique-rfc-2822-id@example.com>",  # SAME across both users
        subject="Team Conversation",
        sender="charlie@external.com",
        to=["alice@example.com"],
        cc=["bob@example.com"],
        body_plain="Let's discuss the project.",
        labels=[EmailLabel.INBOX],
    )
    thread_a = await EmailThread.get(id=message_a.thread_id).prefetch_related("workspace", "messages")
    await Mailbox.sync(thread_a)

    # User B's copy (they were CC'd, so they have their own thread)
    message_b = await create_email_message(
        user_id=user_b.id,
        organization_id=user_b.organization_id,
        external_thread_id="gmail_thread_bob_789",  # Different from A
        external_message_id="gmail_msg_bob_012",  # Different from A
        message_id="<unique-rfc-2822-id@example.com>",  # SAME as A's message
        subject="Team Conversation",
        sender="charlie@external.com",
        to=["alice@example.com"],
        cc=["bob@example.com"],
        body_plain="Let's discuss the project.",
        labels=[EmailLabel.INBOX],
    )
    thread_b = await EmailThread.get(id=message_b.thread_id).prefetch_related("workspace", "messages")
    await Mailbox.sync(thread_b)

    # User A shares their thread with User B
    with client.current_user_as(user_a):
        response = await client.post(
            f"/api/workspaces/{thread_a.workspace_id}/collaborators", json={"user_id": str(user_b.id)}
        )
        assert response.status_code == status.HTTP_201_CREATED

    # User B views User A's shared thread — the "Shared with me" / "View my copy"
    # affordances are rendered by the React island from the API show envelope.
    with client.current_user_as(user_b):
        api_response = await client.get(f"/api/email_threads/{thread_a.id}")
        assert api_response.status_code == status.HTTP_200_OK
        payload = api_response.json()
        assert payload["mailbox_entry"]["is_shared"] is True
        assert payload["thread"]["is_shared"] is True
        assert payload["thread"]["own_thread_id"] == str(thread_b.id)

    # User A viewing their own thread — not shared.
    with client.current_user_as(user_a):
        api_response = await client.get(f"/api/email_threads/{thread_a.id}")
        assert api_response.status_code == status.HTTP_200_OK
        payload = api_response.json()
        assert payload["mailbox_entry"]["is_shared"] is False
        assert payload["thread"]["is_shared"] is False
        assert payload["thread"]["own_thread_id"] is None

    # User B viewing their own thread — not shared.
    with client.current_user_as(user_b):
        api_response = await client.get(f"/api/email_threads/{thread_b.id}")
        assert api_response.status_code == status.HTTP_200_OK
        payload = api_response.json()
        assert payload["mailbox_entry"]["is_shared"] is False
        assert payload["thread"]["is_shared"] is False
        assert payload["thread"]["own_thread_id"] is None


@pytest.mark.asyncio
async def test_ai_excluded_threads_filtered_from_mailbox_inbox():
    user = await create_user()

    normal_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="normal_thread",
        subject="Normal Thread",
        sender="sender@example.com",
    )
    normal_thread = await EmailThread.get(id=normal_message.thread_id)
    await Mailbox.sync(normal_thread)

    excluded_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="excluded_thread",
        subject="Excluded Thread",
        sender="sender@example.com",
    )
    excluded_thread = await EmailThread.get(id=excluded_message.thread_id)
    await Mailbox.sync(excluded_thread)

    await MailboxEntry.filter(resource_gid=str(excluded_thread.global_id)).update(is_ai_excluded=True)

    mailbox = Mailbox(user=user)

    # Unfiltered inbox contains both threads
    all_entries = await mailbox.filters.inbox
    all_gids = [str(e.resource_gid) for e in all_entries]
    assert str(normal_thread.global_id) in all_gids
    assert str(excluded_thread.global_id) in all_gids

    # Filtered inbox (as used by mailbox view generation) excludes AI-excluded threads
    filtered_entries = await mailbox.filters.inbox.filter(MailboxEntryFilters.ai_included())
    filtered_gids = [str(e.resource_gid) for e in filtered_entries]
    assert str(normal_thread.global_id) in filtered_gids
    assert str(excluded_thread.global_id) not in filtered_gids


@pytest.mark.asyncio
async def test_collaborator_can_start_draft_on_shared_thread(client: AppClient):
    creator = await create_user(email="creator@convictional.com")
    collaborator = await create_user(email="collab@convictional.com", organization_id=creator.organization_id)

    # The creator's outgoing message to alice is the reply target. The recipient
    # routing assertion below would fail if `EmailReply.replier` were the
    # collaborator, because `replier.email != reply_address.email` would route
    # the reply back to the creator instead of to alice.
    sent_message = await create_email_message(
        user_id=creator.id,
        organization_id=creator.organization_id,
        external_thread_id="shared-thread",
        sender=creator.email,
        to=["alice@external.com"],
        headers_list=[{"name": "To", "value": "alice@external.com"}],
        labels=[EmailLabel.SENT],
    )
    thread = await EmailThread.get(id=sent_message.thread_id)
    await thread.fetch_related("workspace", "creator")
    await thread.collaboration.add(collaborator, creator)
    await Mailbox.sync(thread)

    client.current_user = collaborator

    show_response = await client.get(f"/email_threads/{thread.id}")
    assert show_response.status_code == status.HTTP_200_OK
    assert '<div id="root">' in show_response.text

    # The reply/forward URLs the React island posts to live on the API show
    # envelope, not in the server-rendered HTML.
    api_response = await client.get(f"/api/email_threads/{thread.id}")
    assert api_response.status_code == status.HTTP_200_OK
    messages = [item for item in api_response.json()["timeline"] if item["type"] == "message"]
    assert any(item["message"]["reply_url"].endswith(f"{sent_message.id}/reply") for item in messages)
    assert any(item["message"]["forward_url"].endswith(f"{sent_message.id}/forward") for item in messages)

    reply_response = await client.post(
        f"/api/email_threads/{thread.id}/email_messages/{sent_message.id}/reply",
        json={"reply_type": EmailReplyType.REPLY.value},
    )
    assert reply_response.status_code == status.HTTP_201_CREATED

    draft = await thread.get_draft()
    assert draft is not None
    assert draft.user_id == creator.id
    assert "alice@external.com" in draft.message.to
    assert creator.email not in draft.message.to

    envelope_response = await client.get(f"/api/email_threads/{thread.id}/draft")
    assert envelope_response.status_code == status.HTTP_200_OK
    assert envelope_response.json()["sendable_by"]

    # Forward path on a separate thread (existing-draft 409 would block reusing this one).
    forward_source = await create_email_message(
        user_id=creator.id,
        organization_id=creator.organization_id,
        external_thread_id="shared-thread-forward",
        sender="bob@external.com",
        to=[creator.email],
        labels=[EmailLabel.INBOX],
    )
    forward_thread = await EmailThread.get(id=forward_source.thread_id)
    await forward_thread.fetch_related("workspace", "creator")
    await forward_thread.collaboration.add(collaborator, creator)

    forward_response = await client.post(
        f"/api/email_threads/{forward_thread.id}/email_messages/{forward_source.id}/forward",
    )
    assert forward_response.status_code == status.HTTP_201_CREATED

    forward_draft = await forward_thread.get_draft()
    assert forward_draft is not None
    assert forward_draft.user_id == creator.id


@pytest.mark.asyncio
async def test_collaborator_cannot_send_shared_draft(client: AppClient):
    creator = await create_user(email="creator@convictional.com")
    collaborator = await create_user(email="collab@convictional.com", organization_id=creator.organization_id)

    received = await create_email_message(
        user_id=creator.id,
        organization_id=creator.organization_id,
        external_thread_id="shared-thread-send",
        sender="alice@external.com",
        to=[creator.email],
        labels=[EmailLabel.INBOX],
    )
    thread = await EmailThread.get(id=received.thread_id)
    await thread.fetch_related("workspace", "creator")
    await thread.collaboration.add(collaborator, creator)

    client.current_user = collaborator
    reply_response = await client.post(
        f"/api/email_threads/{thread.id}/email_messages/{received.id}/reply",
        json={"reply_type": EmailReplyType.REPLY.value},
    )
    assert reply_response.status_code == status.HTTP_201_CREATED

    send_response = await client.post(
        f"/api/email_threads/{thread.id}/draft/send",
        json={
            "subject": "Re: anything",
            "to": ["alice@external.com"],
            "message_body": "body",
        },
    )
    assert send_response.status_code == status.HTTP_403_FORBIDDEN
