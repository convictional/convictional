import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from freezegun import freeze_time

from app.jobs.mailers import SendOnboardingMailboxSyncCompletedEmailJob
from app.models.workspaces.email.thread import EmailAttachment, EmailMessage, EmailThread
from config.enums import EmailLabel
from infra.email import EmailHeaders, FakeDelivery
from infra.jobs import InlineJobs, JobsOutbox
from integrations.google.enums import GmailLabel
from integrations.google.gmail import (
    GmailMessageExtractor,
    GmailMessageLoader,
    MockGmailAPIState,
    MockGmailAPIStateRegistry,
    MockGoogleAPIClient,
)
from integrations.google.jobs.gmail_onboarding_sync import OnboardingMailboxSyncGmailJob
from integrations.google.types import GmailMessage
from tests.helpers.factories import create_gmail_account

# GmailMessageLoader Integration Tests


@pytest.mark.asyncio
async def test_create_email_record_basic():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    message_data: GmailMessage = {
        "id": "msg_123456",
        "threadId": "thread_789",
        "historyId": "67890",
        "labelIds": [GmailLabel.INBOX, GmailLabel.UNREAD],
        "snippet": "This is a test email snippet",
    }

    headers = EmailHeaders(
        [
            {"name": "subject", "value": "Test Email"},
            {"name": "from", "value": "John Doe <john@example.com>"},
            {"name": "to", "value": "jane@example.com"},
            {"name": "date", "value": "Wed, 25 Dec 2024 10:15:30 +0000"},
            {"name": "message-id", "value": "<msg123@example.com>"},
        ]
    )

    new_message_result = await loader.create_email_record(message_data, headers, "Hello world!", None)
    email = new_message_result.email
    thread = new_message_result.thread
    assert new_message_result.was_new_thread

    # Verify the email was created correctly
    assert email.external_message_id == "msg_123456"
    assert email.external_thread_id == "thread_789"
    assert email.external_history_id == "67890"
    assert email.subject == "Test Email"
    assert email.sender == "John Doe <john@example.com>"
    assert email.to == ["jane@example.com"]
    assert email.body_plain == "Hello world!"
    assert email.preview == "This is a test email snippet"
    assert email.user_id == gmail_account.user.id
    assert isinstance(email.received_at, datetime)

    # Verify the thread was created and metadata set
    assert thread is not None
    assert thread.external_thread_id == "thread_789"
    await thread.fetch_related("messages")
    assert EmailLabel.INBOX in thread.labels
    assert EmailLabel.UNREAD in thread.labels
    sender_emails = [address.email for address in thread.sender_addresses_unique]
    assert len(sender_emails) == 1
    assert "john@example.com" in sender_emails


@pytest.mark.asyncio
async def test_create_email_record_multipart():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    message_data: GmailMessage = {
        "id": "msg_multipart",
        "threadId": "thread_multi",
        "historyId": "111",
        "labelIds": [GmailLabel.INBOX],
        "snippet": "Multipart email",
    }

    headers = EmailHeaders(
        [
            {"name": "subject", "value": "Multipart Test"},
            {"name": "from", "value": "sender@example.com"},
            {"name": "to", "value": "recipient@example.com"},
            {"name": "date", "value": "Wed, 25 Dec 2024 10:15:30 +0000"},
        ]
    )

    new_message_result = await loader.create_email_record(
        message_data, headers, "Plain text version", "<p>HTML version</p>"
    )
    email = new_message_result.email

    # Verify the email was created correctly
    assert email.body_plain == "Plain text version"
    assert email.body_html == "<p>HTML version</p>"


@pytest.mark.asyncio
async def test_create_email_record_with_recipients():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    message_data: GmailMessage = {
        "id": "msg_recipients",
        "threadId": "thread_recipients",
        "historyId": "222",
        "labelIds": [GmailLabel.INBOX],
        "snippet": "Email with multiple recipients",
    }

    headers = EmailHeaders(
        [
            {"name": "subject", "value": "Multiple Recipients"},
            {"name": "from", "value": "sender@example.com"},
            {"name": "to", "value": "user1@example.com, user2@example.com"},
            {"name": "cc", "value": "cc1@example.com, cc2@example.com"},
            {"name": "date", "value": "Wed, 25 Dec 2024 10:15:30 +0000"},
        ]
    )

    new_message_result = await loader.create_email_record(message_data, headers, "Test content", None)
    email = new_message_result.email

    assert email.to == ["user1@example.com", "user2@example.com"]
    assert email.cc == ["cc1@example.com", "cc2@example.com"]


@pytest.mark.asyncio
async def test_create_email_record_with_trash_label():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    message_data: GmailMessage = {
        "id": "msg_trash",
        "threadId": "thread_trash",
        "historyId": "456",
        "labelIds": [GmailLabel.INBOX, "TRASH", GmailLabel.UNREAD],
        "snippet": "This email should be soft deleted",
    }

    headers = EmailHeaders(
        [
            {"name": "subject", "value": "Trash Test"},
            {"name": "from", "value": "sender@example.com"},
            {"name": "to", "value": "recipient@example.com"},
            {"name": "date", "value": "Wed, 25 Dec 2024 10:15:30 +0000"},
        ]
    )

    new_message_result = await loader.create_email_record(message_data, headers, "This should be deleted", None)
    thread = new_message_result.thread
    email = new_message_result.email

    # Verify the email was created but soft deleted
    assert email.external_message_id == "msg_trash"
    assert email.subject == "Trash Test"
    assert email.deleted_at is not None  # Should be soft deleted

    assert thread is not None
    assert thread.is_deleted


@pytest.mark.asyncio
async def test_create_onboarding_sync_email_records_batch():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    # Test data for multiple messages in the same thread
    message1: GmailMessage = {
        "id": "msg_backfill_123",
        "threadId": "thread_backfill_789",
        "historyId": "67890",
        "labelIds": [GmailLabel.UNREAD, GmailLabel.INBOX, GmailLabel.UNREAD],
        "snippet": "This is a backfill email snippet",
    }
    message2: GmailMessage = {
        "id": "msg_backfill_456",
        "threadId": "thread_backfill_789",
        "historyId": "67891",
        "labelIds": [GmailLabel.SENT, GmailLabel.INBOX, GmailLabel.SENT],
        "snippet": "This is a second backfill email",
    }

    messages_data: list[tuple[GmailMessage, EmailHeaders, str | None, str | None]] = [
        (
            message1,
            EmailHeaders(
                [
                    {"name": "subject", "value": "Backfill Test Email"},
                    {"name": "from", "value": "John Doe <john@example.com>"},
                    {"name": "to", "value": "jane@example.com"},
                    {"name": "date", "value": "Wed, 25 Dec 2024 10:15:30 +0000"},
                    {"name": "message-id", "value": "<backfill123@example.com>"},
                ]
            ),
            "Hello backfill world!",
            None,
        ),
        (
            message2,
            EmailHeaders(
                [
                    {"name": "subject", "value": "Re: Backfill Test Email"},
                    {"name": "from", "value": "Jane Smith <jane@example.com>"},
                    {"name": "to", "value": "john@example.com"},
                    {"name": "date", "value": "Wed, 25 Dec 2024 11:15:30 +0000"},
                    {"name": "message-id", "value": "<backfill456@example.com>"},
                ]
            ),
            "Hello back!",
            "<p>Hello back!</p>",
        ),
    ]

    await loader.create_onboarding_sync_email_records_batch(messages_data)

    # Verify emails were created (batch method returns empty list)
    emails = await EmailMessage.filter(external_thread_id="thread_backfill_789").all()
    assert len(emails) == 2

    # Verify first email
    email1 = next((e for e in emails if e.external_message_id == "msg_backfill_123"), None)
    assert email1 is not None
    assert email1.external_thread_id == "thread_backfill_789"
    assert email1.external_history_id == "67890"
    assert email1.subject == "Backfill Test Email"
    assert email1.sender == "John Doe <john@example.com>"
    assert email1.to == ["jane@example.com"]
    assert email1.body_plain == "Hello backfill world!"
    assert email1.preview == "This is a backfill email snippet"
    assert email1.user_id == gmail_account.user.id
    assert isinstance(email1.received_at, datetime)
    assert email1.labels == [EmailLabel.INBOX, EmailLabel.UNREAD]

    # Verify second email
    email2 = next((e for e in emails if e.external_message_id == "msg_backfill_456"), None)
    assert email2 is not None
    assert email2.external_thread_id == "thread_backfill_789"
    assert email2.subject == "Re: Backfill Test Email"
    assert email2.sender == "Jane Smith <jane@example.com>"
    assert email2.body_html == "<p>Hello back!</p>"
    assert email2.labels == [EmailLabel.INBOX, EmailLabel.SENT]

    # Verify the thread was created
    thread = await EmailThread.get(external_thread_id="thread_backfill_789")
    assert thread is not None
    assert thread.external_thread_id == "thread_backfill_789"


@pytest.mark.asyncio
async def test_create_onboarding_sync_email_records_batch_empty():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    # Test with empty list
    await loader.create_onboarding_sync_email_records_batch([])
    emails = await EmailMessage.all()
    assert len(emails) == 0


@pytest.mark.asyncio
async def test_duplicate_email_prevention():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    message_data: GmailMessage = {
        "id": "msg_trash",
        "threadId": "thread_trash",
        "historyId": "456",
        "labelIds": [GmailLabel.INBOX, "TRASH", GmailLabel.UNREAD],
        "snippet": "This email should be soft deleted",
    }

    headers = EmailHeaders(
        [
            {"name": "subject", "value": "Trash Test"},
            {"name": "from", "value": "sender@example.com"},
            {"name": "to", "value": "recipient@example.com"},
            {"name": "date", "value": "Wed, 25 Dec 2024 10:15:30 +0000"},
        ]
    )

    await loader.create_email_record(message_data, headers, "This should be deleted", None)

    # Attempt to create the same email again
    await loader.create_email_record(message_data, headers, "This should be deleted again", None)

    messages = await EmailMessage.all()
    assert len(messages) == 1


@pytest.mark.asyncio
async def test_onboarding_sync_completion_sends_email(background_jobs: InlineJobs, email_delivery: FakeDelivery):
    email_delivery.reset()
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user

    # Use JobsOutbox to capture jobs enqueued during the completion
    async with JobsOutbox():
        job = OnboardingMailboxSyncGmailJob(user_id=user.id)
        await job._complete_onboarding_mailbox_sync(gmail_account, "test completion")

    # Verify the email job was enqueued and executed
    assert background_jobs.has_completed_job(SendOnboardingMailboxSyncCompletedEmailJob)

    # Verify the email was actually sent
    assert len(email_delivery.messages) == 1
    message = email_delivery.messages[0]
    assert message.to == user.email
    assert "email is ready" in message.subject


@pytest.mark.asyncio
async def test_gmail_history_sync_lock():
    """Test that the Gmail history sync lock works correctly."""
    gmail_account = await create_gmail_account()

    # Initially, no lock should be set
    assert gmail_account.history_sync_locked_at is None

    # First acquire should succeed
    assert await gmail_account.acquire_history_sync_lock() is True
    assert gmail_account.history_sync_locked_at is not None

    # Second acquire should fail while lock is held and not stale
    assert await gmail_account.acquire_history_sync_lock() is False

    # Release the lock
    await gmail_account.release_history_sync_lock()
    assert gmail_account.history_sync_locked_at is None

    # Should be able to acquire again after release (since lock is now None)
    assert await gmail_account.acquire_history_sync_lock() is True

    with freeze_time() as frozen_time:
        # Immediately try to acquire again - should fail
        assert await gmail_account.acquire_history_sync_lock() is False

        # Advance time past staleness threshold (600 seconds).
        # Lock becomes stale when current_time > locked_at + stale_seconds.
        # Lock was set at T=0 with locked_at=T, so it becomes stale at T > 0 + 600 = 600 seconds.
        frozen_time.tick(delta=timedelta(seconds=601))

        # Should be able to acquire after becoming stale
        assert await gmail_account.acquire_history_sync_lock() is True


@pytest.mark.asyncio
async def test_process_attachments_inline_referenced_in_html():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")

    # Load the fixture email
    fixture_path = Path("tests/fixtures/email_threads/inline_image_in_html_body.json")
    with fixture_path.open("r", encoding="utf-8") as f:
        thread_data = json.load(f)

    # Load the message through the mock Gmail API state
    gmail_state = MockGmailAPIStateRegistry.get_state()
    gmail_state.set_profile(gmail_account)
    gmail_state.load_threads_from_directory(fixture_path.parent, gmail_account.email)

    # Get the message from the seed data
    message = thread_data["messages"][0]
    gmail_client = await MockGoogleAPIClient.create(gmail_account.user, gmail_account)

    # Extract message content
    extractor = GmailMessageExtractor()
    payload = message.get("payload", {})
    headers = EmailHeaders(payload.get("headers", []))
    body_plain, body_html = extractor.extract_email_body(payload)
    attachments_data = extractor.find_attachments(payload)

    # Create the email record
    loader = GmailMessageLoader(gmail_account)
    new_message_result = await loader.create_email_record(message, headers, body_plain, body_html)
    email = new_message_result.email

    # Process attachments
    await loader.process_attachments(gmail_client, email, attachments_data)

    # Verify the attachment was created and correctly marked
    attachments = await EmailAttachment.filter(email_message_id=email.id).all()
    assert len(attachments) == 1

    attachment = attachments[0]
    await attachment.fetch_related("file")
    assert attachment.file.content_type == "image/jpeg"
    assert attachment.is_inline is True
    assert attachment.is_referenced_in_html is True


@pytest.mark.asyncio
async def test_create_email_record_decodes_html_entities():
    """Gmail returns HTML-encoded entities in both the subject header and the
    snippet (preview). Both must be decoded before persisting."""
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    loader = GmailMessageLoader(gmail_account)

    message_data: GmailMessage = {
        "id": "msg_html_entity",
        "threadId": "thread_html_entity",
        "historyId": "12345",
        "labelIds": [GmailLabel.INBOX],
        "snippet": "Don&#39;t miss the AT&amp;T update &mdash; details inside",
    }

    headers = EmailHeaders(
        [
            {"name": "subject", "value": "Microsoft Research on &#39;Infinite Workday&#39;"},
            {"name": "from", "value": "sender@example.com"},
            {"name": "to", "value": "receiver@example.com"},
            {"name": "date", "value": "Wed, 25 Dec 2024 10:15:30 +0000"},
            {"name": "message-id", "value": "<msghtml@example.com>"},
        ]
    )

    new_message_result = await loader.create_email_record(message_data, headers, "Test body", None)
    email = new_message_result.email
    thread = new_message_result.thread

    assert email.subject == "Microsoft Research on 'Infinite Workday'"
    assert thread.title == "Microsoft Research on 'Infinite Workday'"
    assert email.preview == "Don't miss the AT&T update — details inside"
    assert "&#39;" not in email.preview
    assert "&amp;" not in email.preview


@pytest.mark.asyncio
async def test_find_thread_id_for_rfc822_message_id(gmail_state: MockGmailAPIState):
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    gmail_state.set_profile(gmail_account)

    rfc822_message_id = "<CAPV8UpXQxxiPfpvw_RT96zzqwHAiVFBocZdxJKfaf2jzw1b=wg@mail.gmail.com>"
    gmail_state.add_message(
        message_id="msg_1",
        thread_id="thread_abc123",
        email=gmail_account.email,
        headers={"Message-Id": rfc822_message_id},
    )

    client = await MockGoogleAPIClient.create(gmail_account.user, gmail_account)

    assert await client.find_thread_id_for_rfc822_message_id(rfc822_message_id) == "thread_abc123"
    assert await client.find_thread_id_for_rfc822_message_id("<not-in-mailbox@example.com>") is None
