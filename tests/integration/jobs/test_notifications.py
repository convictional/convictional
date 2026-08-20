from datetime import UTC, datetime

import pytest

from app.jobs.mailbox import SyncMailboxJob
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import SubscriptionPreference
from app.models.workspaces.chat import Chat, ChatMessage
from app.models.workspaces.email.thread import EmailThreadComment
from app.models.workspaces.posts import Post, PostComment
from config.enums import EventAction, MailboxLabel, SubscriptionLevel
from tests.helpers.factories import (
    create_chat,
    create_collaborator,
    create_email_thread,
    create_organization,
    create_post,
    create_user,
)


@pytest.mark.asyncio
async def test_sync_mailbox_job_creates_entries_for_all_collaborators():
    organization = await create_organization()
    email_creator = await create_user(organization_id=organization.id)
    inbox_owner = await create_user(organization_id=organization.id)

    email_thread = await create_email_thread(
        creator_id=email_creator.id, organization_id=organization.id, title="Email Thread for Sync"
    )
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=inbox_owner.id)

    comment = EmailThreadComment(email_thread_id=email_thread.id, user_id=email_creator.id, content="Test comment")
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=email_creator.id
    ) as recording:
        await comment.save(recording.using_db)
        event = recording.event

    # The recording pattern alone does not sync (that's Notifier's job). Run the
    # job directly to verify it syncs every collaborator from a single event.
    await SyncMailboxJob(event_id=event.id).perform()

    entries = await MailboxEntry.filter(MailboxEntry.filters.by_resource(email_thread.global_id))
    owner_ids = {e.owner_id for e in entries}
    assert email_creator.id in owner_ids
    assert inbox_owner.id in owner_ids


@pytest.mark.asyncio
async def test_sync_mailbox_job_is_a_noop_when_resource_is_soft_deleted():
    organization = await create_organization()
    email_creator = await create_user(organization_id=organization.id)
    inbox_owner = await create_user(organization_id=organization.id)

    email_thread = await create_email_thread(
        creator_id=email_creator.id, organization_id=organization.id, title="Soft-deleted thread"
    )
    await create_collaborator(workspace_id=email_thread.workspace_id, user_id=inbox_owner.id)

    comment = EmailThreadComment(email_thread_id=email_thread.id, user_id=email_creator.id, content="Test comment")
    await email_thread.fetch_related("workspace")
    async with email_thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=email_creator.id
    ) as recording:
        await comment.save(recording.using_db)
        event = recording.event

    email_thread.deleted_at = datetime.now(UTC)
    await email_thread.save()

    await SyncMailboxJob(event_id=event.id).perform()

    entries = await MailboxEntry.filter(MailboxEntry.filters.by_resource(email_thread.global_id))
    assert entries == []


@pytest.mark.asyncio
async def test_chat_mention_reaches_inbox_even_when_recipient_is_relevant_only():
    # Settings page promise: "@mentions, assignments, and direct asks always
    # reach you." Without the escalation, a chat @mention to a user whose Chat
    # preference is RELEVANT_ONLY would be filtered out of the resolver's
    # subscriber set and the inbox would stay quiet. The job must bump them anyway.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    muter = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(muter.id, {Chat.record_type: SubscriptionLevel.RELEVANT_ONLY})

    chat = await create_chat(organization_id=organization.id, title="Group")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=sender.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=muter.id)

    message = await ChatMessage.create(chat_id=chat.id, user_id=sender.id, content=f"hey @[{muter.name}]")
    await chat.fetch_related("workspace__collaborators__user")
    async with chat.workspace.record(EventAction.CHAT_MESSAGE_CREATED, recordable=message, creator_id=sender.id) as r:
        await r.resolve_mentions(message.content)
        event = r.event
    await Chat.sync_last_message(chat.id, latest_message=message)

    await SyncMailboxJob(event_id=event.id).perform()

    entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=muter.id)
    assert entry is not None, "@mention should bump muted user's inbox"
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_dm_message_reaches_inbox_even_when_recipient_is_relevant_only():
    # Same promise — "direct asks always reach you" — applied to 1:1 chats.
    # A DM recipient at RELEVANT_ONLY would otherwise be filtered out; the
    # is_dm escalation mirrors what _notify_push_subscribers does for push.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    muter = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(muter.id, {Chat.record_type: SubscriptionLevel.RELEVANT_ONLY})

    chat = await create_chat(organization_id=organization.id)  # No title, no group → DM shape
    await create_collaborator(workspace_id=chat.workspace_id, user_id=sender.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=muter.id)
    await chat.fetch_related("workspace__collaborators__user")
    assert chat.type.is_dm

    message = await ChatMessage.create(chat_id=chat.id, user_id=sender.id, content="ping")
    async with chat.workspace.record(EventAction.CHAT_MESSAGE_CREATED, recordable=message, creator_id=sender.id) as r:
        event = r.event
    await Chat.sync_last_message(chat.id, latest_message=message)

    await SyncMailboxJob(event_id=event.id).perform()

    entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=muter.id)
    assert entry is not None, "DM should bump muted user's inbox"
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_post_mention_reaches_inbox_even_when_mentioned_user_is_relevant_only():
    # Same escalation extended to posts — the settings page promise applies
    # across resource types. add_mentioned_collaborators makes the mentioned
    # user a collaborator on save; the resolver then filters them out via
    # their global Posts=RELEVANT_ONLY; the escalation puts them back.
    organization = await create_organization()
    author = await create_user(organization_id=organization.id)
    muter = await create_user(name="Muted Reader", organization_id=organization.id)
    await SubscriptionPreference.update_for(muter.id, {Post.record_type: SubscriptionLevel.RELEVANT_ONLY})

    post = await create_post(creator_id=author.id, organization_id=organization.id)
    await post.fetch_related("workspace__collaborators__user")

    comment = PostComment(content=f"hi @[{muter.name}]", post_id=post.id, user_id=author.id)
    async with post.workspace.record(EventAction.POST_COMMENTED, recordable=comment, creator_id=author.id) as r:
        await comment.save(r.using_db)
        await r.resolve_mentions(comment.content)
        event = r.event

    await SyncMailboxJob(event_id=event.id).perform()

    entry = await MailboxEntry.get_or_none(resource_gid=str(post.global_id), owner_id=muter.id)
    assert entry is not None, "@mention should bump muted user's inbox on posts too"
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels
