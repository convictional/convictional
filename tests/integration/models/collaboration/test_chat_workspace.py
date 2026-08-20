import pytest

from app.models.collaboration.workspace import (
    Collaborator,
    Event,
    SubscriberResolver,
    Subscription,
    Visit,
    Workspace,
    workspace_registry,
)
from app.models.workspaces.chat import Chat, ChatMailboxEntry, ChatMessage
from config.enums import CollaboratorStatus, EventAction, Sharing
from infra.db import transaction
from tests.helpers.factories import (
    create_chat,
    create_group,
    create_group_member,
    create_organization,
    create_user,
)


@pytest.mark.asyncio
async def test_chat_registered_in_workspace_registry():
    assert "Chat" in workspace_registry
    assert workspace_registry["Chat"] is Chat


@pytest.mark.asyncio
async def test_new_chat_has_workspace():
    org = await create_organization()
    creator = await create_user(organization_id=org.id)
    chat = await create_chat(organization_id=org.id, creator_id=creator.id)

    assert chat.workspace_id is not None
    workspace = await Workspace.get(id=chat.workspace_id)
    assert str(workspace.resource_gid) == f"gid://convictional/Chat/{chat.id}"
    assert workspace.organization_id == org.id


@pytest.mark.asyncio
async def test_workspace_resource_resolves_to_chat():
    org = await create_organization()
    creator = await create_user(organization_id=org.id)
    chat = await create_chat(organization_id=org.id, creator_id=creator.id)

    workspace = await Workspace.get(id=chat.workspace_id)
    resource = await workspace.fetch_resource()
    assert resource.id == chat.id


@pytest.mark.asyncio
async def test_find_or_create_direct_sets_workspace_and_creator():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, created = await Chat.find_or_create_direct(user1, user2, using_db=conn)

    assert created is True
    assert chat.workspace_id is not None
    assert chat.creator_id == user1.id
    assert chat.title is None  # DMs have no title

    workspace = await Workspace.get(id=chat.workspace_id)
    assert str(workspace.resource_gid) == f"gid://convictional/Chat/{chat.id}"


@pytest.mark.asyncio
async def test_find_or_create_multi_sets_workspace_and_creator():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, created = await Chat.find_or_create_multi(user1, [user2, user3], using_db=conn)

    assert created is True
    assert chat.workspace_id is not None
    assert chat.creator_id == user1.id
    assert chat.title is None  # unnamed multi chats have no title

    workspace = await Workspace.get(id=chat.workspace_id)
    assert str(workspace.resource_gid) == f"gid://convictional/Chat/{chat.id}"


@pytest.mark.asyncio
async def test_find_or_create_for_group_sets_workspace_creator_and_title():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    group = await create_group(organization_id=org.id, name="Engineering")
    await create_group_member(group_id=group.id, user_id=user1.id)
    await create_group_member(group_id=group.id, user_id=user2.id)

    async with transaction() as conn:
        chat, created = await Chat.find_or_create_for_group(group, creator_user_id=user1.id, using_db=conn)

    assert created is True
    assert chat.workspace_id is not None
    assert chat.creator_id == user1.id
    assert chat.title == "Engineering"

    workspace = await Workspace.get(id=chat.workspace_id)
    assert str(workspace.resource_gid) == f"gid://convictional/Chat/{chat.id}"


@pytest.mark.asyncio
async def test_workspace_is_private():
    org = await create_organization()
    creator = await create_user(organization_id=org.id)
    chat = await create_chat(organization_id=org.id, creator_id=creator.id)

    workspace = await Workspace.get(id=chat.workspace_id)
    assert workspace.sharing == Sharing.PRIVATE


@pytest.mark.asyncio
async def test_find_or_create_for_group_fallback_creator():
    """When no creator_user_id is passed, falls back to first group member."""
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    group = await create_group(organization_id=org.id, name="Solo")
    gm = await create_group_member(group_id=group.id, user_id=user1.id)

    async with transaction() as conn:
        chat, created = await Chat.find_or_create_for_group(group, using_db=conn)

    assert created is True
    assert chat.creator_id == gm.user_id


# Chat membership flows through Collaborator — ChatMember was removed in PR 5.
# These tests lock in that every write path maintains Collaborator correctly.


async def _collab_user_ids(workspace_id):
    rows = await (
        Collaborator.unscoped.get_queryset().filter(workspace_id=workspace_id).values_list("user_id", flat=True)
    )
    return set(rows)


@pytest.mark.asyncio
async def test_find_or_create_direct_dual_writes_collaborators():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_direct(user1, user2, using_db=conn)

    assert await _collab_user_ids(chat.workspace_id) == {user1.id, user2.id}
    collabs = await Collaborator.unscoped.get_queryset().filter(workspace_id=chat.workspace_id)
    assert all(c.status == CollaboratorStatus.APPROVED for c in collabs)
    assert all(c.added_by_id == user1.id for c in collabs)


@pytest.mark.asyncio
async def test_find_or_create_multi_dual_writes_collaborators():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_multi(user1, [user2, user3], using_db=conn)

    assert await _collab_user_ids(chat.workspace_id) == {user1.id, user2.id, user3.id}
    collabs = await Collaborator.unscoped.get_queryset().filter(workspace_id=chat.workspace_id)
    assert all(c.added_by_id == user1.id for c in collabs)


@pytest.mark.asyncio
async def test_find_or_create_for_group_dual_writes_collaborators():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    group = await create_group(organization_id=org.id, name="Engineering")
    await create_group_member(group_id=group.id, user_id=user1.id)
    await create_group_member(group_id=group.id, user_id=user2.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_for_group(group, creator_user_id=user1.id, using_db=conn)

    assert await _collab_user_ids(chat.workspace_id) == {user1.id, user2.id}
    collabs = await Collaborator.unscoped.get_queryset().filter(workspace_id=chat.workspace_id)
    assert all(c.added_by_id == user1.id for c in collabs)


@pytest.mark.asyncio
async def test_add_member_dual_writes_collaborator():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_direct(user1, user2, using_db=conn)

    async with transaction() as conn:
        await chat.add_collaborator(user3, added_by=user1, using_db=conn)

    assert await _collab_user_ids(chat.workspace_id) == {user1.id, user2.id, user3.id}
    collab = await Collaborator.unscoped.get_queryset().filter(workspace_id=chat.workspace_id, user_id=user3.id).get()
    assert collab.added_by_id == user1.id
    assert collab.status == CollaboratorStatus.APPROVED


@pytest.mark.asyncio
async def test_remove_member_deletes_collaborator():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)
    user4 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_multi(user1, [user2, user3, user4], using_db=conn)

    async with transaction() as conn:
        result = await chat.remove_collaborator(user4.id, using_db=conn)
    assert result.archived is False

    assert await _collab_user_ids(chat.workspace_id) == {user1.id, user2.id, user3.id}
    # user4's Collaborator row is hard-deleted on remove_member


@pytest.mark.asyncio
async def test_group_member_sync_signal_dual_writes_collaborator():
    org = await create_organization()
    group = await create_group(organization_id=org.id, name="Ops")
    user1 = await create_user(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user1.id)

    chat = await create_chat(organization_id=org.id, group_id=group.id, creator_id=user1.id)

    # Baseline: creator is auto-added as Collaborator when the Workspace is saved.
    assert await _collab_user_ids(chat.workspace_id) == {user1.id}

    # Adding a GroupMember syncs a Collaborator via signal
    user2 = await create_user(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user2.id)

    assert await _collab_user_ids(chat.workspace_id) == {user1.id, user2.id}

    # Removing the GroupMember removes the Collaborator for that user
    await group.remove_member(user2)
    assert await _collab_user_ids(chat.workspace_id) == {user1.id}


@pytest.mark.asyncio
async def test_duplicate_dual_write_is_idempotent():
    """Rerunning a dual-write path against an existing Collaborator must not raise."""
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_direct(user1, user2, using_db=conn)

    # Re-running the helper shouldn't violate the unique (workspace_id, user_id) constraint.
    async with transaction() as conn:
        await Chat.upsert_collaborators(chat.workspace_id, [user1.id], user2.id, using_db=conn)
        await Chat.upsert_collaborators(chat.workspace_id, [user1.id], user2.id, using_db=conn)

    assert await _collab_user_ids(chat.workspace_id) == {user1.id, user2.id}


# Events, Visits, and Subscriptions are the workspace-level plumbing introduced in PR 3.
# Chat message and member activity must produce Event rows so Visit-based unread tracking
# lines up with every other workspace resource.


async def _events_for(workspace_id):
    return await Event.filter(workspace_id=workspace_id).order_by("created_at").all()


@pytest.mark.asyncio
async def test_add_member_emits_event_without_subscription_row():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_direct(user1, user2, using_db=conn)

    async with transaction() as conn:
        await chat.add_collaborator(user3, added_by=user1, using_db=conn)

    events = await Event.filter(workspace_id=chat.workspace_id, action=EventAction.CHAT_COLLABORATOR_ADDED).all()
    assert len(events) == 1
    assert events[0].creator_id == user1.id
    assert events[0].details.get("user_id") == str(user3.id)

    # Adding a collaborator no longer writes a subscription row; effective
    # subscription resolves via the user's global preference at delivery time.
    assert await Subscription.get_or_none(workspace_id=chat.workspace_id, subscriber_id=user3.id) is None


@pytest.mark.asyncio
async def test_remove_member_emits_event():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_multi(user1, [user2, user3], using_db=conn)

    async with transaction() as conn:
        await chat.remove_collaborator(user3.id, removed_by_id=user1.id, using_db=conn)

    events = await Event.filter(workspace_id=chat.workspace_id, action=EventAction.CHAT_COLLABORATOR_REMOVED).all()
    assert len(events) == 1
    assert events[0].creator_id == user1.id
    assert events[0].details.get("user_id") == str(user3.id)


@pytest.mark.asyncio
async def test_group_sync_signal_emits_member_events():
    org = await create_organization()
    group = await create_group(organization_id=org.id, name="Ops")
    user1 = await create_user(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user1.id)

    chat = await create_chat(organization_id=org.id, group_id=group.id, creator_id=user1.id)

    user2 = await create_user(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user2.id)

    added = await Event.filter(workspace_id=chat.workspace_id, action=EventAction.CHAT_COLLABORATOR_ADDED).all()
    assert any(e.details.get("user_id") == str(user2.id) and e.details.get("via") == "group_sync" for e in added)

    await group.remove_member(user2)
    removed = await Event.filter(workspace_id=chat.workspace_id, action=EventAction.CHAT_COLLABORATOR_REMOVED).all()
    assert any(e.details.get("user_id") == str(user2.id) and e.details.get("via") == "group_sync" for e in removed)


@pytest.mark.asyncio
async def test_chat_creator_has_no_auto_subscription_row():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_direct(user1, user2, using_db=conn)

    assert await Subscription.get_or_none(workspace_id=chat.workspace_id, subscriber_id=user1.id) is None
    await chat.fetch_related("workspace")
    assert user1 in await SubscriberResolver(workspace=chat.workspace).resolve()


@pytest.mark.asyncio
async def test_mark_as_read_dual_writes_visit():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_direct(user1, user2, using_db=conn)

    # Seed an event so there's a last_event_id for Visit to anchor on.
    async with transaction() as conn:
        message = await ChatMessage.create(chat_id=chat.id, user_id=user2.id, content="hi", using_db=conn)
        async with chat.workspace.record(
            EventAction.CHAT_MESSAGE_CREATED,
            recordable=message,
            creator_id=user2.id,
            using_db=conn,
        ):
            pass

    # Prime the mailbox entry so mark_as_read can find one.
    await chat.fetch_related("workspace__collaborators__user", "last_message__user")
    entry_helper = ChatMailboxEntry(chat=chat)
    await entry_helper.sync()

    await entry_helper.mark_as_read(user1)

    visit = await Visit.get_or_none(workspace_id=chat.workspace_id, user_id=user1.id)
    assert visit is not None
    assert visit.last_event_id is not None

    latest_event = await Event.filter(workspace_id=chat.workspace_id).order_by("-created_at").first()
    assert latest_event is not None
    assert visit.last_event_id == latest_event.id
