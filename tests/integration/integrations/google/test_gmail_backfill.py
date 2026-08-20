from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from app.models.workspaces.email.thread import EmailMessage, EmailThread
from config.enums import EmailLabel, EmailMailboxLabel, EmailMessageType
from infra.jobs import InlineJobs, JobsOutbox
from integrations.google.gmail import MockGmailAPIState, MockGoogleAPIClient
from integrations.google.jobs.maintenance import BACKFILL_QUERIES, BackfillGmailEmailsJob
from tests.helpers.factories import (
    create_email_message,
    create_gmail_account,
    create_mailbox_entry,
    create_user,
)
from tests.integration.integrations.google.conftest import add_gmail_token_to_user


async def _setup_user_with_gmail(gmail_state: MockGmailAPIState):
    user = await create_user()
    await add_gmail_token_to_user(user)
    gmail_account = await create_gmail_account(
        history_id="1000",
        user_id=user.id,
        email=user.email,
        onboarding_mailbox_sync_completed_at=datetime.now(UTC),
    )
    gmail_state.set_profile(gmail_account)
    return user, gmail_account


@pytest.mark.asyncio
async def test_backfill_gmail_emails_happy_path(gmail_state: MockGmailAPIState):
    # Archived Gmail query must not exclude sent — otherwise sent-then-archived threads
    # shown in mailbox_archived would never be backfilled.
    assert "-in:sent" not in BACKFILL_QUERIES[1]

    user, gmail_account = await _setup_user_with_gmail(gmail_state)
    gmail_state.add_message(
        "msg_sent_1",
        "thread_sent_1",
        email=gmail_account.email,
        labels=["SENT"],
        headers={"Subject": "Sent 1", "From": user.email, "To": "recipient1@example.com"},
        body_plain="Sent message 1.",
    )
    gmail_state.add_message(
        "msg_sent_2",
        "thread_sent_2",
        email=gmail_account.email,
        labels=["SENT"],
        headers={"Subject": "Sent 2", "From": user.email, "To": "recipient2@example.com"},
        body_plain="Sent message 2.",
    )
    gmail_state.add_message(
        "msg_archived_1",
        "thread_archived_1",
        email=gmail_account.email,
        labels=["CATEGORY_PERSONAL"],
        headers={"Subject": "Archived 1", "From": "sender@example.com", "To": user.email},
        body_plain="Archived message.",
    )

    # Patch enqueue_job so the sent → archived re-enqueue is captured instead of run.
    # That lets us assert (1) end-to-end sync of sent messages AND (2) that the archived
    # re-enqueue carries messages_created forward (P1-1 regression — if reset to 0, the
    # shared per-run budget silently doubles).
    captured: list[BackfillGmailEmailsJob] = []

    async def capture(job_definition):
        if isinstance(job_definition, BackfillGmailEmailsJob):
            captured.append(job_definition)

    with patch("integrations.google.jobs.maintenance.enqueue_job", side_effect=capture):
        async with JobsOutbox():
            await BackfillGmailEmailsJob(user_id=user.id, max_messages=100).perform()

    messages = await EmailMessage.filter(thread__creator_id=user.id).all()
    assert {m.external_message_id for m in messages} == {"msg_sent_1", "msg_sent_2"}

    archived_reenqueue = next(j for j in captured if j.current_query_index == 1)
    assert archived_reenqueue.messages_created == 2
    assert archived_reenqueue.max_messages == 100


@pytest.mark.asyncio
async def test_backfill_gmail_emails_sad_paths(background_jobs: InlineJobs, gmail_state: MockGmailAPIState):
    # No GmailAccount — early return, no job recorded.
    user_no_account = await create_user()
    await add_gmail_token_to_user(user_no_account)
    async with JobsOutbox():
        await BackfillGmailEmailsJob(user_id=user_no_account.id).perform()
    assert not background_jobs.has_completed_job(BackfillGmailEmailsJob)

    # Onboarding not completed — early return.
    user_incomplete = await create_user()
    await add_gmail_token_to_user(user_incomplete)
    account_incomplete = await create_gmail_account(
        history_id="1000",
        user_id=user_incomplete.id,
        email=user_incomplete.email,
        onboarding_mailbox_sync_completed_at=None,
    )
    gmail_state.set_profile(account_incomplete)
    background_jobs.reset()
    async with JobsOutbox():
        await BackfillGmailEmailsJob(user_id=user_incomplete.id).perform()
    assert not background_jobs.has_completed_job(BackfillGmailEmailsJob)

    # GmailAccount present, onboarding complete, but user has no Gmail OAuth scopes — early return.
    user_no_scopes = await create_user()
    account_no_scopes = await create_gmail_account(
        history_id="1000",
        user_id=user_no_scopes.id,
        email=user_no_scopes.email,
        onboarding_mailbox_sync_completed_at=datetime.now(UTC),
    )
    gmail_state.set_profile(account_no_scopes)
    background_jobs.reset()
    async with JobsOutbox():
        await BackfillGmailEmailsJob(user_id=user_no_scopes.id).perform()
    assert not background_jobs.has_completed_job(BackfillGmailEmailsJob)

    # Already at budget cap — early return, no messages created.
    user, gmail_account = await _setup_user_with_gmail(gmail_state)
    gmail_state.add_message(
        "msg_over_cap",
        "thread_over_cap",
        email=gmail_account.email,
        labels=["SENT"],
        headers={"Subject": "Over Cap", "From": user.email, "To": "recipient@example.com"},
        body_plain="Should not be created.",
    )
    before_count = await EmailMessage.filter(thread__creator_id=user.id).count()
    background_jobs.reset()
    async with JobsOutbox():
        await BackfillGmailEmailsJob(user_id=user.id, max_messages=5, messages_created=5).perform()
    assert await EmailMessage.filter(thread__creator_id=user.id).count() == before_count

    # One thread failing to fetch must not abort the rest of the batch — we rely on
    # gather(return_exceptions=True); regressing that would silently drop whole pages.
    user, gmail_account = await _setup_user_with_gmail(gmail_state)
    for i, tid in enumerate(["thread_ok_1", "thread_bad", "thread_ok_2"]):
        gmail_state.add_message(
            f"msg_{tid}",
            tid,
            email=gmail_account.email,
            labels=["SENT"],
            headers={"Subject": tid, "From": user.email, "To": f"r{i}@example.com"},
            body_plain=tid,
        )

    original_fetch = MockGoogleAPIClient.fetch_thread_data

    async def fetch_with_failure(self_client, thread_id):
        if thread_id == "thread_bad":
            raise RuntimeError("transient gmail API error")
        return await original_fetch(self_client, thread_id)

    with patch.object(MockGoogleAPIClient, "fetch_thread_data", fetch_with_failure):
        async with JobsOutbox():
            await BackfillGmailEmailsJob(user_id=user.id).perform()

    external_ids = {m.external_message_id for m in await EmailMessage.filter(thread__creator_id=user.id).all()}
    assert {"msg_thread_ok_1", "msg_thread_ok_2"}.issubset(external_ids)
    assert "msg_thread_bad" not in external_ids

    # Per-owner anchor: user A's `before:` must track user A's own oldest synced message.
    # User B's messages (on threads user A does not own) must never influence user A's anchor
    # — regressing would either leak user B's timestamps into user A's Gmail query or
    # re-include collaborator messages via raw EmailMessage.labels filtering (P2-2).
    user_a = await create_user()
    user_b = await create_user(organization_id=user_a.organization_id)
    await add_gmail_token_to_user(user_a)
    await create_gmail_account(
        history_id="1000",
        user_id=user_a.id,
        email=user_a.email,
        onboarding_mailbox_sync_completed_at=datetime.now(UTC),
    )

    user_a_received_at = datetime(2026, 1, 1, tzinfo=UTC)
    message_a = await create_email_message(
        message_type=EmailMessageType.SENT,
        user_id=user_a.id,
        organization_id=user_a.organization_id,
        labels=[EmailLabel.SENT],
        sender=user_a.email,
        to=["external@example.com"],
        received_at=user_a_received_at,
    )
    for i in range(10):
        await create_email_message(
            message_type=EmailMessageType.SENT,
            user_id=user_b.id,
            organization_id=user_a.organization_id,
            labels=[EmailLabel.SENT],
            sender=user_b.email,
            to=["external@example.com"],
            external_message_id=f"shared_b_{i}",
            received_at=datetime(2025, 1, 1, tzinfo=UTC),
        )
    thread_a = await EmailThread.get(id=message_a.thread_id)
    await create_mailbox_entry(
        resource_gid=thread_a.global_id,
        owner_id=user_a.id,
        organization_id=user_a.organization_id,
        labels=[EmailMailboxLabel.SENT],
        last_comment_author_id=user_a.id,
    )

    # Anchor must match user A's own message timestamp, not user B's (older) one —
    # picking up user B's timestamp would be the regression.
    anchor = await BackfillGmailEmailsJob(user_id=user_a.id)._resolve_before_timestamp()
    assert anchor == int(user_a_received_at.timestamp())
