from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import MagicMock

import pytest
from freezegun import freeze_time

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.workspaces.email.thread import EmailThread
from config.enums import EmailLabel, EmailMessageType, Integration
from infra.jobs import JobsOutbox
from integrations.google.constants import (
    GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_TIMEOUT_SECONDS,
    GMAIL_WATCH_LIVENESS_THRESHOLD_SECONDS,
)
from integrations.google.gmail import GoogleAPIClient, MockGmailAPIState
from integrations.google.jobs.gmail import GmailHealthCheckJob, ProcessGmailHistoryJob
from integrations.google.models import GmailAccount
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_message, create_gmail_account, create_user
from tests.integration.integrations.google.conftest import add_gmail_token_to_user


@pytest.mark.asyncio
async def test_process_history_job_new_message(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="2000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    gmail_state.add_message(
        "msg_inbox_1",
        "thread_1",
        email=gmail_account.email,
        labels=["INBOX", "UNREAD"],
        headers={
            "Subject": "Important Meeting",
            "From": "boss@company.com",
            "To": user.email,
        },
        body_plain="Please review the quarterly reports before tomorrow's meeting.",
    )
    next_history_id = gmail_state.get_last_pending_history_id_for_account(
        gmail_account.email, gmail_account.history_id
    )

    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=next_history_id)
        await job.perform()

    # Verify the message was processed and stored with a thread
    thread = await EmailThread.filter(creator_id=user.id).first().prefetch_related("messages")
    assert thread is not None
    assert thread.title == "Important Meeting"
    assert len(thread.messages) == 1
    message = thread.messages[0]
    assert message.subject == "Important Meeting"
    assert message.body_plain == "Please review the quarterly reports before tomorrow's meeting."

    # Verify there is a MailboxEntry
    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    assert mailbox_entry.is_inbox
    assert mailbox_entry.is_unread


@pytest.mark.asyncio
async def test_process_history_job_label_changes(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="0", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        subject="Test Email Thread",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        external_message_id="msg_1",
        external_thread_id="thread_1",
        email=gmail_account.email,
    )
    gmail_state.add_message(
        "msg_1",
        "thread_1",
        email=gmail_account.email,
        labels=["INBOX", "UNREAD"],
        headers={
            "Subject": "Test Email Thread",
            "From": "someguy@emails.com",
            "To": user.email,
        },
        body_plain="This is a test email.",
    )
    # Increment history ID because we have already created the message and don't need to process the messageAdded
    # history event that we get from gmail_state.add_message
    gmail_account.history_id = "1"
    await gmail_account.save()

    # Create the MailboxEntry the way production does: when mail first arrives,
    # GmailMessageAddedProcessor calls `Mailbox.sync(thread)`, which seeds the entry
    # WITH INBOX. The factory above does not create an entry, so without this the
    # entry would be born only after the archive and never carry INBOX — masking the bug.
    thread = await EmailThread.filter(creator_id=user.id).first()
    assert thread is not None
    await Mailbox.sync(thread)

    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    assert mailbox_entry.is_inbox

    # Mark as read by removing UNREAD
    gmail_state.update_labels(email=gmail_account.email, message_id="msg_1", labels_to_remove=["UNREAD"])
    # Archive by removing INBOX
    gmail_state.update_labels(email=gmail_account.email, message_id="msg_1", labels_to_remove=["INBOX"])

    history_id = gmail_state.get_last_pending_history_id_for_account(gmail_account.email, gmail_account.history_id)
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=history_id)
        await job.perform()

    thread = await EmailThread.filter(creator_id=user.id).first().prefetch_related("messages")
    assert thread is not None
    message = thread.messages[0]
    assert message is not None
    assert message.is_read
    assert message.is_archived
    assert EmailLabel.UNREAD not in message.labels
    assert thread.is_read
    assert thread.is_archived

    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    assert mailbox_entry.is_archived
    assert mailbox_entry.is_read


@pytest.mark.asyncio
async def test_process_history_job_multi_message_thread_archive(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="0", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    for message_id, sender in (("msg_1", "someguy@emails.com"), ("msg_2", "someguy@emails.com")):
        await create_email_message(
            creator_id=user.id,
            organization_id=user.organization_id,
            subject="Multi Message Thread",
            labels=[EmailLabel.INBOX],
            external_message_id=message_id,
            external_thread_id="thread_1",
            email=gmail_account.email,
        )
        gmail_state.add_message(
            message_id,
            "thread_1",
            email=gmail_account.email,
            labels=["INBOX"],
            headers={
                "Subject": "Multi Message Thread",
                "From": sender,
                "To": user.email,
            },
            body_plain="This is a multi-message thread.",
        )
    # Skip the messageAdded events for the messages we already created.
    gmail_account.history_id = "2"
    await gmail_account.save()

    # Seed the entry the production way (with INBOX) before the archive arrives.
    thread = await EmailThread.filter(creator_id=user.id).first()
    assert thread is not None
    await Mailbox.sync(thread)
    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    assert mailbox_entry.is_inbox

    gmail_state.update_labels(email=gmail_account.email, message_id="msg_1", labels_to_remove=["INBOX"])
    gmail_state.update_labels(email=gmail_account.email, message_id="msg_2", labels_to_remove=["INBOX"])

    history_id = gmail_state.get_last_pending_history_id_for_account(gmail_account.email, gmail_account.history_id)
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=history_id)
        await job.perform()

    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    # Two per-message INBOX removals archive the single entry exactly once (idempotent).
    assert mailbox_entry.is_archived


@pytest.mark.asyncio
async def test_process_history_job_partial_inbox_removal_keeps_thread(
    client: AppClient, gmail_state: MockGmailAPIState
):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="0", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    for message_id in ("msg_1", "msg_2"):
        await create_email_message(
            creator_id=user.id,
            organization_id=user.organization_id,
            subject="Partial Inbox Thread",
            labels=[EmailLabel.INBOX],
            external_message_id=message_id,
            external_thread_id="thread_1",
            email=gmail_account.email,
        )
        gmail_state.add_message(
            message_id,
            "thread_1",
            email=gmail_account.email,
            labels=["INBOX"],
            headers={
                "Subject": "Partial Inbox Thread",
                "From": "someguy@emails.com",
                "To": user.email,
            },
            body_plain="This is a multi-message thread.",
        )
    gmail_account.history_id = "2"
    await gmail_account.save()

    thread = await EmailThread.filter(creator_id=user.id).first()
    assert thread is not None
    await Mailbox.sync(thread)
    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    assert mailbox_entry.is_inbox

    # Only one message loses INBOX; the sibling keeps it, so the Gmail thread is still in the
    # inbox. The Convictional entry must stay in the inbox — archiving here would over-archive.
    gmail_state.update_labels(email=gmail_account.email, message_id="msg_1", labels_to_remove=["INBOX"])

    history_id = gmail_state.get_last_pending_history_id_for_account(gmail_account.email, gmail_account.history_id)
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=history_id)
        await job.perform()

    thread = await EmailThread.filter(creator_id=user.id).first()
    assert thread is not None
    assert thread.is_inbox

    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    assert mailbox_entry.is_inbox


@pytest.mark.asyncio
async def test_process_history_job_archive_isolated_to_owner(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="0", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    collaborator = await create_user(organization_id=user.organization_id)

    await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        subject="Shared Thread",
        labels=[EmailLabel.INBOX],
        external_message_id="msg_1",
        external_thread_id="thread_1",
        email=gmail_account.email,
    )
    gmail_state.add_message(
        "msg_1",
        "thread_1",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={
            "Subject": "Shared Thread",
            "From": "someguy@emails.com",
            "To": user.email,
        },
        body_plain="This is a shared thread.",
    )
    gmail_account.history_id = "1"
    await gmail_account.save()

    # Seed both users' entries with INBOX (as production does) before the owner archives.
    thread = await EmailThread.filter(creator_id=user.id).first()
    assert thread is not None
    await thread.fetch_related("workspace")
    await thread.collaboration.add(collaborator, user)
    await Mailbox.sync(thread)

    owner_entry = await Mailbox(user).entry(thread).get_or_none()
    collaborator_entry = await Mailbox(collaborator).entry(thread).get_or_none()
    assert owner_entry is not None and owner_entry.is_inbox
    assert collaborator_entry is not None and collaborator_entry.is_inbox

    gmail_state.update_labels(email=gmail_account.email, message_id="msg_1", labels_to_remove=["INBOX"])

    history_id = gmail_state.get_last_pending_history_id_for_account(gmail_account.email, gmail_account.history_id)
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=history_id)
        await job.perform()

    owner_entry = await Mailbox(user).entry(thread).get_or_none()
    collaborator_entry = await Mailbox(collaborator).entry(thread).get_or_none()
    # The owner's Gmail archive is scoped to their mailbox; the collaborator's entry is untouched.
    assert owner_entry is not None and owner_entry.is_archived
    assert collaborator_entry is not None and collaborator_entry.is_inbox


@pytest.mark.asyncio
async def test_process_history_id_comparison(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    # Start with history_id="9"
    gmail_account = await create_gmail_account(history_id="9", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # Add a message which will generate history_id="10", which is greater than "9"
    gmail_state.add_message(
        "msg_inbox_1",
        "thread_1",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={
            "Subject": "Test Message",
            "From": "sender@example.com",
            "To": user.email,
        },
        body_plain="Test body",
    )
    next_history_id = gmail_state.get_last_pending_history_id_for_account(
        gmail_account.email, gmail_account.history_id
    )
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=next_history_id)
        await job.perform()

    # Verify the message was processed and stored with a thread
    thread = await EmailThread.filter(creator_id=user.id).first()
    assert thread is not None, "Message should have been processed, not skipped"
    assert thread.title == "Test Message"

    # Verify history_id was updated to the new value
    await gmail_account.refresh_from_db()
    assert gmail_account.history_id == next_history_id


@pytest.mark.asyncio
async def test_process_history_job_deleted_message(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="0", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        subject="Test Email Thread",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        external_message_id="msg_1",
        external_thread_id="thread_1",
        email=gmail_account.email,
    )
    gmail_state.add_message(
        "msg_1",
        "thread_1",
        email=gmail_account.email,
        labels=["INBOX", "UNREAD"],
        headers={
            "Subject": "Test Email Thread",
            "From": "bob@clams.net",
            "To": user.email,
        },
        body_plain="This is a test email.",
    )
    # Increment history ID because we have already created the message and don't need to process the message
    # Added history event that we get from gmail_state.add_message
    gmail_account.history_id = "1"
    await gmail_account.save()

    # Delete the message
    gmail_state.delete_message(email=gmail_account.email, message_id="msg_1")
    history_id = gmail_state.get_last_pending_history_id_for_account(gmail_account.email, gmail_account.history_id)
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=history_id)
        await job.perform()

    thread = cast(
        EmailThread | None,
        await EmailThread.unscoped.get_queryset().filter(creator_id=user.id).first().prefetch_related("messages"),
    )
    assert thread is not None
    assert thread.is_deleted
    assert len(thread.messages) == 0


@pytest.mark.asyncio
async def test_process_history_job_trash_does_not_archive(client: AppClient, gmail_state: MockGmailAPIState):
    """Trashing a message emits labelsRemoved(INBOX) + labelsAdded(TRASH), not messagesDeleted.

    Trashing must never archive:
    - a single-message thread that is trashed gets soft-deleted (not archived), and the job
      must complete the rest of the history batch instead of aborting on the archive lookup; and
    - trashing one message of a live multi-message thread must not archive the conversation.
    """
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="0", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # --- Scenario A: single-message thread trashed -> soft-deleted, not archived ---
    await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        subject="Trash Single Thread",
        labels=[EmailLabel.INBOX],
        external_message_id="trash_msg_1",
        external_thread_id="trash_thread_1",
        email=gmail_account.email,
    )
    gmail_state.add_message(
        "trash_msg_1",
        "trash_thread_1",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={
            "Subject": "Trash Single Thread",
            "From": "someguy@emails.com",
            "To": user.email,
        },
        body_plain="This message will be trashed.",
    )
    # Skip the messageAdded event for the message we already created.
    gmail_account.history_id = "1"
    await gmail_account.save()

    single_thread = await EmailThread.filter(creator_id=user.id, external_thread_id="trash_thread_1").first()
    assert single_thread is not None
    await Mailbox.sync(single_thread)
    single_entry = await MailboxEntry.get_or_none(resource_gid=str(single_thread.global_id))
    assert single_entry is not None
    assert single_entry.is_inbox

    # Trash in Gmail: remove INBOX and add TRASH in a single labels change.
    gmail_state.update_labels(
        email=gmail_account.email,
        message_id="trash_msg_1",
        labels_to_remove=["INBOX"],
        labels_to_add=["TRASH"],
    )

    history_id = gmail_state.get_last_pending_history_id_for_account(gmail_account.email, gmail_account.history_id)
    # The job completing without raising DoesNotExist proves the batch was not aborted.
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=history_id)
        await job.perform()

    trashed_thread = cast(
        EmailThread | None,
        await EmailThread.unscoped.get_queryset()
        .filter(creator_id=user.id, external_thread_id="trash_thread_1")
        .first(),
    )
    assert trashed_thread is not None
    assert trashed_thread.is_deleted

    # --- Scenario B: multi-message thread, ONE message trashed -> not archived ---
    gmail_account.history_id = str(gmail_state.history_counters[gmail_account.email])
    await gmail_account.save()

    for message_id, sender in (("multi_msg_1", "alice@emails.com"), ("multi_msg_2", "bob@emails.com")):
        await create_email_message(
            creator_id=user.id,
            organization_id=user.organization_id,
            subject="Trash Multi Thread",
            labels=[EmailLabel.INBOX],
            external_message_id=message_id,
            external_thread_id="trash_thread_2",
            email=gmail_account.email,
        )
        gmail_state.add_message(
            message_id,
            "trash_thread_2",
            email=gmail_account.email,
            labels=["INBOX"],
            headers={
                "Subject": "Trash Multi Thread",
                "From": sender,
                "To": user.email,
            },
            body_plain="This is a multi-message thread.",
        )
    # Skip the messageAdded events for the two messages we already created.
    gmail_account.history_id = str(gmail_state.history_counters[gmail_account.email])
    await gmail_account.save()

    multi_thread = await EmailThread.filter(creator_id=user.id, external_thread_id="trash_thread_2").first()
    assert multi_thread is not None
    await Mailbox.sync(multi_thread)
    multi_entry = await MailboxEntry.get_or_none(resource_gid=str(multi_thread.global_id))
    assert multi_entry is not None
    assert multi_entry.is_inbox

    # Trash only ONE message; the other keeps INBOX so the conversation stays live.
    gmail_state.update_labels(
        email=gmail_account.email,
        message_id="multi_msg_1",
        labels_to_remove=["INBOX"],
        labels_to_add=["TRASH"],
    )

    history_id = gmail_state.get_last_pending_history_id_for_account(gmail_account.email, gmail_account.history_id)
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=history_id)
        await job.perform()

    multi_entry = await MailboxEntry.get_or_none(resource_gid=str(multi_thread.global_id))
    assert multi_entry is not None
    assert multi_entry.is_inbox
    assert not multi_entry.is_archived


@pytest.mark.asyncio
async def test_history_checkpoint_equals_max_processed_record(client: AppClient, gmail_state: MockGmailAPIState):
    """The stored checkpoint is the MAX history record actually processed.

    When no record is lagging, every record up to Gmail's current historyId is returned, so the
    max processed record id equals the response historyId — the two coincide here, but it is the
    max-processed value (not the response historyId) that the checkpoint tracks.
    """
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="2000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # Message A: the one the webhook notification tells us about
    gmail_state.add_message(
        "msg_a",
        "thread_a",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={"Subject": "Message A", "From": "a@example.com", "To": user.email},
        body_plain="First message",
    )
    notification_history_id = gmail_state.get_last_pending_history_id_for_account(
        gmail_account.email, gmail_account.history_id
    )

    # Message B: arrives between notification dispatch and job execution
    gmail_state.add_message(
        "msg_b",
        "thread_b",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={"Subject": "Message B", "From": "b@example.com", "To": user.email},
        body_plain="Second message",
    )
    actual_current_history_id = str(gmail_state.history_counters[gmail_account.email])
    assert notification_history_id != actual_current_history_id

    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=notification_history_id)
        await job.perform()

    # Both messages should be processed
    threads = await EmailThread.filter(creator_id=user.id).all()
    assert len(threads) == 2

    # The stored history_id is the MAX history record actually processed. Because no record is
    # lagging here, that max equals the response historyId — so the checkpoint lands on the actual
    # current value and entries beyond the notification are not re-processed on the next sync.
    await gmail_account.refresh_from_db()
    assert gmail_account.history_id == actual_current_history_id


@pytest.mark.asyncio
async def test_health_check_converges_on_non_record_history_drift(client: AppClient, gmail_state: MockGmailAPIState):
    """A mailbox whose live historyId sits above its last processed record must not make the
    health check re-trigger a no-op sync on every cycle.

    Gmail's profile historyId routinely runs ahead of the last *record* returned by history.list
    (eventual-consistency drift, plus changes that aren't messageAdded/labelAdded/labelRemoved/
    messageDeleted). Since the checkpoint tracks the max processed record id, that gap never
    closes on its own: each health-check cycle sees stored < live, enqueues a ProcessGmailHistoryJob
    that finds zero records and leaves the checkpoint untouched, and the next cycle repeats. This
    test asserts the desired convergent behaviour — it fails on a branch that loops.
    """
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="3000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # Live mailbox pointer sits ahead of the checkpoint with NO history records in between
    # (pure non-record drift). This is the normal steady state, not a lagging-record anomaly.
    # simulate_history_lag advances the pointer list_history reports; the profile (what the health
    # check reads) must match it, since both reflect the one live historyId in real Gmail.
    gmail_state.simulate_history_lag(gmail_account.email, 3010)
    gmail_state.profiles[gmail_account.email]["historyId"] = "3010"

    async def run_health_check_cycle() -> list:
        async with JobsOutbox():
            await GmailHealthCheckJob(user_id=user.id).perform()
            syncs = [j for j in await JobsOutbox.get() if j.job_type == ProcessGmailHistoryJob.job_type()]
            await JobsOutbox.reset()
        return syncs

    # Cycle 1: stored (3000) < live (3010), so the health check enqueues a recovery sync.
    first_cycle = await run_health_check_cycle()
    assert len(first_cycle) == 1, "Health check should enqueue a sync the first time it sees a gap"

    # A worker picks up that sync and runs it to completion (Job marked SUCCESSFUL), exactly as
    # production would between two health-check cycles. The unique=True dedup only suppresses a
    # *pending* duplicate, so completing it here is what lets the next cycle re-enqueue.
    await first_cycle[0].run()

    # There are no records between 3000 and 3010, so the sync processed nothing and the resume cursor
    # stays at 3000 (it must keep trailing so a lagging record below 3010 is still re-scanned). The
    # caught-up marker, however, advances to the live historyId we just scanned through — that is what
    # lets the next cycle recognise the mailbox is caught up.
    await gmail_account.refresh_from_db()
    assert gmail_account.history_id == "3000"
    assert gmail_account.synced_history_id == "3010"

    # Cycle 2: the mailbox is genuinely caught up — there is nothing left to recover — so the
    # health check should converge and enqueue nothing.
    second_cycle = await run_health_check_cycle()
    assert second_cycle == [], (
        "Health check re-triggered a no-op sync: the checkpoint (max processed record) can never "
        "reach the live profile historyId, so this fires a wasted ProcessGmailHistoryJob every "
        "recurring cycle, forever."
    )


@pytest.mark.asyncio
@freeze_time("2025-01-15 12:00:00")
async def test_process_history_job_re_enqueues_when_locked(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)

    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="2000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # Add a message that will generate a new history event
    gmail_state.add_message(
        "msg_inbox_1",
        "thread_1",
        email=gmail_account.email,
        labels=["INBOX", "UNREAD"],
        headers={
            "Subject": "Test Message",
            "From": "sender@example.com",
            "To": user.email,
        },
        body_plain="This is a test message.",
    )
    next_history_id = gmail_state.get_last_pending_history_id_for_account(
        gmail_account.email, gmail_account.history_id
    )

    # Manually acquire the lock to simulate another job holding it
    gmail_account.history_sync_locked_at = datetime.now(UTC) - timedelta(seconds=10)
    await gmail_account.save()

    # Try to process the job while lock is held
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=next_history_id)
        await job.perform()

        # Verify no message was processed (job exited early due to lock)
        thread = await EmailThread.filter(creator_id=user.id).first()
        assert thread is None, "No message should have been processed while lock is held"

        # Verify a new job was re-enqueued
        enqueued_jobs = await JobsOutbox.get()
        assert len(enqueued_jobs) == 1, "Exactly one job should be re-enqueued"

        re_enqueued_job = enqueued_jobs[0]
        assert re_enqueued_job.job_type == "process_gmail_history"
        assert re_enqueued_job.job_details["gmail_account_id"] == str(gmail_account.id)
        assert re_enqueued_job.job_details["history_id"] == next_history_id

        # Verify the re-enqueued job is scheduled for retry after the sync lock timeout
        expected_perform_at = datetime.now(UTC) + timedelta(
            seconds=GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_TIMEOUT_SECONDS
        )
        assert re_enqueued_job.perform_at == expected_perform_at


@pytest.mark.asyncio
async def test_history_checkpoint_tracks_processed_records_and_recovers_lagging_reply(
    client: AppClient, gmail_state: MockGmailAPIState
):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="2000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # Record "2001" materializes, but the mailbox's current historyId lags ahead at "2010".
    gmail_state.add_message(
        "msg_a",
        "thread_a",
        email=gmail_account.email,
        labels=["INBOX"],
        headers={"Subject": "Message A", "From": "a@example.com", "To": user.email},
    )
    gmail_state.simulate_history_lag(gmail_account.email, 2010)

    # Phase 1 — checkpoint tracks the max processed record (no overshoot) and stays behind mailbox current.
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id="2010")
        await job.perform()

    thread = (
        await EmailThread.filter(creator_id=user.id, external_thread_id="thread_a")
        .first()
        .prefetch_related("messages")
    )
    assert thread is not None
    assert len(thread.messages) == 1
    assert thread.messages[0].subject == "Message A"

    await gmail_account.refresh_from_db()
    assert gmail_account.history_id == "2001"
    assert gmail_account.is_history_newer("2010") is True

    # Phase 2 — a reply that lagged in below the overshoot must not be skipped.
    gmail_state.materialize_lagging_message(
        "msg_b",
        "thread_a",
        gmail_account.email,
        history_id="2005",
        labels=["INBOX"],
        headers={"Subject": "Reply", "From": "a@example.com", "To": user.email},
    )

    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id="2005")
        await job.perform()

    thread = (
        await EmailThread.filter(creator_id=user.id, external_thread_id="thread_a")
        .first()
        .prefetch_related("messages")
    )
    assert thread is not None
    assert len(thread.messages) == 2

    await gmail_account.refresh_from_db()
    assert gmail_account.history_id == "2005"

    # Phase 3 — an expired-history 404 advances the checkpoint to the webhook id.
    gmail_state.simulate_history_expired(gmail_account.email)

    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id="9999")
        await job.perform()

    await gmail_account.refresh_from_db()
    assert gmail_account.history_id == "9999"
    assert gmail_account.synced_history_id == "9999"


@pytest.mark.asyncio
async def test_lagging_self_sent_message_recovered_into_inbox(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_account = await create_gmail_account(history_id="3000", user_id=user.id, email=user.email)
    gmail_state.set_profile(gmail_account)

    # Mailbox current historyId lags ahead at "3010" with no records materialized yet.
    gmail_state.simulate_history_lag(gmail_account.email, 3010)

    # Phase 1 — an empty history result must leave the checkpoint unchanged (no overshoot to "3010").
    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id="3010")
        await job.perform()

    await gmail_account.refresh_from_db()
    assert gmail_account.history_id == "3000"

    # Phase 2 — a self-sent message that lagged in below the overshoot is recovered into the inbox.
    gmail_state.materialize_lagging_message(
        "msg_self",
        "thread_self",
        gmail_account.email,
        history_id="3005",
        labels=["SENT", "INBOX"],
        headers={"Subject": "Apple developer #", "From": user.email, "To": user.email},
    )

    async with JobsOutbox():
        job = ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id="3005")
        await job.perform()

    thread = (
        await EmailThread.filter(creator_id=user.id, external_thread_id="thread_self")
        .first()
        .prefetch_related("messages")
    )
    assert thread is not None
    assert len(thread.messages) == 1
    message = thread.messages[0]
    assert message.message_type == EmailMessageType.SENT
    assert EmailLabel.INBOX in message.labels

    mailbox_entry = await MailboxEntry.get_or_none(resource_gid=str(thread.global_id))
    assert mailbox_entry is not None
    assert mailbox_entry.is_inbox is True


@pytest.mark.asyncio
@freeze_time("2026-06-30 12:00:00")
async def test_health_check_marks_silently_dead_watch_for_renewal(client: AppClient, gmail_state: MockGmailAPIState):
    """A watch can stop delivering pushes while watch_expires_at still says it's valid, so
    RenewGmailWatchesJob (which only renews expiring_soon accounts) never re-establishes it. When the
    health check sees undelivered mail AND no recent push, it marks the watch expired so the renewal
    job picks the account up and real-time delivery resumes."""
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    # Our records still consider the watch valid (expires in 6 days), but no push has arrived in
    # longer than the liveness threshold.
    valid_for_days = datetime.now(UTC) + timedelta(days=6)
    stale_push = datetime.now(UTC) - timedelta(seconds=GMAIL_WATCH_LIVENESS_THRESHOLD_SECONDS + 60)
    gmail_account = await create_gmail_account(
        history_id="3000",
        user_id=user.id,
        email=user.email,
        watch_expires_at=valid_for_days,
        last_push_received_at=stale_push,
    )
    gmail_state.set_profile(gmail_account)

    # Mail has arrived that the (dead) watch never delivered: the live historyId is ahead of what
    # we've synced, so the health check considers the account behind.
    gmail_state.simulate_history_lag(gmail_account.email, 3010)
    gmail_state.profiles[gmail_account.email]["historyId"] = "3010"

    async with JobsOutbox():
        await GmailHealthCheckJob(user_id=user.id).perform()

    await gmail_account.refresh_from_db()
    # Marked expired (now), so the account now matches the renewal job's selection filter.
    assert gmail_account.watch_expires_at == datetime.now(UTC)
    is_selected_for_renewal = (
        await GmailAccount.filter(GmailAccount.filters.expiring_soon() & GmailAccount.filters.has_valid_gmail_oauth())
        .filter(id=gmail_account.id)
        .exists()
    )
    assert is_selected_for_renewal


@pytest.mark.asyncio
@freeze_time("2026-06-30 12:00:00")
async def test_health_check_keeps_watch_when_push_is_recent(client: AppClient, gmail_state: MockGmailAPIState):
    """Being briefly behind with a recent push is normal (a push in flight, or a single dropped
    message) — not a dead watch. The health check must catch up via a sync without forcing a renewal."""
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    valid_for_days = datetime.now(UTC) + timedelta(days=6)
    gmail_account = await create_gmail_account(
        history_id="3000",
        user_id=user.id,
        email=user.email,
        watch_expires_at=valid_for_days,
        last_push_received_at=datetime.now(UTC),
    )
    gmail_state.set_profile(gmail_account)
    gmail_state.simulate_history_lag(gmail_account.email, 3010)
    gmail_state.profiles[gmail_account.email]["historyId"] = "3010"

    async with JobsOutbox():
        await GmailHealthCheckJob(user_id=user.id).perform()

    await gmail_account.refresh_from_db()
    # Watch left untouched — recent push means real-time delivery is working.
    assert gmail_account.watch_expires_at == valid_for_days


@pytest.mark.asyncio
async def test_setup_watch_preserves_resume_cursor_on_renewal():
    """setup_watch must only seed history_id on the first watch. On renewal, history_id is the live
    resume cursor that must keep trailing the mailbox historyId — overwriting it with the watch
    response's current historyId would skip every record between the cursor and now."""
    watch_response = {"historyId": "9999", "expiration": str(int(datetime(2026, 7, 7, tzinfo=UTC).timestamp() * 1000))}
    gmail = MagicMock()
    gmail.users.return_value.watch.return_value.execute.return_value = watch_response

    # Renewal: cursor already advanced past 0 — it must NOT jump to the watch response's historyId.
    renewing = await create_gmail_account(history_id="5000")
    await GoogleAPIClient(gmail_account=renewing, gmail=gmail).setup_watch()
    await renewing.refresh_from_db()
    assert renewing.history_id == "5000"
    assert renewing.watch_expires_at == datetime(2026, 7, 7, tzinfo=UTC)

    # First watch: an unset cursor ("0") is seeded from the watch response.
    fresh = await create_gmail_account(history_id="0")
    await GoogleAPIClient(gmail_account=fresh, gmail=gmail).setup_watch()
    await fresh.refresh_from_db()
    assert fresh.history_id == "9999"
