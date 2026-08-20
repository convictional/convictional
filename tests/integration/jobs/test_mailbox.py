from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.mailbox import UnsnoozeMailboxEntryJob
from app.models.accounts import User
from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.workspaces.chat import Chat
from app.models.workspaces.posts import Post, PostMailboxEntry
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_post,
    create_user,
)


async def _post_entry(user: User) -> tuple[MailboxEntry, Post]:
    other = await create_user(organization_id=user.organization_id)
    post = await create_post(creator_id=other.id, organization_id=user.organization_id, title="Shared")
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, user_id=user.id)
    await post.workspace.subscribe(user.id)
    await PostMailboxEntry(post).sync()

    entry = await MailboxEntry.get(resource_gid=str(post.global_id), owner_id=user.id)
    return entry, post


async def _chat_entry(user: User) -> tuple[MailboxEntry, Chat]:
    other = await create_user(organization_id=user.organization_id)
    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat.id, user_id=other.id, content="Hello")
    await chat.refresh_from_db()
    await Mailbox.sync(chat)

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user.id)
    return entry, chat


async def _expire_snooze(entry: MailboxEntry) -> None:
    """Force the snooze past its expiry, as the recurring scan would see it."""
    entry.snoozed_until = datetime.now(UTC) - timedelta(hours=1)
    await entry.save(update_fields=["snoozed_until"])


@pytest.mark.asyncio
@pytest.mark.parametrize("resource_kind", ["post", "chat"])
async def test_unsnooze_job_wakes_non_email_entries(resource_kind: str):
    # The reported bug (issue #8837): a snoozed Post never returned to the inbox because
    # the wake job only unsnoozed EmailThreads. Chat guards against the same email-only
    # regression on any non-email resource type.
    user = await create_user()
    resource: Post | Chat
    if resource_kind == "post":
        entry, resource = await _post_entry(user)
    else:
        entry, resource = await _chat_entry(user)

    await Mailbox(user).snooze(resource, snoozed_until=datetime.now(UTC) + timedelta(hours=2))
    await entry.refresh_from_db()
    assert entry.is_snoozed
    assert entry.is_archived
    await _expire_snooze(entry)

    await UnsnoozeMailboxEntryJob(mailbox_entry_id=entry.id).perform()

    await entry.refresh_from_db()
    assert entry.snoozed_until is None
    assert entry.is_inbox is True
    assert entry.is_unread is True


@pytest.mark.asyncio
async def test_unsnooze_job_soft_deletes_orphaned_entry():
    # A snoozed Chat deleted before any resync leaves a dangling entry (Chat.soft_delete
    # doesn't cascade into mailbox cleanup the way Post/EmailThread do). The wake job must
    # soft-delete the orphan, NOT resurface a ghost pointing at a nonexistent resource.
    user = await create_user()
    entry, chat = await _chat_entry(user)

    await Mailbox(user).snooze(chat, snoozed_until=datetime.now(UTC) + timedelta(hours=2))
    await entry.refresh_from_db()
    await _expire_snooze(entry)

    await chat.soft_delete()

    await UnsnoozeMailboxEntryJob(mailbox_entry_id=entry.id).perform()

    # The entry is gone from every view — not resurfaced into the inbox as unread.
    views = Mailbox(user).filters
    assert await views.inbox.filter(id=entry.id).count() == 0
    assert await views.archived.filter(id=entry.id).count() == 0
    assert await views.snoozed.filter(id=entry.id).count() == 0

    orphan = await MailboxEntry.unscoped.get(id=entry.id)
    assert orphan.is_deleted
