import pytest

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.workspaces.email.thread import EmailThread
from config.enums import EmailLabel, EmailMailboxLabel, EmailMessageType, MailboxLabel
from integrations.google.enums import GmailLabel
from integrations.google.jobs.gmail import (
    GmailMessageDeletedProcessor,
    GmailMessageStateProcessor,
    RestoreGmailInboxLabelJob,
    SendEmailThroughGmailJob,
)
from tests.helpers.factories import (
    create_collaborator,
    create_email_message,
    create_gmail_account,
    create_mailbox_entry,
    create_user,
)
from tests.integration.integrations.google.conftest import add_gmail_token_to_user


@pytest.mark.asyncio
async def test_thread_deleted_when_all_messages_deleted():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")

    # Create first message (and thread)
    email_1 = await create_email_message(
        external_message_id="msg_draft_123",
        external_thread_id="thread_draft_456",
        subject="Draft Message",
        sender="user@example.com",
        to=["recipient@example.com"],
        body_plain="First draft content",
        organization_id=gmail_account.user.organization_id,
        user_id=gmail_account.user.id,
    )
    await email_1.fetch_related("thread")
    thread = email_1.thread

    # Create second message in the same thread
    email_2 = await create_email_message(
        external_message_id="msg_draft_456",
        external_thread_id="thread_draft_456",
        subject="Re: Draft Message",
        sender="user@example.com",
        to=["recipient@example.com"],
        body_plain="Second draft content",
        organization_id=gmail_account.user.organization_id,
        user_id=gmail_account.user.id,
    )

    # Verify both messages and thread were created
    assert email_1.external_message_id == "msg_draft_123"
    assert not email_1.is_deleted
    assert email_2.external_message_id == "msg_draft_456"
    assert not email_2.is_deleted
    assert thread.external_thread_id == "thread_draft_456"
    assert not thread.is_deleted

    # Delete the first message using the processor - thread should still exist
    await GmailMessageDeletedProcessor(
        gmail_account_id=gmail_account.id, external_message_id="msg_draft_123"
    ).perform()

    # Verify first message is deleted but thread and second message are not
    await email_1.refresh_from_db()
    await email_2.refresh_from_db()
    await thread.refresh_from_db()
    assert email_1.is_deleted
    assert not email_2.is_deleted
    assert not thread.is_deleted

    # Now delete the second message using the processor - thread should be deleted too
    await GmailMessageDeletedProcessor(
        gmail_account_id=gmail_account.id, external_message_id="msg_draft_456"
    ).perform()

    # Verify all messages and thread are now soft-deleted
    await email_1.refresh_from_db()
    await email_2.refresh_from_db()
    await thread.refresh_from_db()
    assert email_1.is_deleted
    assert email_2.is_deleted
    assert thread.is_deleted


@pytest.mark.asyncio
async def test_gmail_processors_trigger_mailbox_entry_sync():
    gmail_user = await create_user()
    collaborator = await create_user(organization_id=gmail_user.organization_id)

    gmail_account = await create_gmail_account(user_id=gmail_user.id, email=gmail_user.email)
    await gmail_account.fetch_related("user")

    # Create an email thread with workspace collaborators
    email_message = await create_email_message(
        external_message_id="gmail_sync_msg",
        external_thread_id="gmail_sync_thread",
        subject="Gmail Sync Test",
        sender="sender@example.com",
        to=["recipient@example.com"],
        body_plain="Gmail sync test content",
        organization_id=gmail_user.organization_id,
        user_id=gmail_user.id,
    )
    await email_message.fetch_related("thread__workspace")
    thread = email_message.thread

    # Add collaborator to workspace
    await create_collaborator(workspace_id=thread.workspace_id, user_id=collaborator.id)

    # Verify no MailboxEntry records exist initially
    mailbox_entry_count = await MailboxEntry.filter(resource_gid=str(thread.global_id)).count()
    assert mailbox_entry_count == 0

    # Test that Gmail processors trigger a mailbox sync
    # Create and add a new message (simulating Gmail message added webhook)
    await thread.receive_message(
        {
            "external_message_id": "gmail_new_msg",
            "external_thread_id": "gmail_sync_thread",
            "subject": "Re: Gmail Sync Test",
            "sender": "reply@example.com",
            "to": ["recipient@example.com"],
            "body_plain": "Gmail reply content",
            "user_id": gmail_user.id,
            "organization_id": gmail_user.organization_id,
            "message_type": EmailMessageType.RECEIVED,
            "labels": [EmailLabel.INBOX],
        }
    )

    # Call the Gmail processor sync logic directly (this is what gets called in perform())
    await Mailbox.sync(thread)

    # Verify mailbox records were created for both users
    mailbox_entries = await MailboxEntry.filter(resource_gid=str(thread.global_id))
    assert len(mailbox_entries) == 2  # gmail_user and collaborator

    # Verify basic sync worked - this is lightweight verification, detailed sync testing is in the model test
    owner_ids = {entry.owner_id for entry in mailbox_entries}
    assert owner_ids == {gmail_user.id, collaborator.id}

    for entry in mailbox_entries:
        assert entry.resource_gid == thread.global_id
        assert entry.title == thread.title
        assert MailboxLabel.INBOX in entry.labels


@pytest.mark.asyncio
async def test_send_email_job_retry_syncs_mailbox_draft_label():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user

    # Create a message that is already in SENT state (simulating a retry where the first attempt succeeded)
    email_message = await create_email_message(
        external_message_id="sent_msg_retry_001",
        external_thread_id="sent_thread_retry_001",
        subject="Already Sent Message",
        sender=user.email,
        to=["recipient@example.com"],
        body_plain="This was already sent",
        organization_id=user.organization_id,
        user_id=user.id,
    )
    await email_message.fetch_related("thread")
    thread = email_message.thread

    # Update the message to SENT state (factory creates as RECEIVED by default)
    email_message.message_type = EmailMessageType.SENT
    email_message.labels = [EmailLabel.SENT]
    await email_message.save(update_fields=["message_type", "labels"])
    assert email_message.sent_from_convictional_at is None
    await thread.update_metadata_from_messages()

    # Initial Mailbox.sync creates MailboxEntry without DRAFT
    await Mailbox.sync(thread)
    entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=user.id)
    assert EmailMailboxLabel.DRAFT not in entry.labels

    # Simulate stale MailboxEntry that still has DRAFT label
    entry.labels.append(EmailMailboxLabel.DRAFT)
    await entry.save(update_fields=["labels"])
    await entry.refresh_from_db()
    assert EmailMailboxLabel.DRAFT in entry.labels

    # Run the job on retry — draft is already SENT so get_draft returns None
    await SendEmailThroughGmailJob(email_thread_id=thread.id).perform()

    # The stale DRAFT label should be cleaned up by Mailbox.sync
    await entry.refresh_from_db()
    assert EmailMailboxLabel.DRAFT not in entry.labels


@pytest.mark.asyncio
async def test_gmail_state_processor_does_not_readd_draft_label_on_sent_message(gmail_state):
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user

    # Create a message in SENT state
    email_message = await create_email_message(
        external_message_id="sent_ext_msg_001",
        external_thread_id="sent_ext_thread_001",
        subject="Sent Message",
        sender=user.email,
        to=["recipient@example.com"],
        body_plain="This message has been sent",
        organization_id=user.organization_id,
        user_id=user.id,
    )
    await email_message.fetch_related("thread")
    thread = email_message.thread

    # Update to SENT state
    email_message.message_type = EmailMessageType.SENT
    email_message.labels = [EmailLabel.SENT]
    await email_message.save(update_fields=["message_type", "labels"])
    await thread.update_metadata_from_messages()

    # Sync mailbox — MailboxEntry should not have DRAFT
    await Mailbox.sync(thread)
    entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=user.id)
    assert EmailMailboxLabel.DRAFT not in entry.labels

    # Gmail API returns stale DRAFT label for this sent message (race condition)
    gmail_state.add_message(
        "sent_ext_msg_001",
        "sent_ext_thread_001",
        email=gmail_account.email,
        labels=["DRAFT"],
    )

    # Run the state processor — it fetches the stale Gmail response
    await GmailMessageStateProcessor(
        gmail_account_id=gmail_account.id, external_message_id="sent_ext_msg_001"
    ).perform()

    # DRAFT should not be re-applied to the MailboxEntry
    await entry.refresh_from_db()
    assert EmailMailboxLabel.DRAFT not in entry.labels


@pytest.mark.asyncio
async def test_gmail_state_processor_does_not_apply_draft_label_on_sending_message(gmail_state):
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user

    # Create a message in SENDING state (send job is in progress)
    email_message = await create_email_message(
        external_message_id="sending_ext_msg_001",
        external_thread_id="sending_ext_thread_001",
        subject="Sending Message",
        sender=user.email,
        to=["recipient@example.com"],
        body_plain="This message is being sent",
        organization_id=user.organization_id,
        user_id=user.id,
    )
    await email_message.fetch_related("thread")
    thread = email_message.thread

    # Transition to SENDING state (HTTP handler sets this before enqueuing the send job)
    email_message.message_type = EmailMessageType.SENDING
    email_message.labels = [EmailLabel.DRAFT]
    await email_message.save(update_fields=["message_type", "labels"])
    await thread.update_metadata_from_messages()

    # Sync mailbox — thread is still draft during SENDING window
    await Mailbox.sync(thread)
    entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=user.id)
    assert EmailMailboxLabel.DRAFT in entry.labels

    # Send job completes: mark message as SENT and clear DRAFT from MailboxEntry
    email_message.message_type = EmailMessageType.SENT
    email_message.labels = [EmailLabel.SENT]
    await email_message.save(update_fields=["message_type", "labels"])
    await thread.update_metadata_from_messages()
    await Mailbox.sync(thread)
    await entry.refresh_from_db()
    assert EmailMailboxLabel.DRAFT not in entry.labels

    # Gmail API returns stale DRAFT label (history sync fires after the send completed)
    gmail_state.add_message(
        "sending_ext_msg_001",
        "sending_ext_thread_001",
        email=gmail_account.email,
        labels=["DRAFT"],
    )

    # Run the state processor — it fetches the stale Gmail response
    await GmailMessageStateProcessor(
        gmail_account_id=gmail_account.id, external_message_id="sending_ext_msg_001"
    ).perform()

    # DRAFT should not be re-applied to the MailboxEntry
    await entry.refresh_from_db()
    assert EmailMailboxLabel.DRAFT not in entry.labels


@pytest.mark.asyncio
async def test_gmail_state_processor_scopes_lookup_to_user(gmail_state):
    # Gmail's per-mailbox message IDs aren't globally unique. Two users can each
    # have an EmailMessage with the same external_message_id (the table's
    # unique_together is (external_message_id, user_id)). The state processor
    # must scope the lookup to its own user — otherwise the unscoped query
    # returns multiple rows and raises MultipleObjectsReturned.
    shared_external_message_id = "shared_gmail_msg_id"

    user_a_gmail_account = await create_gmail_account()
    await user_a_gmail_account.fetch_related("user")
    user_a = user_a_gmail_account.user

    email_a = await create_email_message(
        external_message_id=shared_external_message_id,
        external_thread_id="thread_user_a",
        organization_id=user_a.organization_id,
        user_id=user_a.id,
        labels=[EmailLabel.INBOX],
    )

    user_b = await create_user()
    email_b = await create_email_message(
        external_message_id=shared_external_message_id,
        external_thread_id="thread_user_b",
        organization_id=user_b.organization_id,
        user_id=user_b.id,
        labels=[EmailLabel.INBOX],
    )

    # Gmail returns UNREAD (no INBOX) for user A's message, so the processor
    # exercises the full save + thread metadata + Mailbox.sync path.
    gmail_state.add_message(
        shared_external_message_id,
        "thread_user_a",
        email=user_a_gmail_account.email,
        labels=["UNREAD"],
    )

    await GmailMessageStateProcessor(
        gmail_account_id=user_a_gmail_account.id,
        external_message_id=shared_external_message_id,
    ).perform()

    await email_a.refresh_from_db()
    await email_b.refresh_from_db()

    assert email_a.labels == [EmailLabel.UNREAD]
    assert email_b.labels == [EmailLabel.INBOX]


#
# Snoozing
#
#


@pytest.mark.asyncio
async def test_restore_gmail_inbox_label_job_mirrors_thread_to_gmail(gmail_state):
    # The generic UnsnoozeMailboxEntryJob (app/jobs/mailbox.py) handles our own inbox
    # state for every resource type; this Gmail-only job restores the thread to the
    # original recipient's Gmail inbox and is enqueued alongside it for EmailThread entries.
    user = await create_user()
    await create_gmail_account(user_id=user.id, email=user.email)
    await add_gmail_token_to_user(user)

    message = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="ext-thread-unsnooze",
    )
    thread = await EmailThread.get(id=message.thread_id)
    assert thread.is_original_recipient(user.id)
    entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=thread.global_id,
    )
    # modify_thread raises if the thread isn't already known to the mock Gmail client.
    gmail_state.add_thread(thread.external_thread_id)

    await RestoreGmailInboxLabelJob(mailbox_entry_id=entry.id).perform()

    assert gmail_state.threads[thread.external_thread_id]["addLabelIds"] == [GmailLabel.INBOX]
