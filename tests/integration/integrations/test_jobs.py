from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.mailbox import UnsnoozeMailboxEntryJob
from app.models.accounts import User
from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.posts import Post, PostMailboxEntry
from infra.jobs import InlineJobs, JobsOutbox
from integrations.google.jobs.gmail import RestoreGmailInboxLabelJob
from integrations.jobs import CheckSnoozedMailboxEntriesJob
from tests.helpers.factories import (
    create_collaborator,
    create_email_message,
    create_mailbox_entry,
    create_post,
    create_user,
)


async def _expired_snooze(entry: MailboxEntry) -> None:
    entry.snoozed_until = datetime.now(UTC) - timedelta(hours=1)
    await entry.save(update_fields=["snoozed_until"])


async def _post_entry(user: User) -> tuple[MailboxEntry, Post]:
    other = await create_user(organization_id=user.organization_id)
    post = await create_post(creator_id=other.id, organization_id=user.organization_id, title="Shared")
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=user.id)
    await post.workspace.subscribe(user.id)
    await PostMailboxEntry(post).sync()

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=user.id)
    return entry, post


async def _email_entry(user: User) -> tuple[MailboxEntry, EmailThread]:
    message = await create_email_message(creator_id=user.id, organization_id=user.organization_id)
    thread = await EmailThread.get(id=message.thread_id)
    entry = await create_mailbox_entry(
        owner_id=user.id, organization_id=user.organization_id, resource_gid=thread.global_id
    )
    return entry, thread


@pytest.mark.asyncio
async def test_check_snoozed_scan_fans_out_unsnooze_and_only_mirrors_gmail_for_email(background_jobs: InlineJobs):
    # The scan wakes every expiring entry via the generic UnsnoozeMailboxEntryJob, and
    # additionally enqueues the Gmail-only RestoreGmailInboxLabelJob for EmailThread entries.
    user = await create_user()
    post_entry, post = await _post_entry(user)
    email_entry, thread = await _email_entry(user)

    await Mailbox(user).snooze(post, snoozed_until=datetime.now(UTC) + timedelta(hours=2))
    await Mailbox(user).snooze(thread, snoozed_until=datetime.now(UTC) + timedelta(hours=2))
    await post_entry.refresh_from_db()
    await email_entry.refresh_from_db()
    await _expired_snooze(post_entry)
    await _expired_snooze(email_entry)

    # The scan enqueues into the JobsOutbox; draining it on context exit runs the enqueued
    # jobs inline via background_jobs. RestoreGmailInboxLabelJob no-ops here (no Gmail account).
    async with JobsOutbox():
        await CheckSnoozedMailboxEntriesJob().perform()

    assert background_jobs.has_completed_job(UnsnoozeMailboxEntryJob, count=2)
    assert len(background_jobs.all_completed_jobs_by_type(RestoreGmailInboxLabelJob)) == 1

    await post_entry.refresh_from_db()
    await email_entry.refresh_from_db()
    assert post_entry.is_inbox is True
    assert email_entry.is_inbox is True
