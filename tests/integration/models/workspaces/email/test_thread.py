from asyncio import gather
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from urllib.parse import urljoin

import pytest

from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailAttachment, EmailMessage, EmailThread
from config import settings
from config.enums import CollaboratorStatus, EmailLabel, EmailMessageType
from infra.storage import FileReference
from tests.helpers.factories import (
    create_collaborator,
    create_email_draft,
    create_email_message,
    create_email_thread,
    create_organization,
    create_user,
)


@pytest.mark.asyncio
async def test_thread_creation_via_message():
    user = await create_user()
    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_123",
        subject="Re: Important Conversation",
    )

    # Thread should be automatically created via the pre_save signal
    assert message.thread_id is not None

    # Verify thread was created with normalized subject
    thread = await EmailThread.get(id=message.thread_id)
    assert thread.external_thread_id == "thread_123"
    assert thread.title == "Important Conversation"  # "Re:" should be stripped
    assert thread.creator_id == user.id


@pytest.mark.asyncio
async def test_thread_reuse_for_same_external_thread_id():
    user = await create_user()
    first_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_456",
        external_message_id="msg_1",
        subject="Project Update",
        sender="alice@example.com",
    )
    second_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_456",
        external_message_id="msg_2",
        subject="Re: Project Update",
        sender="bob@example.com",
    )
    # Both messages should be linked to the same thread
    assert first_message.thread_id == second_message.thread_id

    # Verify thread metadata is updated
    thread = await EmailThread.get(id=first_message.thread_id).prefetch_related("messages")
    sender_emails = [address.email for address in thread.sender_addresses_unique]
    assert len(sender_emails) == 2
    assert "alice@example.com" in sender_emails
    assert "bob@example.com" in sender_emails


@pytest.mark.asyncio
async def test_thread_metadata_aggregation():
    user = await create_user()
    thread_id = "thread_789"
    first_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id=thread_id,
        external_message_id="msg_1",
        subject="Weekly Meeting",
        sender="Alice Smith <alice@example.com>",
        to=["bob@example.com", "charlie@example.com"],
        cc=["manager@example.com"],
        labels=[EmailLabel.INBOX],
        received_at=datetime(2024, 1, 1, 10, 0, 0, tzinfo=UTC),
    )
    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id=thread_id,
        external_message_id="msg_2",
        subject="Re: Weekly Meeting",
        sender="Bob Johnson <bob@example.com>",
        to=["alice@example.com"],
        labels=[EmailLabel.INBOX],
        received_at=datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC),
    )
    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id=thread_id,
        external_message_id="msg_3",
        subject="Re: Weekly Meeting - Urgent",
        sender="Charlie Brown <charlie@example.com>",
        to=["alice@example.com", "bob@example.com"],
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        received_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    thread = await EmailThread.get(id=first_message.thread_id).prefetch_related("messages")

    # Check aggregated senders
    sender_emails = [address.email for address in thread.sender_addresses_unique]
    assert len(sender_emails) == 3
    assert "alice@example.com" in sender_emails
    assert "bob@example.com" in sender_emails
    assert "charlie@example.com" in sender_emails

    # Check aggregated labels
    expected_labels = [EmailLabel.INBOX, EmailLabel.UNREAD]
    assert set(thread.labels) == set(expected_labels)

    # Check latest timestamp
    assert thread.last_message_at == datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_thread_isolation_between_users():
    first_user = await create_user()
    second_user = await create_user()

    # Create messages with same external_thread_id for different users
    first_message = await create_email_message(
        user_id=first_user.id,
        organization_id=first_user.organization_id,
        external_thread_id="thread_shared",
        subject="Test Message",
    )
    second_message = await create_email_message(
        user_id=second_user.id,
        organization_id=second_user.organization_id,
        external_thread_id="thread_shared",
        subject="Test Message",
    )
    # Should create separate threads for different users
    assert first_message.thread_id != second_message.thread_id
    first_thread = await EmailThread.get(id=first_message.thread_id)
    second_thread = await EmailThread.get(id=second_message.thread_id)
    assert first_thread.creator_id == first_user.id
    assert second_thread.creator_id == second_user.id


@pytest.mark.asyncio
async def test_thread_soft_deletion_when_all_messages_deleted():
    user = await create_user()
    email = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_message_id="msg_thread_delete",
        external_thread_id="thread_delete_test",
        external_history_id="789",
        subject="Thread Delete Test",
        sender="sender@example.com",
        to=["recipient@example.com"],
        body_plain="This message will be deleted",
        preview="Message that will cause thread deletion",
        deleted_at=datetime.now(UTC),
    )

    thread: EmailThread = await EmailThread.unscoped.get_queryset().get(id=email.thread_id)
    assert thread.is_deleted


@pytest.mark.asyncio
async def test_thread_restoration_when_active_message_added():
    user = await create_user()
    deleted_email = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_message_id="msg_restore_1",
        external_thread_id="thread_restore_test",
        external_history_id="111",
        subject="Thread Restore Test",
        sender="sender@example.com",
        to=["recipient@example.com"],
        body_plain="Deleted message",
        preview="Deleted message",
        deleted_at=datetime.now(UTC),
    )

    # Check the thread is soft deleted
    thread: EmailThread = await EmailThread.unscoped.get_queryset().get(id=deleted_email.thread_id)
    assert thread.is_deleted

    # Now add an active message to the same thread
    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_message_id="msg_restore_2",
        external_thread_id="thread_restore_test",
        external_history_id="222",
        subject="Thread Restore Test",
        sender="sender@example.com",
        to=["recipient@example.com"],
        body_plain="Active message",
        preview="Active message",
    )

    # Refresh the thread and verify it's restored
    await thread.refresh_from_db()
    assert not thread.is_deleted


@pytest.mark.asyncio
async def test_thread_metadata_reset_when_no_messages():
    user = await create_user()
    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_empty_test",
        subject="Thread Metadata Test",
        sender="Alice Smith <alice@example.com>",
        to=["bob@example.com"],
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
    )
    thread = await EmailThread.get(id=message.thread_id).prefetch_related("messages")

    # Verify thread has metadata
    sender_emails = [address.email for address in thread.sender_addresses_unique]
    assert len(sender_emails) == 1
    assert "alice@example.com" in sender_emails
    assert len(thread.labels) > 0

    # Delete all messages
    await message.delete()  # Hard delete to simulate no messages
    await thread.update_metadata_from_messages()

    # Verify metadata is updated for empty thread
    await thread.refresh_from_db()
    await thread.fetch_related("messages")
    assert len(thread.sender_addresses_unique) == 0
    assert thread.labels == []


@pytest.mark.asyncio
async def test_email_message_sort_key():
    """Test EmailMessage sort_key property generates correct sorting tuples."""
    user = await create_user()
    received_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Test sort_key generation
    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_id="foo",
        received_at=received_at,
        headers_list=[{"name": "Date", "value": "Mon, 1 Jan 2024 11:00:00 +0000"}],
    )

    sort_key = message.sort_key
    assert sort_key[0] == received_at
    assert sort_key[2] == "foo"
    assert sort_key[1] == datetime(2024, 1, 1, 11, 0, 0, tzinfo=UTC)

    # Test default values
    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_id=None,
        received_at=None,
        sent_at=None,
    )

    sort_key = message.sort_key
    assert sort_key[0] == datetime.min.replace(tzinfo=UTC)
    assert sort_key[1] == datetime.min.replace(tzinfo=UTC)
    assert sort_key[2] == ""


@pytest.mark.asyncio
async def test_email_payload_generates_correct_attachment_download_urls():
    """Test that EmailDraft.as_payload() generates download URLs that match the actual route pattern.

    This test will fail if the email attachment download route pattern changes,
    ensuring that inline attachment URL generation stays in sync with the actual routes.
    """
    user = await create_user()
    email_draft = await create_email_draft(
        user_id=user.id,
        organization_id=user.organization_id,
        subject="Test Email with Inline Attachment",
        body_html="<p>Email with inline image:</p>",
    )

    # Create a test file reference (mock the download method)
    file_ref = await FileReference.create(
        key="test/image.png", filename="test-image.png", content_type="image/png", byte_size=1024, checksum="abc123"
    )

    # Create an inline attachment
    attachment = await EmailAttachment.create(
        email_message_id=email_draft.id,
        file_id=file_ref.id,
        content_id="test-content-id",
        is_inline=True,
        thread_id=email_draft.thread_id,
    )

    # Update the HTML to reference the actual attachment ID with the full URL
    attachment_url = urljoin(
        str(settings.base_url),
        f"email_threads/{email_draft.thread_id}/attachments/{attachment.id}/download",
    )
    email_draft.message.body_html = f'<p>Email with inline image:<img src="{attachment_url}" alt="test"></p>'
    email_draft.message.body_markdown = "Email with inline image"
    await email_draft.save()

    # Fetch related attachments and generate the payload (mock file download)
    await email_draft.fetch_related("attachments__file", "thread__messages")

    with patch.object(
        email_draft.message.attachments[0].file, "download", new=AsyncMock(return_value=b"fake image content")
    ):
        payload = await email_draft.as_payload()

    # Find the inline attachment in the payload
    inline_attachment = next(
        (att for att in payload.attachments if att.is_inline and att.content_id == "test-content-id"), None
    )
    assert inline_attachment is not None

    # Verify the download URL matches the expected route pattern
    expected_url = urljoin(
        str(settings.base_url),
        f"/email_threads/{email_draft.thread_id}/attachments/{attachment.id}/download",
    )
    assert inline_attachment.download_url == expected_url, (
        f"Download URL mismatch. Expected: {expected_url}, Got: {inline_attachment.download_url}. "
        f"This indicates the route pattern may have changed. Please update the URL generation in "
        f"EmailAttachment.as_payload() to match the route pattern in email_attachments router."
    )


@pytest.mark.asyncio
async def test_email_thread_preview():
    user = await create_user()

    # Create messages with different read states
    first_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="preview_test",
        subject="First Message",
        preview="First message preview",
        labels=[EmailLabel.INBOX],  # Read message (no UNREAD label)
    )
    second_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="preview_test",
        subject="Second Message",
        preview="Second message preview",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],  # Unread message
    )

    thread = await EmailThread.get(id=first_message.thread_id).prefetch_related("messages__attachments")

    # Should return preview from most recent unread message
    assert thread.preview == "Second message preview"

    # If all messages are read, should return preview from latest message
    second_message.labels.remove(EmailLabel.UNREAD)
    await second_message.save()
    await thread.refresh_from_db()
    await thread.fetch_related("messages__attachments")

    assert thread.preview == "Second message preview"


@pytest.mark.asyncio
async def test_sorted_conversation_simple_thread():
    """Test sorted_conversation with a simple reply thread."""
    user = await create_user()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Create original message
    original = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg1",
        received_at=base_time,
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="test_thread",
    )

    # Create reply - same external_thread_id will link to same thread
    reply = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg2",
        received_at=base_time.replace(hour=13),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="test_thread",
        headers_list=[{"name": "In-Reply-To", "value": "msg1"}],
    )

    # Get the thread and fetch messages
    thread = await EmailThread.get(id=original.thread_id).prefetch_related("messages")

    sorted_messages = thread.sorted_conversation

    assert len(sorted_messages) == 2
    assert sorted_messages[0].id == original.id  # Original first
    assert sorted_messages[1].id == reply.id  # Reply second


@pytest.mark.asyncio
async def test_sorted_conversation_filters_drafts():
    """Test sorted_conversation filters out draft messages."""
    user = await create_user()

    delivered = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg1",
        received_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="filter_test",
    )

    # Get the thread first, then start a draft on it
    thread = await EmailThread.get(id=delivered.thread_id)
    await thread.start_draft(user=user, subject="Draft subject", body_plain="Draft body")

    # Refresh thread with messages
    await thread.fetch_related("messages")

    sorted_messages = thread.sorted_conversation

    assert len(sorted_messages) == 1
    assert sorted_messages[0].id == delivered.id


@pytest.mark.asyncio
async def test_email_thread_start_draft():
    user = await create_user()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
    original = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg1",
        received_at=base_time,
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="complex_thread",
    )
    reply = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg2",
        received_at=base_time.replace(hour=13),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="complex_thread",
        headers_list=[{"name": "In-Reply-To", "value": "msg1"}],
    )

    # Get the thread first, then start a draft on it
    thread = await EmailThread.get(id=original.thread_id)
    draft = await thread.start_draft(user=user, subject="Draft subject", body_plain="Draft body")
    assert draft is not None
    assert draft.message.in_reply_to_id == reply.id

    # Verify live document was created
    topic = draft.live_document_topic
    live_doc = await LiveDocument.for_topic(topic)
    assert live_doc is not None
    # Verify it starts empty
    assert live_doc.markdown == ""

    # Start a new draft in reply to the first reply
    draft = await thread.start_draft(
        user=user, subject="New Draft Subject", body_plain="New Draft Body", in_reply_to=original
    )
    assert draft is not None
    assert draft.message.in_reply_to_id == original.id

    # Verify new draft gets its own live document
    new_topic = draft.live_document_topic
    new_live_doc = await LiveDocument.for_topic(new_topic)
    assert new_live_doc is not None
    assert new_live_doc.markdown == ""


@pytest.mark.asyncio
async def test_sorted_conversation_complex_thread():
    """Test sorted_conversation with branching conversation."""
    user = await create_user()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Original message
    original = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg1",
        received_at=base_time,
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="complex_thread",
    )

    # First reply
    reply = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg2",
        received_at=base_time.replace(hour=13),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="complex_thread",
        headers_list=[{"name": "In-Reply-To", "value": "msg1"}],
    )

    # Reply to the first reply
    reply_to_reply = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg3",
        received_at=base_time.replace(hour=14),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="complex_thread",
        headers_list=[{"name": "In-Reply-To", "value": "msg2"}],
    )

    # Another direct reply to original
    second_reply = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg4",
        received_at=base_time.replace(hour=15),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="complex_thread",
        headers_list=[{"name": "In-Reply-To", "value": "msg1"}],
    )

    thread = await EmailThread.get(id=original.thread_id).prefetch_related("messages")

    sorted_messages = thread.sorted_conversation

    # (Original, then first reply chain, then second branch)
    assert len(sorted_messages) == 4
    assert sorted_messages[0].id == original.id
    assert sorted_messages[1].id == reply.id
    assert sorted_messages[2].id == reply_to_reply.id
    assert sorted_messages[3].id == second_reply.id


@pytest.mark.asyncio
async def test_sorted_conversation_orphaned_messages():
    """Test sorted_conversation handles orphaned messages (references missing parent)."""
    user = await create_user()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Message that references a non-existent parent
    orphan = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="orphan",
        received_at=base_time,
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="orphan_thread",
        headers_list=[{"name": "In-Reply-To", "value": "missing_parent"}],
    )

    # Regular message
    regular = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="regular",
        received_at=base_time.replace(hour=13),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="orphan_thread",
    )

    thread = await EmailThread.get(id=orphan.thread_id).prefetch_related("messages")

    sorted_messages = thread.sorted_conversation

    # Both should be included, sorted by time
    assert len(sorted_messages) == 2
    assert sorted_messages[0].id == orphan.id  # Earlier time
    assert sorted_messages[1].id == regular.id  # Later time


@pytest.mark.asyncio
async def test_sorted_conversation_falling_back_to_references():
    """Test sorted_conversation handles messages that include references."""
    user = await create_user()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Create original message
    original = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg1",
        received_at=base_time,
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="test_thread",
    )

    # Create reply - same external_thread_id will link to same thread
    reply = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg2",
        received_at=base_time.replace(hour=13),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="test_thread",
        headers_list=[{"name": "References", "value": "msg1"}],
    )

    # Get the thread and fetch messages
    thread = await EmailThread.get(id=original.thread_id).prefetch_related("messages")

    sorted_messages = thread.sorted_conversation

    assert len(sorted_messages) == 2
    assert sorted_messages[0].id == original.id  # Original first
    assert sorted_messages[1].id == reply.id  # Reply second


@pytest.mark.asyncio
async def test_sorted_conversation_self_reference():
    """Test sorted_conversation handles self-referencing messages."""
    user = await create_user()

    # Message that references itself (shouldn't create cycle)
    self_ref = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="self_ref",
        received_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="self_ref_thread",
        headers_list=[{"name": "In-Reply-To", "value": "self_ref"}],
    )

    thread = await EmailThread.get(id=self_ref.thread_id).prefetch_related("messages")

    sorted_messages = thread.sorted_conversation

    assert len(sorted_messages) == 1
    assert sorted_messages[0].id == self_ref.id


@pytest.mark.asyncio
async def test_sorted_conversation_sent_message_without_received_at():
    """Sent messages without received_at sort by sent_at, not datetime.min.

    Reproduces the bug where a user drafts a reply to a message, another reply arrives
    while drafting, and the sent reply sorts before the intervening message because
    sort_key falls back to datetime.min when received_at is None.
    """
    user = await create_user()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    original = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg1",
        received_at=base_time,
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="sent_ordering_thread",
    )

    intervening = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="msg2",
        received_at=base_time.replace(hour=13),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="sent_ordering_thread",
        headers_list=[{"name": "In-Reply-To", "value": "msg1"}],
    )

    # User's sent reply — received_at is None (not yet synced from Gmail),
    # but sent_at is set. This is the state after mark_as_sent() but before Gmail sync.
    sent_reply = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_id="msg3",
        received_at=None,
        sent_at=base_time.replace(hour=14),
        message_type=EmailMessageType.SENT,
        thread_id=original.thread_id,
        external_thread_id="sent_ordering_thread",
        headers_list=[{"name": "In-Reply-To", "value": "msg1"}],
    )

    thread = await EmailThread.get(id=original.thread_id).prefetch_related("messages")
    sorted_messages = thread.sorted_conversation

    assert len(sorted_messages) == 3
    assert sorted_messages[0].id == original.id
    assert sorted_messages[1].id == intervening.id
    assert sorted_messages[2].id == sent_reply.id


@pytest.mark.asyncio
async def test_draft_references_header_rfc_compliance():
    """Test that draft References header follows RFC 5322 specification."""
    user = await create_user()
    base_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)

    # Create original message
    original = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="<original@example.com>",
        received_at=base_time,
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="rfc_test_thread",
        headers_list=[{"name": "Message-ID", "value": "<original@example.com>"}],
    )

    # Create reply with References header
    reply = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="<reply1@example.com>",
        received_at=base_time.replace(hour=13),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="rfc_test_thread",
        headers_list=[
            {"name": "Message-ID", "value": "<reply1@example.com>"},
            {"name": "References", "value": "<original@example.com>"},
            {"name": "In-Reply-To", "value": "<original@example.com>"},
        ],
    )

    # Create another reply with accumulated References
    reply2 = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        message_id="<reply2@example.com>",
        received_at=base_time.replace(hour=14),
        message_type=EmailMessageType.RECEIVED,
        external_thread_id="rfc_test_thread",
        headers_list=[
            {"name": "Message-ID", "value": "<reply2@example.com>"},
            {"name": "References", "value": "<original@example.com> <reply1@example.com>"},
            {"name": "In-Reply-To", "value": "<reply1@example.com>"},
        ],
    )

    # Get thread and create draft in reply to reply2
    thread = await EmailThread.get(id=original.thread_id)
    await thread.fetch_related("messages")
    draft = await thread.start_draft(user=user, subject="Re: Test", body_plain="Draft body", in_reply_to=reply2)
    # Fetch the in_reply_to relationship for the draft message
    await draft.fetch_related("in_reply_to")

    # Test RFC 5322 compliance: References should contain parent's References + parent's Message-ID
    expected_references = "original@example.com reply1@example.com <reply2@example.com>"
    assert draft.references == expected_references

    # Test with parent that has no References but has In-Reply-To
    draft_reply_to_original = await thread.start_draft(
        user=user, subject="Re: Original", body_plain="Reply to original", in_reply_to=original
    )
    await draft_reply_to_original.fetch_related("in_reply_to")
    # Original has no References or In-Reply-To, so should just be its Message-ID
    assert draft_reply_to_original.references == "<original@example.com>"

    # REGRESSION TEST: Reply to first reply (not the latest message in thread)
    # This ensures we don't include reply2's Message-ID when replying to reply1
    draft_reply_to_middle = await thread.start_draft(
        user=user, subject="Re: First Reply", body_plain="Reply to the first reply, not the latest", in_reply_to=reply
    )
    await draft_reply_to_middle.fetch_related("in_reply_to")
    # Should only contain reply1's References + reply1's Message-ID
    # Should NOT include reply2's Message-ID even though it's the latest in the thread
    expected_regression_references = "original@example.com <reply1@example.com>"
    assert draft_reply_to_middle.references == expected_regression_references
    assert "<reply2@example.com>" not in draft_reply_to_middle.references

    # Test with no in_reply_to (new thread)
    new_thread = await create_email_thread(
        creator_id=user.id, organization_id=user.organization_id, title="New Thread"
    )
    new_draft = await new_thread.start_draft(user=user, subject="New Message", body_plain="New message body")
    # No in_reply_to should result in empty References
    assert new_draft.references == ""


@pytest.mark.asyncio
async def test_email_labels_normalization():
    message = await create_email_message(
        external_thread_id="test_sorting",
        subject="Test Label Sorting",
        labels=[EmailLabel.SPAM, EmailLabel.INBOX, EmailLabel.UNREAD, EmailLabel.INBOX, EmailLabel.DRAFT],
    )

    # Labels should be sorted and deduplicated
    expected_labels = sorted({EmailLabel.SPAM, EmailLabel.INBOX, EmailLabel.UNREAD, EmailLabel.DRAFT})
    assert message.labels == expected_labels

    # Test updating labels maintains sorting
    message.labels = [EmailLabel.SENT, EmailLabel.SPAM, EmailLabel.UNREAD, EmailLabel.SENT]
    await message.save()

    # Labels should be sorted and deduplicated
    expected_updated_labels = sorted({EmailLabel.SENT, EmailLabel.SPAM, EmailLabel.UNREAD})
    assert message.labels == expected_updated_labels


@pytest.mark.asyncio
async def test_save_draft_updates_thread_and_mailbox():
    user = await create_user()
    thread = await create_email_thread(
        creator_id=user.id,
        organization_id=user.organization_id,
        title="Original Title",
        labels=[EmailLabel.DRAFT],
    )

    # Start a draft
    draft = await thread.start_draft(user=user, subject="Initial Draft Subject", body_plain="Draft body")
    await thread.refresh_from_db()
    assert thread.title == "Initial Draft Subject"

    # Sender address should be the parsed email address of the thread creator
    test_user_email = EmailAddress.parse_safe(user.email)
    assert test_user_email is not None
    assert thread.sender_addresses_unique == [test_user_email]

    # Update draft subject
    draft.message.subject = "Updated Draft Subject"
    await thread.save_draft(draft, user)

    # Verify thread title was updated
    assert thread.title == "Updated Draft Subject"

    # Verify mailbox entry was synced with updated title
    mailbox_entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=user.id)
    assert mailbox_entry.title == "Updated Draft Subject"


@pytest.mark.asyncio
async def test_thread_timestamps_from_messages():
    """Thread timestamps computed from earliest/latest messages regardless of creation order"""
    user = await create_user()

    # Start with middle-timestamped message
    msg2 = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_timestamps",
        external_message_id="msg_2",
        subject="Second Message",
        received_at=datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=msg2.thread_id).prefetch_related("messages")
    assert thread.created_at == datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC)
    assert thread.updated_at == datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC)

    # Add later message - should update updated_at
    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_timestamps",
        external_message_id="msg_3",
        subject="Third Message",
        received_at=datetime(2024, 1, 3, 15, 0, 0, tzinfo=UTC),
    )

    await thread.refresh_from_db()
    await thread.fetch_related("messages")
    assert thread.created_at == datetime(2024, 1, 2, 12, 0, 0, tzinfo=UTC)
    assert thread.updated_at == datetime(2024, 1, 3, 15, 0, 0, tzinfo=UTC)

    # Add earlier message - should update created_at
    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_timestamps",
        external_message_id="msg_1",
        subject="First Message",
        received_at=datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC),
    )

    await thread.refresh_from_db()
    await thread.fetch_related("messages")
    assert thread.created_at == datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)
    assert thread.updated_at == datetime(2024, 1, 3, 15, 0, 0, tzinfo=UTC)

    # Add another in-between message - timestamps unchanged (still earliest/latest)
    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_timestamps",
        external_message_id="msg_middle",
        subject="Middle Message",
        received_at=datetime(2024, 1, 2, 20, 0, 0, tzinfo=UTC),
    )

    await thread.refresh_from_db()
    await thread.fetch_related("messages")
    assert thread.created_at == datetime(2024, 1, 1, 8, 0, 0, tzinfo=UTC)
    assert thread.updated_at == datetime(2024, 1, 3, 15, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_thread_timestamps_with_draft_only():
    """Draft-only thread timestamps should use draft's created_at"""
    user = await create_user()
    org = await create_organization()

    # Create a thread with only a draft
    thread = await EmailThread.create(
        creator_id=user.id,
        organization_id=org.id,
        title="Draft Thread",
        labels=[EmailLabel.DRAFT],
    )

    # Start a draft
    draft = await thread.start_draft(
        user=user,
        subject="Draft Only",
        body_plain="This is a draft",
    )

    # Manually set the draft's created_at for testing
    draft.message.created_at = datetime(2024, 2, 1, 9, 0, 0, tzinfo=UTC)
    await draft.message.save()

    # Update metadata to recompute timestamps
    await thread.update_metadata_from_messages()
    await thread.refresh_from_db()

    # Thread timestamps should match the draft's created_at
    assert thread.created_at == datetime(2024, 2, 1, 9, 0, 0, tzinfo=UTC)
    assert thread.updated_at == datetime(2024, 2, 1, 9, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_thread_timestamps_when_message_removed():
    """Timestamps should update when messages are removed"""
    user = await create_user()

    # Create three messages
    msg1 = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_remove_msgs",
        external_message_id="msg_1",
        subject="First",
        received_at=datetime(2024, 4, 1, 10, 0, 0, tzinfo=UTC),
    )

    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_remove_msgs",
        external_message_id="msg_2",
        subject="Second",
        received_at=datetime(2024, 4, 2, 11, 0, 0, tzinfo=UTC),
    )

    msg3 = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_remove_msgs",
        external_message_id="msg_3",
        subject="Third",
        received_at=datetime(2024, 4, 3, 12, 0, 0, tzinfo=UTC),
    )

    thread = await EmailThread.get(id=msg1.thread_id).prefetch_related("messages")

    # Verify initial timestamps
    assert thread.created_at == datetime(2024, 4, 1, 10, 0, 0, tzinfo=UTC)
    assert thread.updated_at == datetime(2024, 4, 3, 12, 0, 0, tzinfo=UTC)

    # Remove the first message (earliest)
    await thread.remove_message(msg1)
    await thread.refresh_from_db()
    await thread.fetch_related("messages")

    # created_at should now be the second message
    assert thread.created_at == datetime(2024, 4, 2, 11, 0, 0, tzinfo=UTC)
    # updated_at should still be the third message
    assert thread.updated_at == datetime(2024, 4, 3, 12, 0, 0, tzinfo=UTC)

    # Remove the third message (latest)
    await thread.remove_message(msg3)
    await thread.refresh_from_db()
    await thread.fetch_related("messages")

    # Both timestamps should now be the second message
    assert thread.created_at == datetime(2024, 4, 2, 11, 0, 0, tzinfo=UTC)
    assert thread.updated_at == datetime(2024, 4, 2, 11, 0, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_concurrent_get_or_create_does_not_raise_integrity_error():
    """Concurrent get_or_create_for_message calls with the same external_thread_id
    should not raise IntegrityError — one creates the thread, the other returns it."""
    user = await create_user()
    message_data = {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "external_thread_id": "concurrent_thread_123",
        "subject": "Test Subject",
    }

    results = await gather(
        EmailThread.get_or_create_for_message(message_data),
        EmailThread.get_or_create_for_message(message_data),
    )

    threads = [r[0] for r in results]
    created_flags = [r[1] for r in results]

    assert threads[0].id == threads[1].id
    assert sorted(created_flags) == [False, True]
    assert await EmailThread.filter(creator_id=user.id, external_thread_id="concurrent_thread_123").count() == 1


@pytest.mark.asyncio
async def test_inbound_reply_joins_collaborative_thread_via_references():
    org = await create_organization()
    composer = await create_user(organization_id=org.id)
    assignee = await create_user(organization_id=org.id)

    # Root message composed by A, establishing the shared thread T.
    root = await create_email_message(
        user_id=composer.id,
        organization_id=org.id,
        external_thread_id="a_mailbox_thread",
        external_message_id="a_root",
        message_id="<root@x>",
        subject="Shared thread",
    )
    shared_thread = await EmailThread.get(id=root.thread_id)

    # B is a collaborator on T's workspace (the shared/assignee relationship).
    await create_collaborator(workspace_id=shared_thread.workspace_id, user_id=assignee.id, organization_id=org.id)

    # Scenario 1 — inbound reply arrives in B's mailbox with a DIFFERENT Gmail
    # thread id, but an In-Reply-To pointing at the root Message-ID. It must join
    # the shared thread rather than fragment into a new one.
    reply = await create_email_message(
        user_id=assignee.id,
        organization_id=org.id,
        external_thread_id="b_mailbox_thread",
        external_message_id="b_reply",
        message_id="<reply@x>",
        subject="Re: Shared thread",
        headers_list=[{"name": "In-Reply-To", "value": "<root@x>"}],
    )
    assert reply.thread_id == shared_thread.id
    assert await EmailThread.filter(organization_id=org.id).count() == 1

    # Scenario 2 — a second inbound reply carries ONLY a References header (the
    # mailing-list case). This guards bracket canonicalization: EmailHeaders.references
    # strips to `root@x` while the stored Message-ID is `<root@x>`.
    references_reply = await create_email_message(
        user_id=assignee.id,
        organization_id=org.id,
        external_thread_id="b_mailbox_thread_2",
        external_message_id="b_reply_2",
        message_id="<reply2@x>",
        subject="Re: Shared thread",
        headers_list=[{"name": "References", "value": "<root@x>"}],
    )
    assert references_reply.thread_id == shared_thread.id

    # Scenario 3 — over-merge guard. C owns their own thread that B is NOT a
    # collaborator on; an inbound message from B referencing C's Message-ID must
    # NOT merge into C's thread.
    stranger = await create_user(organization_id=org.id)
    stranger_msg = await create_email_message(
        user_id=stranger.id,
        organization_id=org.id,
        external_thread_id="c_mailbox_thread",
        external_message_id="c_msg",
        message_id="<stranger@x>",
    )
    stranger_thread_id = stranger_msg.thread_id
    no_merge = await create_email_message(
        user_id=assignee.id,
        organization_id=org.id,
        external_thread_id="b_mailbox_thread_3",
        external_message_id="b_reply_3",
        message_id="<reply3@x>",
        subject="Re: Something else",
        headers_list=[{"name": "In-Reply-To", "value": "<stranger@x>"}],
    )
    assert no_merge.thread_id not in {stranger_thread_id, shared_thread.id}

    # Scenario 4 — baseline. No In-Reply-To/References: creates its own thread.
    baseline = await create_email_message(
        user_id=assignee.id,
        organization_id=org.id,
        external_thread_id="b_mailbox_thread_4",
        external_message_id="b_reply_4",
        message_id="<reply4@x>",
        subject="A brand new conversation",
    )
    assert baseline.thread_id is not None
    assert baseline.thread_id != shared_thread.id

    # Scenario 5 — PENDING collaborators are NOT matched. The fallback is scoped
    # to APPROVED collaborators (by_collaborated_workspaces), so a user who is only
    # a PENDING collaborator on T's workspace must not have their inbound reply
    # merged into the shared thread.
    pending_user = await create_user(organization_id=org.id)
    await create_collaborator(
        workspace_id=shared_thread.workspace_id,
        user_id=pending_user.id,
        organization_id=org.id,
        status=CollaboratorStatus.PENDING,
    )
    pending_reply = await create_email_message(
        user_id=pending_user.id,
        organization_id=org.id,
        external_thread_id="pending_mailbox_thread",
        external_message_id="pending_reply",
        message_id="<pending_reply@x>",
        subject="Re: Shared thread",
        headers_list=[{"name": "In-Reply-To", "value": "<root@x>"}],
    )
    assert pending_reply.thread_id != shared_thread.id

    # Scenario 6 — soft-deleted shared thread is found AND restored. The fallback
    # queries via cls.unscoped.get_queryset(), so a soft-deleted shared thread is
    # still matched, and joining it restores the thread.
    thread = await EmailThread.unscoped.get_queryset().get(id=shared_thread.id)
    await thread.soft_delete()
    assert thread.is_deleted

    restore_reply = await create_email_message(
        user_id=assignee.id,
        organization_id=org.id,
        external_thread_id="restore_mailbox_thread",
        external_message_id="restore_reply",
        message_id="<restore_reply@x>",
        subject="Re: Shared thread",
        headers_list=[{"name": "In-Reply-To", "value": "<root@x>"}],
    )
    assert restore_reply.thread_id == shared_thread.id

    refreshed = await EmailThread.unscoped.get_queryset().get(id=shared_thread.id)
    assert not refreshed.is_deleted


@pytest.mark.asyncio
async def test_draft_owner_for():
    creator = await create_user()
    assignee = await create_user(organization_id=creator.organization_id)
    collaborator = await create_user(organization_id=creator.organization_id)

    # Existing thread (external_thread_id set): only the creator can_reply,
    # so collaborators get redirected to creator-owned drafts.
    existing_thread = await create_email_thread(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        external_thread_id="thread_existing",
    )
    await existing_thread.fetch_related("workspace", "creator")
    await existing_thread.collaboration.add(collaborator, creator)
    await existing_thread.collaboration.add(assignee, creator)
    await existing_thread.collaboration.assign_to(assignee, creator)

    assert existing_thread.draft_owner_for(creator).id == creator.id
    assert existing_thread.draft_owner_for(collaborator).id == creator.id
    # Even an assignee owns drafts under the creator on existing threads,
    # because can_reply only opens to assignees on new threads.
    assert existing_thread.draft_owner_for(assignee).id == creator.id

    # New thread (no external_thread_id): the assignee can_reply too, so they
    # own their own draft. Non-assignee collaborators still get the creator.
    new_thread = await create_email_thread(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        external_thread_id=None,
    )
    await new_thread.fetch_related("workspace", "creator")
    await new_thread.collaboration.add(collaborator, creator)
    await new_thread.collaboration.add(assignee, creator)
    await new_thread.collaboration.assign_to(assignee, creator)

    assert new_thread.draft_owner_for(creator).id == creator.id
    assert new_thread.draft_owner_for(assignee).id == assignee.id
    assert new_thread.draft_owner_for(collaborator).id == creator.id


@pytest.mark.asyncio
async def test_mark_as_read_bulk_updates_messages_without_n_plus_one():
    # Regression for the mark_read N+1: marking a thread read used to issue one
    # UPDATE emailmessage per unread message. It must now batch into a single
    # bulk_update while still clearing UNREAD on every message.
    user = await create_user()
    for i in range(3):
        await create_email_message(
            creator_id=user.id,
            organization_id=user.organization_id,
            message_id=f"msg{i}",
            external_thread_id="bulk_read_thread",
            message_type=EmailMessageType.RECEIVED,
            labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        )

    thread = await EmailThread.get(external_thread_id="bulk_read_thread").prefetch_related("messages")
    assert sum(1 for m in thread.messages if m.is_unread) == 3

    with patch.object(EmailMessage, "bulk_update", wraps=EmailMessage.bulk_update) as bulk_update:
        await thread.mark_as_read()

    assert bulk_update.call_count == 1
    assert len(bulk_update.call_args.args[0]) == 3

    refreshed = await EmailMessage.filter(thread_id=thread.id)
    assert all(m.is_read for m in refreshed)
    assert all(EmailLabel.UNREAD not in m.labels for m in refreshed)


@pytest.mark.asyncio
async def test_mark_as_unread_bulk_updates_messages_without_n_plus_one():
    # Symmetric guard for mark_as_unread, which shares the batching helper.
    user = await create_user()
    for i in range(3):
        await create_email_message(
            creator_id=user.id,
            organization_id=user.organization_id,
            message_id=f"msg{i}",
            external_thread_id="bulk_unread_thread",
            message_type=EmailMessageType.RECEIVED,
            labels=[EmailLabel.INBOX],
        )

    thread = await EmailThread.get(external_thread_id="bulk_unread_thread").prefetch_related("messages")
    assert all(m.is_read for m in thread.messages)

    with patch.object(EmailMessage, "bulk_update", wraps=EmailMessage.bulk_update) as bulk_update:
        await thread.mark_as_unread()

    assert bulk_update.call_count == 1
    assert len(bulk_update.call_args.args[0]) == 3

    refreshed = await EmailMessage.filter(thread_id=thread.id)
    assert all(m.is_unread for m in refreshed)
