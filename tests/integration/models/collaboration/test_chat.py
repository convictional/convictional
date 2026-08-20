from uuid import UUID

import pytest
from tortoise.exceptions import IntegrityError

from app.models.collaboration.workspace import Collaborator, Subscription
from app.models.workspaces.chat import Chat, ChatMailboxEntry, ChatMessage
from config.enums import ChatType, EmailDelivery, ReactionType, SubscriptionLevel
from infra.db import allow_soft_deleted, transaction
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_group,
    create_group_member,
    create_organization,
    create_user,
)


@pytest.mark.asyncio
async def test_chat_creation_and_constraints():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    group = await create_group(organization_id=org.id, name="Engineering")

    # 1:1 chat — no group, no title
    dm = await create_chat(organization_id=org.id, creator_id=user1.id)
    await create_collaborator(workspace_id=dm.workspace_id, user_id=user2.id)
    assert dm.group_id is None
    assert dm.title is None
    assert await Collaborator.filter(workspace_id=dm.workspace_id).count() == 2

    # Group-backed chat
    group_chat = await create_chat(organization_id=org.id, group_id=group.id, title="Engineering")
    assert group_chat.group_id == group.id
    assert group_chat.title == "Engineering"

    # N-party chat
    users = [await create_user(organization_id=org.id) for _ in range(4)]
    multi = await create_chat(organization_id=org.id, title="Project Alpha", creator_id=users[0].id)
    for u in users[1:]:
        await create_collaborator(workspace_id=multi.workspace_id, user_id=u.id)
    assert await Collaborator.filter(workspace_id=multi.workspace_id).count() == 4
    assert multi.group_id is None

    # Collaborator (workspace_id, user_id) uniqueness
    with pytest.raises(IntegrityError):
        await Collaborator.create(workspace_id=dm.workspace_id, user_id=user1.id)

    # One chat per group
    with pytest.raises(IntegrityError):
        await Chat.create(organization_id=org.id, group_id=group.id, creator_id=user1.id)

    # Multiple chats without group is fine
    another = await create_chat(organization_id=org.id)
    assert another.id != dm.id


@pytest.mark.asyncio
async def test_chat_messages_and_reactions():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    chat = await create_chat(organization_id=org.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user1.id)

    # Message creation via CommentMixin
    message = await create_chat_message(chat_id=chat.id, user_id=user1.id, content="<p>Hello</p>")
    assert message.content == "<p>Hello</p>"
    assert message.reactions == {}
    assert message.user_id == user1.id
    assert not message.was_edited

    # Reactions
    message.toggle_reaction(user2.id, ReactionType.THUMBS_UP)
    assert user2.id in message.reactions[ReactionType.THUMBS_UP]
    message.toggle_reaction(user2.id, ReactionType.THUMBS_UP)
    assert user2.id not in message.reactions[ReactionType.THUMBS_UP]


@pytest.mark.asyncio
async def test_group_membership_sync():
    org = await create_organization()
    group = await create_group(organization_id=org.id)
    user = await create_user(organization_id=org.id)

    # No chat for group — adding a group member creates no Collaborator
    await create_group_member(group_id=group.id, user_id=user.id)

    # Create group chat, then add a new member via group membership
    chat = await create_chat(organization_id=org.id, group_id=group.id)
    user2 = await create_user(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user2.id)

    synced = await Collaborator.filter(workspace_id=chat.workspace_id, user_id=user2.id).first()
    assert synced is not None

    # Remove group member — Collaborator is deleted
    await group.remove_member(user2)
    assert await Collaborator.filter(workspace_id=chat.workspace_id, user_id=user2.id).first() is None


@pytest.mark.asyncio
async def test_soft_delete():
    org = await create_organization()
    user = await create_user(organization_id=org.id)
    chat = await create_chat(organization_id=org.id)
    message = await create_chat_message(chat_id=chat.id, user_id=user.id)

    await chat.soft_delete()
    assert await Chat.filter(id=chat.id).first() is None
    async with allow_soft_deleted():
        assert await Chat.filter(id=chat.id).first() is not None

    await message.soft_delete()
    assert await ChatMessage.filter(id=message.id).first() is None
    async with allow_soft_deleted():
        assert await ChatMessage.filter(id=message.id).first() is not None


@pytest.mark.asyncio
async def test_last_message_sync():
    org = await create_organization()
    user = await create_user(organization_id=org.id)
    chat = await create_chat(organization_id=org.id)

    # Empty chat — no last_message
    await chat.refresh_from_db()
    assert chat.last_message_id is None

    # Creating a message sets last_message_id
    msg1 = await create_chat_message(chat_id=chat.id, user_id=user.id, content="First")
    await chat.refresh_from_db()
    assert chat.last_message_id == msg1.id

    # Creating another message updates to the newest
    msg2 = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Second")
    await chat.refresh_from_db()
    assert chat.last_message_id == msg2.id

    # Soft-deleting a non-last message is a no-op
    await msg1.soft_delete()
    await Chat.sync_last_message(chat.id)
    await chat.refresh_from_db()
    assert chat.last_message_id == msg2.id

    # Soft-deleting the last message recalculates to the previous non-deleted one
    msg3 = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Third")
    await chat.refresh_from_db()
    assert chat.last_message_id == msg3.id

    await msg3.soft_delete()
    await Chat.sync_last_message(chat.id)
    await chat.refresh_from_db()
    assert chat.last_message_id == msg2.id

    # Soft-deleting all remaining messages sets last_message_id to None
    await msg2.soft_delete()
    await Chat.sync_last_message(chat.id)
    await chat.refresh_from_db()
    assert chat.last_message_id is None


@pytest.mark.asyncio
async def test_find_or_create_for_group():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)
    group = await create_group(organization_id=org.id, name="Engineering")
    await create_group_member(group_id=group.id, user_id=user1.id)
    await create_group_member(group_id=group.id, user_id=user2.id)
    await create_group_member(group_id=group.id, user_id=user3.id)

    # Creates chat with all group members
    async with transaction() as conn:
        chat, created = await Chat.find_or_create_for_group(group, using_db=conn)
    assert created is True
    assert chat.group_id == group.id
    assert chat.title == "Engineering"
    members = await Collaborator.filter(workspace_id=chat.workspace_id)
    assert {m.user_id for m in members} == {user1.id, user2.id, user3.id}

    # Idempotent — returns existing chat
    async with transaction() as conn:
        same_chat, created = await Chat.find_or_create_for_group(group, using_db=conn)
    assert created is False
    assert same_chat.id == chat.id

    # New group member added after chat creation is synced by signal
    user4 = await create_user(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user4.id)
    assert await Collaborator.filter(workspace_id=chat.workspace_id, user_id=user4.id).exists()


@pytest.mark.asyncio
async def test_my_chats_query():
    org = await create_organization()
    user = await create_user(organization_id=org.id)
    other = await create_user(organization_id=org.id)

    chat1 = await create_chat(organization_id=org.id)
    await create_collaborator(workspace_id=chat1.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat1.workspace_id, user_id=other.id)

    group = await create_group(organization_id=org.id)
    chat2 = await create_chat(organization_id=org.id, group_id=group.id)
    await create_collaborator(workspace_id=chat2.workspace_id, user_id=user.id)

    # Chat user is NOT a member of
    chat3 = await create_chat(organization_id=org.id)
    await create_collaborator(workspace_id=chat3.workspace_id, user_id=other.id)

    my_workspace_ids = {m.workspace_id for m in await Collaborator.filter(user_id=user.id)}
    assert my_workspace_ids == {chat1.workspace_id, chat2.workspace_id}


@pytest.mark.asyncio
async def test_compute_collaborators_hash():
    id1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    id2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

    hash_a = Chat.compute_collaborators_hash([UUID(id1), UUID(id2)])
    hash_b = Chat.compute_collaborators_hash([UUID(id2), UUID(id1)])
    assert hash_a == hash_b, "Hash should be order-independent"
    assert len(hash_a) == 64, "SHA256 hex digest should be 64 chars"

    hash_c = Chat.compute_collaborators_hash([UUID(id1)])
    assert hash_a != hash_c, "Different member sets should produce different hashes"


@pytest.mark.asyncio
async def test_find_existing():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    # No match when nothing exists
    result = await Chat.find_existing([user1.id, user2.id, user3.id], org.id)
    assert result is None

    # Create a multi chat and find it by collaborators_hash
    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_multi(user1, [user2, user3], using_db=conn)

    result = await Chat.find_existing([user1.id, user2.id, user3.id], org.id)
    assert result is not None
    assert result.id == chat.id

    # Order of user_ids doesn't matter
    result = await Chat.find_existing([user3.id, user1.id, user2.id], org.id)
    assert result is not None
    assert result.id == chat.id

    # Different member set returns None
    user4 = await create_user(organization_id=org.id)
    result = await Chat.find_existing([user1.id, user2.id, user4.id], org.id)
    assert result is None

    # Finds a matching group chat
    group = await create_group(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user1.id)
    await create_group_member(group_id=group.id, user_id=user2.id)
    async with transaction() as conn:
        group_chat, _ = await Chat.find_or_create_for_group(group, using_db=conn)
    result = await Chat.find_existing([user1.id, user2.id], org.id)
    assert result is not None
    assert result.id == group_chat.id


@pytest.mark.asyncio
async def test_find_or_create_multi():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    # Creates a new multi chat
    async with transaction() as conn:
        chat, created = await Chat.find_or_create_multi(user1, [user2, user3], using_db=conn)
    assert created is True
    assert chat.collaborators_hash is not None
    assert chat.group_id is None
    members = await Collaborator.filter(workspace_id=chat.workspace_id)
    assert {m.user_id for m in members} == {user1.id, user2.id, user3.id}

    # Deduplicates — returns existing multi chat
    async with transaction() as conn:
        same_chat, created = await Chat.find_or_create_multi(user2, [user1, user3], using_db=conn)
    assert created is False
    assert same_chat.id == chat.id

    # 2-person find_or_create_multi deduplicates with existing DM
    user4 = await create_user(organization_id=org.id)
    async with transaction() as conn:
        dm, _ = await Chat.find_or_create_direct(user1, user4, using_db=conn)
    async with transaction() as conn:
        result, created = await Chat.find_or_create_multi(user1, [user4], using_db=conn)
    assert created is False
    assert result.collaborators_hash == dm.collaborators_hash


@pytest.mark.asyncio
async def test_find_or_create_direct_sets_collaborators_hash():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, created = await Chat.find_or_create_direct(user1, user2, using_db=conn)
    assert created is True
    assert chat.collaborators_hash is not None
    assert chat.collaborators_hash == Chat.compute_collaborators_hash([user1.id, user2.id])


@pytest.mark.asyncio
async def test_add_member_updates_hash():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_direct(user1, user2, using_db=conn)
    original_hash = chat.collaborators_hash

    async with transaction() as conn:
        await chat.add_collaborator(user3, added_by=user1, using_db=conn)

    await chat.refresh_from_db()
    assert chat.collaborators_hash != original_hash
    assert chat.collaborators_hash == Chat.compute_collaborators_hash([user1.id, user2.id, user3.id])
    assert await Collaborator.filter(workspace_id=chat.workspace_id, user_id=user3.id).exists()


@pytest.mark.asyncio
async def test_remove_member():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)
    user4 = await create_user(organization_id=org.id)

    # 4-person chat: removing one leaves 3, chat continues
    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_multi(user1, [user2, user3, user4], using_db=conn)
    async with transaction() as conn:
        result = await chat.remove_collaborator(user4.id, using_db=conn)
    assert result.archived is False
    assert result.conflicting_dm_id is None
    await chat.refresh_from_db()
    assert chat.collaborators_hash == Chat.compute_collaborators_hash([user1.id, user2.id, user3.id])

    # 3-person chat: removing one drops to 2 — morphs to DM (no conflict)
    async with transaction() as conn:
        result = await chat.remove_collaborator(user3.id, using_db=conn)
    assert result.archived is False
    await chat.refresh_from_db()
    assert chat.collaborators_hash == Chat.compute_collaborators_hash([user1.id, user2.id])

    # 3-person chat with existing DM conflict: archives and returns DM id
    async with transaction() as conn:
        multi, _ = await Chat.find_or_create_multi(user1, [user2, user3], using_db=conn)
    # user1+user2 DM already exists from the morph above
    async with transaction() as conn:
        result = await multi.remove_collaborator(user3.id, using_db=conn)
    assert result.archived is True
    assert result.conflicting_dm_id == chat.id
    async with allow_soft_deleted():
        archived = await Chat.filter(id=multi.id).first()
        assert archived is not None
        assert archived.is_deleted

    # Once a chat becomes a DM (2 members), further removal is blocked
    user5 = await create_user(organization_id=org.id)
    user6 = await create_user(organization_id=org.id)
    async with transaction() as conn:
        tiny, _ = await Chat.find_or_create_multi(user5, [user6, user1], using_db=conn)
    async with transaction() as conn:
        await tiny.remove_collaborator(user1.id, using_db=conn)
    # Now 2 remain (user5+user6) — effectively a DM, so removal is blocked
    with pytest.raises(ValueError, match="Cannot remove collaborators from a DM"):
        async with transaction() as conn:
            await tiny.remove_collaborator(user6.id, using_db=conn)


@pytest.mark.asyncio
async def test_resolve_title_multi():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id, name="Alice A")
    user2 = await create_user(organization_id=org.id, name="Bob B")
    user3 = await create_user(organization_id=org.id, name="Charlie C")

    async with transaction() as conn:
        chat, _ = await Chat.find_or_create_multi(user1, [user2, user3], using_db=conn)
    await chat.fetch_related("workspace__collaborators__user")

    entry = ChatMailboxEntry.from_resource(chat)
    title = entry._resolve_title(user1.id)
    assert "Bob" in title
    assert "Charlie" in title
    assert "Alice" not in title

    # With a title set, resolved_title uses it
    chat.title = "Project Chat"
    title = entry._resolve_title(user1.id)
    assert title == "Project Chat"


@pytest.mark.asyncio
async def test_resolved_title_handles_viewer_id_none():
    org = await create_organization()
    alice = await create_user(organization_id=org.id, name="Alice A")
    bob = await create_user(organization_id=org.id, name="Bob B")
    carol = await create_user(organization_id=org.id, name="Carol C")

    async with transaction() as conn:
        dm, _ = await Chat.find_or_create_direct(alice, bob, using_db=conn)
    await dm.fetch_related("workspace__collaborators__user")

    assert dm.resolved_title(alice.id) == "Bob B"
    assert dm.resolved_title(viewer_id=None) == "Alice A and Bob B"

    async with transaction() as conn:
        multi, _ = await Chat.find_or_create_multi(alice, [bob, carol], using_db=conn)
    await multi.fetch_related("workspace__collaborators__user")

    assert multi.resolved_title(viewer_id=None) == "Alice A, Bob B, Carol C"

    self_chat, _ = await Chat.find_or_create_self(alice)
    await self_chat.fetch_related("workspace__collaborators__user")
    assert self_chat.resolved_title(viewer_id=None) == "Note to self"

    dm.title = "Custom Title"
    assert dm.resolved_title(viewer_id=None) == "Custom Title"


@pytest.mark.asyncio
async def test_find_or_create_self():
    org = await create_organization()
    user = await create_user(organization_id=org.id, name="Jake")

    chat, created = await Chat.find_or_create_self(user)
    assert created is True
    assert chat.group_id is None
    assert chat.collaborators_hash == Chat.compute_collaborators_hash([user.id])
    members = await Collaborator.filter(workspace_id=chat.workspace_id)
    assert {m.user_id for m in members} == {user.id}

    # Dedupe — second call returns the same chat
    same_chat, created = await Chat.find_or_create_self(user)
    assert created is False
    assert same_chat.id == chat.id

    # Type and title
    await chat.fetch_related("workspace__collaborators__user")
    assert chat.type == ChatType.SELF
    assert chat.type.is_self is True
    assert chat.resolved_title(user.id) == "Note to self"


@pytest.mark.asyncio
async def test_chat_skips_email_delivery():
    assert Chat.email_delivery == EmailDelivery.SKIP
    assert Chat.email_delivery.is_skip is True
    assert Chat.email_delivery.is_send is False


@pytest.mark.asyncio
async def test_upsert_collaborators_writes_no_subscription_rows():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    # DM
    dm, _ = await Chat.find_or_create_direct(user1, user2)
    assert await Collaborator.filter(workspace_id=dm.workspace_id).count() == 2
    assert await Subscription.filter(workspace_id=dm.workspace_id).count() == 0

    # Multi
    multi, _ = await Chat.find_or_create_multi(user1, [user2, user3])
    assert await Collaborator.filter(workspace_id=multi.workspace_id).count() == 3
    assert await Subscription.filter(workspace_id=multi.workspace_id).count() == 0

    # Group
    group = await create_group(organization_id=org.id)
    await create_group_member(group_id=group.id, user_id=user1.id)
    await create_group_member(group_id=group.id, user_id=user2.id)
    group_chat, _ = await Chat.find_or_create_for_group(group)
    assert await Collaborator.filter(workspace_id=group_chat.workspace_id).count() == 2
    assert await Subscription.filter(workspace_id=group_chat.workspace_id).count() == 0


@pytest.mark.asyncio
async def test_upsert_collaborators_is_idempotent_on_re_run():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    chat, _ = await Chat.find_or_create_direct(user1, user2)

    # Re-running with the same users does not duplicate Collaborator rows.
    await Chat.upsert_collaborators(chat.workspace_id, [user1.id, user2.id], user1.id)

    collab_count = await Collaborator.filter(workspace_id=chat.workspace_id).count()
    assert collab_count == 2


@pytest.mark.asyncio
async def test_upsert_collaborators_does_not_touch_existing_subscription_row():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)

    chat, _ = await Chat.find_or_create_direct(user1, user2)

    # User2 explicitly opts out of this chat.
    await chat.workspace.unsubscribe(user2.id)

    # Re-running upsert_collaborators must not modify or remove the explicit row.
    await Chat.upsert_collaborators(chat.workspace_id, [user1.id, user2.id], user1.id)

    user2_sub = await Subscription.get(workspace_id=chat.workspace_id, subscriber_id=user2.id)
    assert user2_sub.level == SubscriptionLevel.RELEVANT_ONLY


@pytest.mark.asyncio
async def test_delete_collaborator_preserves_subscription_rows():
    org = await create_organization()
    user1 = await create_user(organization_id=org.id)
    user2 = await create_user(organization_id=org.id)
    user3 = await create_user(organization_id=org.id)

    chat, _ = await Chat.find_or_create_multi(user1, [user2, user3])
    await chat.workspace.subscribe(user3.id)

    await Chat.delete_collaborator(chat.workspace_id, user3.id)

    assert not await Collaborator.filter(workspace_id=chat.workspace_id, user_id=user3.id).exists()
    user3_sub = await Subscription.get(workspace_id=chat.workspace_id, subscriber_id=user3.id)
    assert user3_sub.level == SubscriptionLevel.ALL
