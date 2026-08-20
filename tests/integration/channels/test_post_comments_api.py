import pytest

from config.enums import ChannelEventAction, ChannelEventResource
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import (
    create_collaborator,
    create_post,
    create_post_comment,
    create_user,
)


@pytest.mark.asyncio
async def test_created_event_reaches_authoring_users_other_tabs(client: AppClient):
    # The handler intentionally does NOT skip the broadcast's author_id —
    # a user with two tabs open needs tab 2 to receive a CREATED triggered
    # by tab 1. The React reducer dedupes by comment id.
    owner = await client.get_default_user()
    post = await create_post(creator_id=owner.id, organization_id=owner.organization_id)
    await post.fetch_related("workspace")

    topic = Topic("post_comments", post_id=post.id)

    client.current_user = owner
    async with client.connect_channel(topic) as websocket:
        comment = await create_post_comment(post_id=post.id, user_id=owner.id, content="own")
        await topic.broadcast(new_comment_id=str(comment.id), author_id=str(owner.id))

        event = await receive_event(websocket, ChannelEventResource.POST_COMMENT)
        assert event["action"] == ChannelEventAction.CREATED
        assert event["data"]["id"] == str(comment.id)


@pytest.mark.asyncio
async def test_created_event_for_other_user(client: AppClient):
    owner = await client.get_default_user()
    other = await create_user(organization_id=owner.organization_id)
    post = await create_post(creator_id=owner.id, organization_id=owner.organization_id)
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=owner.id, user_id=other.id)

    topic = Topic("post_comments", post_id=post.id)

    client.current_user = other
    async with client.connect_channel(topic) as websocket:
        comment = await create_post_comment(post_id=post.id, user_id=owner.id, content="from owner")
        await topic.broadcast(new_comment_id=str(comment.id), author_id=str(owner.id))

        event = await receive_event(websocket, ChannelEventResource.POST_COMMENT)
        assert event["action"] == ChannelEventAction.CREATED
        assert event["data"]["id"] == str(comment.id)
        assert event["data"]["content"] == "from owner"


@pytest.mark.asyncio
async def test_edited_event(client: AppClient):
    owner = await client.get_default_user()
    other = await create_user(organization_id=owner.organization_id)
    post = await create_post(creator_id=owner.id, organization_id=owner.organization_id)
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=owner.id, user_id=other.id)
    comment = await create_post_comment(post_id=post.id, user_id=owner.id, content="orig")

    topic = Topic("post_comments", post_id=post.id)

    client.current_user = other
    async with client.connect_channel(topic) as websocket:
        comment.content = "edited"
        await comment.save(update_fields=["content"])
        await topic.broadcast(edited_comment_id=str(comment.id), author_id=str(owner.id))

        event = await receive_event(websocket, ChannelEventResource.POST_COMMENT)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["id"] == str(comment.id)
        assert event["data"]["content"] == "edited"


@pytest.mark.asyncio
async def test_deleted_event(client: AppClient):
    owner = await client.get_default_user()
    other = await create_user(organization_id=owner.organization_id)
    post = await create_post(creator_id=owner.id, organization_id=owner.organization_id)
    await post.fetch_related("workspace")
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=owner.id, user_id=other.id)
    comment = await create_post_comment(post_id=post.id, user_id=owner.id, content="x")

    topic = Topic("post_comments", post_id=post.id)

    client.current_user = other
    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(deleted_comment_id=str(comment.id), author_id=str(owner.id))

        event = await receive_event(websocket, ChannelEventResource.POST_COMMENT)
        assert event["action"] == ChannelEventAction.DELETED
        assert event["data"]["id"] == str(comment.id)


@pytest.mark.asyncio
async def test_reaction_toggled_event(client: AppClient):
    owner = await client.get_default_user()
    post = await create_post(creator_id=owner.id, organization_id=owner.organization_id)
    await post.fetch_related("workspace")
    comment = await create_post_comment(post_id=post.id, user_id=owner.id, content="react")

    topic = Topic("post_comments", post_id=post.id)

    # REACTION_TOGGLED does NOT skip the sender (reactions are server-authoritative).
    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(updated_comment_id=str(comment.id))

        event = await receive_event(websocket, ChannelEventResource.POST_COMMENT)
        assert event["action"] == ChannelEventAction.REACTION_TOGGLED
        assert event["data"]["comment_id"] == str(comment.id)
