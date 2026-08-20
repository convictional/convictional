import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.models.collaboration.mailbox import BaseMailboxEntry, MailboxEntry
from app.models.collaboration.workspace import SubscriberResolver, Subscription, SubscriptionPreference, Visit
from app.models.workspaces.chat import Chat, ChatMailboxEntry
from config.enums import EventAction, MailboxLabel, SubscriptionLevel
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_event,
    create_organization,
    create_user,
)


async def _dm_chat_with_message(organization, user_a, user_b):
    chat = await create_chat(organization_id=organization.id, creator_id=user_a.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_b.id)
    message = await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="Hello")
    await chat.refresh_from_db()
    return chat, message


async def _record_message_event(chat, message, user_id):
    await chat.fetch_related("workspace")
    async with chat.workspace.record(EventAction.CHAT_MESSAGE_CREATED, recordable=message, creator_id=user_id):
        pass


@pytest.mark.asyncio
async def test_sync_creates_entries_for_all_members():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)

    await ChatMailboxEntry(chat).sync()

    entries = await MailboxEntry.filter(resource_gid=str(chat.global_id))
    owner_ids = {e.owner_id for e in entries}
    assert user_a.id in owner_ids
    assert user_b.id in owner_ids


@pytest.mark.asyncio
async def test_sync_from_sets_entry_fields():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, message = await _dm_chat_with_message(organization, user_a, user_b)

    await ChatMailboxEntry(chat).sync()

    entry_b = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert entry_b.title == user_a.display_name
    assert entry_b.is_shared is True
    assert entry_b.organization_id == organization.id
    assert entry_b.last_comment == "Hello"
    assert entry_b.last_comment_author_id == user_a.id
    assert MailboxLabel.INBOX in entry_b.labels
    assert MailboxLabel.UNREAD in entry_b.labels

    # Sender should not get inbox/unread for their own message
    entry_a = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_a.id)
    assert MailboxLabel.INBOX not in entry_a.labels
    assert MailboxLabel.UNREAD not in entry_a.labels


@pytest.mark.asyncio
async def test_activity_event_supersedes_message_preview():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, message = await _dm_chat_with_message(organization, user_a, user_b)
    await _record_message_event(chat, message, user_a.id)

    # A chat-level activity event newer than the last message pins the event and drops the message
    # text — the client renders the activity line from the raw event instead of the message preview.
    await chat.fetch_related("workspace")
    async with chat.workspace.record(EventAction.CHAT_RENAMED, recordable=chat, creator_id=user_a.id) as rec:
        rec.event.details.update({"title": "Roadmap"})
    await ChatMailboxEntry(chat).sync()

    entry_b = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert entry_b.last_event_id == rec.event.id
    assert entry_b.last_comment is None

    # A newer message restores the message preview (the activity event is no longer newest).
    await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="back to chatting")
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    entry_b = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert entry_b.last_event_id is None
    assert entry_b.last_comment == "back to chatting"


@pytest.mark.asyncio
async def test_decided_event_drives_activity_preview():
    # Recording a decision creates no message, so it must drive the activity line via its event
    # (like rename), not the message preview — the row already force-unreads on DECIDED.
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, message = await _dm_chat_with_message(organization, user_a, user_b)
    await _record_message_event(chat, message, user_a.id)

    await chat.fetch_related("workspace")
    decision = await create_event(chat.workspace, creator_id=user_a.id, action=EventAction.DECIDED)
    await ChatMailboxEntry(chat).sync()

    entry_b = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert entry_b.last_event_id == decision.id
    assert entry_b.last_comment is None


@pytest.mark.asyncio
async def test_dm_title_shows_counterpart_name():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)

    await ChatMailboxEntry(chat).sync()

    entry_a = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_a.id)
    entry_b = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert entry_a.title == user_b.display_name
    assert entry_b.title == user_a.display_name


@pytest.mark.asyncio
async def test_group_chat_title_uses_chat_name():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat = await create_chat(organization_id=organization.id, title="Team Chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_a.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_b.id)

    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_a.id)
    assert entry.title == "Team Chat"


@pytest.mark.asyncio
async def test_sync_updates_on_new_message():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    entry.label_as_read()
    entry.label_as_archived()
    await entry.save(update_fields=["labels"])

    await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="Follow up")
    await chat.refresh_from_db()

    await ChatMailboxEntry(chat).sync()

    await entry.refresh_from_db()
    assert entry.last_comment == "Follow up"
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_sync_soft_deletes_on_chat_deletion():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    await chat.soft_delete()
    await ChatMailboxEntry(chat).sync()

    entries = await MailboxEntry.filter(resource_gid=str(chat.global_id))
    assert len(entries) == 0

    deleted_entries = await MailboxEntry.unscoped.filter(resource_gid=str(chat.global_id))
    assert all(e.is_deleted for e in deleted_entries)


@pytest.mark.asyncio
async def test_touch_syncs_single_user():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    # Mark user_b's entry as read so we can detect if touch re-syncs it
    entry_b = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    entry_b.label_as_read()
    entry_b.label_as_archived()
    await entry_b.save(update_fields=["labels"])

    await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="New message")
    await chat.refresh_from_db()

    # Touch only user_a — user_b's entry should remain archived
    await ChatMailboxEntry(chat).touch(user_a)

    entry_a = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_a.id)
    assert entry_a.last_comment == "New message"

    await entry_b.refresh_from_db()
    assert MailboxLabel.INBOX not in entry_b.labels


@pytest.mark.asyncio
async def test_sync_soft_deletes_entries_for_non_members():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)
    user_c = await create_user(organization_id=organization.id)

    chat = await create_chat(organization_id=organization.id, title="Group")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_a.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_b.id)
    member_c = await create_collaborator(workspace_id=chat.workspace_id, user_id=user_c.id)

    await ChatMailboxEntry(chat).sync()
    assert await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=user_c.id) is not None

    # Remove user_c from the workspace, then re-sync. ChatMailboxEntry._clear_non_members
    # drives the mailbox cleanup — no dedicated signal.
    await member_c.delete()
    await ChatMailboxEntry(chat).sync()

    assert await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=user_c.id) is None
    deleted_entry = await MailboxEntry.unscoped.get(resource_gid=str(chat.global_id), owner_id=user_c.id)
    assert deleted_entry.is_deleted


@pytest.mark.asyncio
async def test_own_messages_do_not_trigger_inbox():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_a.id)
    entry.label_as_read()
    entry.label_as_archived()
    await entry.save(update_fields=["labels"])

    await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="My own message")
    await chat.refresh_from_db()

    await ChatMailboxEntry(chat).sync()

    await entry.refresh_from_db()
    assert MailboxLabel.INBOX not in entry.labels
    assert MailboxLabel.UNREAD not in entry.labels


@pytest.mark.asyncio
async def test_mark_as_read_records_visit_and_clears_unread():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    assert await Visit.get_or_none(workspace_id=chat.workspace_id, user_id=user_b.id) is None

    await ChatMailboxEntry(chat).mark_as_read(user_b)

    visit = await Visit.get_or_none(workspace_id=chat.workspace_id, user_id=user_b.id)
    assert visit is not None

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert MailboxLabel.UNREAD not in entry.labels


@pytest.mark.asyncio
async def test_mark_as_unread_rewinds_visit_so_unread_count_recovers():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, first_message = await _dm_chat_with_message(organization, user_a, user_b)
    await _record_message_event(chat, first_message, user_a.id)
    second_message = await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="Second")
    await _record_message_event(chat, second_message, user_a.id)
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    await ChatMailboxEntry(chat).mark_as_read(user_b)

    visit = await Visit.get_or_none(workspace_id=chat.workspace_id, user_id=user_b.id)
    assert visit is not None
    read_event_id: UUID | None = visit.last_event_id
    assert read_event_id is not None

    await ChatMailboxEntry(chat).mark_as_unread(user_b)

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert MailboxLabel.UNREAD in entry.labels
    # Explicit mark_as_unread clears the read high-water mark (shared base behavior).
    assert entry.read_at is None

    await visit.refresh_from_db()
    assert visit.last_event_id != read_event_id
    assert visit.last_event_id is not None

    # Visit cursor must be older than the latest non-self message so chat
    # detail counts at least one unread message.
    await visit.fetch_related("last_event")
    assert visit.last_event is not None
    assert visit.last_event.created_at < second_message.created_at


@pytest.mark.asyncio
async def test_mark_as_unread_with_only_self_messages_is_noop_on_visit():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat = await create_chat(organization_id=organization.id, creator_id=user_a.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_b.id)
    self_message = await create_chat_message(chat_id=chat.id, user_id=user_b.id, content="self")
    await _record_message_event(chat, self_message, user_b.id)
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()
    await ChatMailboxEntry(chat).mark_as_read(user_b)
    visit = await Visit.get_or_none(workspace_id=chat.workspace_id, user_id=user_b.id)
    assert visit is not None
    initial_event_id = visit.last_event_id

    await ChatMailboxEntry(chat).mark_as_unread(user_b)

    await visit.refresh_from_db()
    assert visit.last_event_id == initial_event_id


@pytest.mark.asyncio
async def test_sync_without_messages_does_not_inbox():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat = await create_chat(organization_id=organization.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_a.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user_b.id)

    await ChatMailboxEntry(chat).sync()

    for user in [user_a, user_b]:
        entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user.id)
        assert MailboxLabel.INBOX not in entry.labels
        assert MailboxLabel.UNREAD not in entry.labels
        assert entry.last_activity_at == chat.created_at


@pytest.mark.asyncio
async def test_new_message_unsnoozes_entry():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    entry.snoozed_until = datetime.now(UTC) + timedelta(days=1)
    entry.label_as_archived()
    await entry.save(update_fields=["labels", "snoozed_until"])

    await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="Wake up")
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    await entry.refresh_from_db()
    assert entry.snoozed_until is None
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_last_activity_at_updates_on_new_message():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, first_message = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert entry.last_activity_at == first_message.created_at

    second_message = await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="Follow up")
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    await entry.refresh_from_db()
    assert entry.last_activity_at == second_message.created_at


@pytest.mark.asyncio
async def test_unread_follows_message_deletion():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, first_message = await _dm_chat_with_message(organization, user_a, user_b)
    second_message = await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="second")
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert MailboxLabel.UNREAD in entry.labels

    # Deleting one of two unread messages: another unread message remains, so UNREAD persists.
    await second_message.soft_delete()
    await Chat.sync_last_message(chat.id)
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()
    await entry.refresh_from_db()
    assert MailboxLabel.UNREAD in entry.labels

    # Deleting the last remaining message: nothing left to read, UNREAD must clear.
    await first_message.soft_delete()
    await Chat.sync_last_message(chat.id)
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()
    await entry.refresh_from_db()
    assert MailboxLabel.UNREAD not in entry.labels


@pytest.mark.asyncio
async def test_last_activity_at_does_not_regress_on_message_deletion():
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, first_message = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    second_message = await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="Follow up")
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert entry.last_activity_at == second_message.created_at

    await second_message.soft_delete()
    await Chat.sync_last_message(chat.id)
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    await entry.refresh_from_db()
    assert entry.last_activity_at == second_message.created_at


@pytest.mark.asyncio
async def test_decision_event_marks_unread_via_routing_but_does_not_leak():
    # A decision mark creates no message, so chat's message-based content gate
    # (_refresh_content) can't see it. The routing layer (InboxUpdate.for_event) marks a
    # reached, non-sender DECIDED event unread regardless of the content gate. Because that
    # decision rides on the event, a later no-event recompute has nothing to force and can't
    # resurrect the decision.
    assert "event" not in inspect.signature(BaseMailboxEntry._refresh_content).parameters

    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    entry.label_as_read()
    await entry.save(update_fields=["labels"])

    await chat.fetch_related("workspace")
    decision = await create_event(chat.workspace, creator_id=user_a.id, action=EventAction.DECIDED)
    await ChatMailboxEntry(chat).sync(event=decision)

    await entry.refresh_from_db()
    assert MailboxLabel.UNREAD in entry.labels

    # Read it, then run a no-event recompute: with no event to thread, the decision
    # can't re-mark the row unread.
    entry.label_as_read()
    await entry.save(update_fields=["labels"])
    await ChatMailboxEntry(chat).sync()

    await entry.refresh_from_db()
    assert MailboxLabel.UNREAD not in entry.labels


@pytest.mark.asyncio
async def test_concurrent_mark_as_read_and_sync_serialize_via_select_for_update():
    # Regression for the race called out in chat.py:644: a user marking a chat read
    # at the same instant another collaborator's send triggers Mailbox.sync would
    # otherwise compute label_as_unread from stale state, and whichever transaction
    # committed second would clobber the other's labels (update_fields=[labels, ...]).
    # The SELECT FOR UPDATE inside find_or_create_entry serializes them so the loser
    # reads the winner's labels and computes from current state. Either serialization
    # is acceptable; the invariant is that no labels-vs-read_at clobber happens.
    organization = await create_organization()
    user_a = await create_user(organization_id=organization.id)
    user_b = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, user_a, user_b)
    # Pre-existing state: user_b's entry is in inbox+unread from user_a's first message.
    await ChatMailboxEntry(chat).sync()
    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=user_b.id)
    assert MailboxLabel.UNREAD in entry.labels
    assert MailboxLabel.INBOX in entry.labels
    assert entry.read_at is None

    # Race: user_b marks the chat read while user_a's next message lands and triggers
    # a full mailbox sync. Run both concurrently; the SELECT FOR UPDATE must serialize.
    await create_chat_message(chat_id=chat.id, user_id=user_a.id, content="follow up")
    await chat.refresh_from_db()

    await asyncio.gather(
        ChatMailboxEntry(chat).mark_as_read(user_b),
        ChatMailboxEntry(chat).sync(),
    )

    await entry.refresh_from_db()
    # No matter the serialization order, mark_as_read ran and persisted read_at.
    # If the SELECT FOR UPDATE failed, mark_as_read's update_fields=[labels, read_at]
    # would race the sync's update_fields=[labels, last_activity_at, ...], and the
    # loser's writes would be lost on its own update_fields. read_at being None
    # would be the smoking gun for a lost mark_as_read write.
    assert entry.read_at is not None, "mark_as_read's read_at write was lost — SELECT FOR UPDATE serialization broken"

    # The labels and read_at must remain coherent with each other:
    #   - sync committing first, mark_as_read second: entry is read (UNREAD cleared,
    #     INBOX retained — label_as_read doesn't touch INBOX).
    #   - mark_as_read committing first, sync second: entry is unread again (sync
    #     saw the new message arriving after read_at and re-marked unread+inbox).
    if MailboxLabel.UNREAD in entry.labels:
        assert MailboxLabel.INBOX in entry.labels
    # Either ordering is a valid serializable outcome — the test's job is to make
    # sure no torn write happens (read_at preserved).


@pytest.mark.asyncio
async def test_sync_respects_relevant_only_subscription():
    # Chat defaults to ALL for every collaborator, but a user can mute a noisy chat
    # via the bell (set subscription to RELEVANT_ONLY). When that happens, new
    # messages from others must NOT relight the chat in their inbox. PostMailboxEntry
    # already respects this by iterating the resolver's subscriber set; chat now does too.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    listener = await create_user(organization_id=organization.id)  # stays ALL
    muter = await create_user(organization_id=organization.id)  # drops to RELEVANT_ONLY

    chat = await create_chat(organization_id=organization.id, title="Noisy team chat")
    await create_collaborator(workspace_id=chat.workspace_id, user_id=sender.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=listener.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=muter.id)

    # Muter explicitly opts out of the chat's inbox surface.
    await chat.workspace.unsubscribe(muter.id)

    # Sender posts a message; trigger the mailbox sync.
    await create_chat_message(chat_id=chat.id, user_id=sender.id, content="who's around")
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    listener_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=listener.id)
    assert listener_entry is not None
    assert MailboxLabel.INBOX in listener_entry.labels
    assert MailboxLabel.UNREAD in listener_entry.labels

    # Muter at RELEVANT_ONLY: row must NOT be created/relit. PostMailboxEntry behaves
    # the same way — non-subscribers don't get their rows touched on routine activity.
    muter_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=muter.id)
    assert muter_entry is None or (
        MailboxLabel.INBOX not in muter_entry.labels and MailboxLabel.UNREAD not in muter_entry.labels
    )


@pytest.mark.asyncio
async def test_event_sync_escalation_lives_only_in_resolver(monkeypatch):
    # Inbox escalation (@mention force-include, DM force-include) must live
    # exclusively in SubscriberResolver, never inline in the mailbox sync path —
    # otherwise the same rule drifts across two layers. recipient here is BOTH a
    # DM collaborator and a mention target (the two escalation vectors), yet with
    # the resolver stubbed to name nobody the sync writes nobody. Any row would
    # mean the sync path escalated on its own.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    recipient = await create_user(organization_id=organization.id)

    chat, _ = await _dm_chat_with_message(organization, sender, recipient)
    # Drop recipient below the chat's ALL default so baseline membership can't
    # account for their inclusion — only the DM force-include / mention vectors
    # can, which is what the control below must isolate.
    await Subscription.create(
        workspace_id=chat.workspace_id, subscriber_id=recipient.id, level=SubscriptionLevel.RELEVANT_ONLY
    )
    await chat.fetch_related("workspace__collaborators__user")
    assert chat.type.is_dm

    event = await create_event(chat.workspace, creator_id=sender.id, action=EventAction.CHAT_MESSAGE_CREATED)

    # Control: at RELEVANT_ONLY the recipient is reached only via escalation
    # (DM force-include + mention), so the real resolver naming them confirms
    # the empty result below is the stub's doing, not an inert fixture.
    would_reach = await SubscriberResolver(workspace=chat.workspace).resolve_for_inbox(
        event, direct_recipients=[recipient]
    )
    assert recipient.id in {u.id for u in would_reach}

    async def _resolve_nobody(self, *args, **kwargs):
        return []

    monkeypatch.setattr(SubscriberResolver, "resolve_for_inbox", _resolve_nobody)

    await ChatMailboxEntry(chat).sync(event=event, direct_recipients=[recipient])

    recipient_entry = await MailboxEntry.get_or_none(resource_gid=str(chat.global_id), owner_id=recipient.id)
    assert recipient_entry is None


async def _send_and_sync(chat, sender, content, *, direct_recipients=None):
    await create_chat_message(chat_id=chat.id, user_id=sender.id, content=content)
    await chat.refresh_from_db()
    await chat.fetch_related("workspace")
    event = await create_event(chat.workspace, creator_id=sender.id, action=EventAction.CHAT_MESSAGE_CREATED)
    await ChatMailboxEntry(chat).sync(event=event, direct_recipients=direct_recipients or [])


@pytest.mark.asyncio
async def test_existing_row_tracks_live_content_for_below_all_owner():
    # The mentioned-then-quiet staleness fix. An owner below ALL via a *global*
    # RELEVANT_ONLY preference (not a per-chat bell-mute) who was pulled into their
    # inbox by a mention keeps their row tracking live content on later non-mention
    # messages — and once they've read it, those updates don't re-bump it to unread.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    observer = await create_user(organization_id=organization.id)
    third = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(observer.id, {Chat.record_type: SubscriptionLevel.RELEVANT_ONLY})

    chat = await create_chat(organization_id=organization.id, title="Team chat")
    for user in (sender, observer, third):
        await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    # The mention pulls the below-ALL observer into their inbox, unread.
    await _send_and_sync(chat, sender, "heads up @observer", direct_recipients=[observer])
    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=observer.id)
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels

    await ChatMailboxEntry(chat).mark_as_read(observer)

    # Subsequent non-mention messages keep the row current without re-bumping unread.
    await _send_and_sync(chat, sender, "first follow up")
    await _send_and_sync(chat, third, "second follow up")
    await _send_and_sync(chat, sender, "third follow up")

    await entry.refresh_from_db()
    assert entry.last_comment == "third follow up"
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD not in entry.labels
    assert entry.read_at is not None


@pytest.mark.asyncio
async def test_bell_muted_row_tracks_content_but_not_unread():
    # Slack model: muting a chat affects the badge, not the preview. After a user
    # bell-mutes (per-workspace Subscription at RELEVANT_ONLY), new non-mention
    # messages keep their row's content current but never mark it unread.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    muter = await create_user(organization_id=organization.id)
    third = await create_user(organization_id=organization.id)

    chat = await create_chat(organization_id=organization.id, title="Noisy chat")
    for user in (sender, muter, third):
        await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    await _send_and_sync(chat, sender, "ping @muter", direct_recipients=[muter])
    await ChatMailboxEntry(chat).mark_as_read(muter)
    await chat.fetch_related("workspace")
    await chat.workspace.unsubscribe(muter.id)

    await _send_and_sync(chat, sender, "more chatter nobody asked for")

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=muter.id)
    assert entry.last_comment == "more chatter nobody asked for"  # content tracks
    assert MailboxLabel.UNREAD not in entry.labels  # but the mute keeps the badge off


@pytest.mark.asyncio
async def test_archived_row_tracks_content_but_is_not_resurrected():
    # Slack model: archiving affects inbox presence, not the preview. New non-mention
    # activity keeps an archived row's content current but does NOT pull it back into
    # the inbox — only a reaching event (ALL-level, mention, DM) resurrects it.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    observer = await create_user(organization_id=organization.id)
    third = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(observer.id, {Chat.record_type: SubscriptionLevel.RELEVANT_ONLY})

    chat = await create_chat(organization_id=organization.id, title="Team chat")
    for user in (sender, observer, third):
        await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    await _send_and_sync(chat, sender, "@observer look", direct_recipients=[observer])
    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=observer.id)
    entry.label_as_archived()
    await entry.save(update_fields=["labels"])

    await _send_and_sync(chat, sender, "later message")

    await entry.refresh_from_db()
    assert MailboxLabel.INBOX not in entry.labels  # still archived, not resurrected
    assert entry.last_comment == "later message"  # but content tracks


@pytest.mark.asyncio
async def test_sender_row_refreshes_without_unread_bump():
    # The sender's own message refreshes their existing row's preview but never
    # flips it back to unread.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    other = await create_user(organization_id=organization.id)

    # other sends the opening message, creating sender's row (unread).
    chat, _ = await _dm_chat_with_message(organization, other, sender)
    await chat.fetch_related("workspace")
    event = await create_event(chat.workspace, creator_id=other.id, action=EventAction.CHAT_MESSAGE_CREATED)
    await ChatMailboxEntry(chat).sync(event=event, direct_recipients=[])

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=sender.id)
    assert MailboxLabel.UNREAD in entry.labels
    await ChatMailboxEntry(chat).mark_as_read(sender)

    await _send_and_sync(chat, sender, "my reply")

    await entry.refresh_from_db()
    assert entry.last_comment == "my reply"
    assert MailboxLabel.UNREAD not in entry.labels


@pytest.mark.asyncio
async def test_state_driven_recompute_refreshes_existing_below_all_rows():
    # A state-driven recompute (no event — e.g. a collaborator-add or rename) must keep
    # an existing below-ALL row's content current too, not just ALL-level subscribers'.
    # Otherwise the Slack-model "rows track content" guarantee would hold for events but
    # silently break on membership recomputes.
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    observer = await create_user(organization_id=organization.id)
    third = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(observer.id, {Chat.record_type: SubscriptionLevel.RELEVANT_ONLY})

    chat = await create_chat(organization_id=organization.id, title="Team chat")
    for user in (sender, observer, third):
        await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    # A mention gives the below-ALL observer a row.
    await _send_and_sync(chat, sender, "@observer look", direct_recipients=[observer])

    # New activity lands, then only a state-driven recompute runs (no event).
    await create_chat_message(chat_id=chat.id, user_id=sender.id, content="later, via recompute")
    await chat.refresh_from_db()
    await ChatMailboxEntry(chat).sync()

    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=observer.id)
    assert entry.last_comment == "later, via recompute"


@pytest.mark.asyncio
async def test_refresh_does_not_unsnooze_below_all_holder():
    # Snooze-leak fix: un-snoozing happens only on a *reaching* event (the surface path),
    # never on a content-only refresh. A below-ALL holder with a snoozed row sees content
    # track on non-mention activity but stays snoozed. (Under the pre-split code the
    # unsnooze lived in the shared content apply, so this refresh would have cleared it.)
    organization = await create_organization()
    sender = await create_user(organization_id=organization.id)
    observer = await create_user(organization_id=organization.id)
    third = await create_user(organization_id=organization.id)
    await SubscriptionPreference.update_for(observer.id, {Chat.record_type: SubscriptionLevel.RELEVANT_ONLY})

    chat = await create_chat(organization_id=organization.id, title="Team chat")
    for user in (sender, observer, third):
        await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    # A mention gives the below-ALL observer a row; then they snooze it.
    await _send_and_sync(chat, sender, "@observer look", direct_recipients=[observer])
    entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=observer.id)
    entry.snoozed_until = datetime.now(UTC) + timedelta(days=1)
    entry.label_as_archived()
    await entry.save(update_fields=["labels", "snoozed_until"])

    # A non-mention message: observer isn't reached, so the row content refreshes but the
    # snooze is untouched.
    await _send_and_sync(chat, sender, "later, unrelated")

    await entry.refresh_from_db()
    assert entry.last_comment == "later, unrelated"  # content tracked
    assert entry.snoozed_until is not None  # but the snooze was NOT cleared
    assert MailboxLabel.INBOX not in entry.labels  # and it wasn't resurfaced
