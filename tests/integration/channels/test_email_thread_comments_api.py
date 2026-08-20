import pytest

from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import (
    create_collaborator,
    create_email_thread,
    create_email_thread_comment,
    create_user,
)


@pytest.mark.asyncio
async def test_email_thread_comments_access_control(client: AppClient):
    owner = await client.get_default_user()
    collaborator = await create_user(organization_id=owner.organization_id)
    non_collaborator = await create_user(organization_id=owner.organization_id)

    thread = await create_email_thread(creator_id=owner.id, organization_id=owner.organization_id)
    await create_collaborator(
        user_id=collaborator.id, workspace_id=thread.workspace_id, organization_id=owner.organization_id
    )

    topic = Topic("email_thread_comments", email_thread_id=thread.id)

    # Owner can subscribe
    client.current_user = owner
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Collaborator can subscribe
    client.current_user = collaborator
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Non-collaborator is rejected
    client.current_user = non_collaborator
    with pytest.raises(Exception):
        async with client.connect_channel(topic):
            pass

    # Missing email_thread_id parameter is rejected
    with pytest.raises(Exception):
        async with client.connect_channel(Topic("email_thread_comments")):
            pass


@pytest.mark.asyncio
async def test_email_thread_comments_subscribe_unauthorized_cross_org(client: AppClient):
    await client.get_default_user()
    other = await create_user(name="Other Org User")
    thread = await create_email_thread(creator_id=other.id, organization_id=other.organization_id)

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "email_thread_comments",
                "topic_params": {"email_thread_id": str(thread.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED


@pytest.mark.asyncio
async def test_email_thread_comments_typing_event(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    thread = await create_email_thread(creator_id=user.id, organization_id=user.organization_id)
    topic = Topic("email_thread_comments", email_thread_id=thread.id)

    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(typing_user_ids=[other_user.id])

        event = await receive_event(websocket, ChannelEventResource.EMAIL_THREAD_COMMENT)
        assert event["action"] == ChannelEventAction.TYPING
        assert len(event["data"]["typing_users"]) == 1
        assert event["data"]["typing_users"][0]["id"] == str(other_user.id)


@pytest.mark.asyncio
async def test_email_thread_comments_update_event(client: AppClient):
    user = await client.get_default_user()
    thread = await create_email_thread(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, content="Original")
    topic = Topic("email_thread_comments", email_thread_id=thread.id)

    async with client.connect_channel(topic) as websocket:
        comment.content = "**Edited**"
        await comment.save(update_fields=["content"])
        await topic.broadcast(edited_comment_id=str(comment.id))

        event = await receive_event(websocket, ChannelEventResource.EMAIL_THREAD_COMMENT)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["comment"]["id"] == str(comment.id)
        assert event["data"]["comment"]["content"] == "**Edited**"


@pytest.mark.asyncio
async def test_email_thread_comments_removed_event(client: AppClient):
    user = await client.get_default_user()
    thread = await create_email_thread(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, content="X")
    topic = Topic("email_thread_comments", email_thread_id=thread.id)

    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(deleted_comment_id=str(comment.id))

        event = await receive_event(websocket, ChannelEventResource.EMAIL_THREAD_COMMENT)
        assert event["action"] == ChannelEventAction.REMOVED
        assert event["data"]["comment_id"] == str(comment.id)


@pytest.mark.asyncio
async def test_email_thread_comments_created_event(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    thread = await create_email_thread(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_email_thread_comment(email_thread_id=thread.id, user_id=other_user.id, content="Brand new")
    topic = Topic("email_thread_comments", email_thread_id=thread.id)

    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(new_comment_id=str(comment.id), author_id=str(other_user.id))

        event = await receive_event(websocket, ChannelEventResource.EMAIL_THREAD_COMMENT)
        assert event["action"] == ChannelEventAction.CREATED
        assert event["data"]["comment"]["id"] == str(comment.id)
        assert event["data"]["comment"]["content"] == "Brand new"


@pytest.mark.asyncio
async def test_email_thread_comments_created_event_carries_reply_to(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(name="Quoted", organization_id=user.organization_id)
    thread = await create_email_thread(creator_id=user.id, organization_id=user.organization_id)
    parent = await create_email_thread_comment(email_thread_id=thread.id, user_id=other_user.id, content="Original")
    reply = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, reply_to_id=parent.id)
    topic = Topic("email_thread_comments", email_thread_id=thread.id)

    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(new_comment_id=str(reply.id), author_id=str(other_user.id))

        event = await receive_event(websocket, ChannelEventResource.EMAIL_THREAD_COMMENT)
        assert event["action"] == ChannelEventAction.CREATED
        assert event["data"]["comment"]["reply_to"]["id"] == str(parent.id)
        assert event["data"]["comment"]["reply_to"]["user_name"] == "Quoted"
        assert event["data"]["comment"]["reply_to"]["is_deleted"] is False


@pytest.mark.asyncio
async def test_email_thread_comments_actor_skip_matrix(client: AppClient):
    # The actor (whoever made the change) should NOT receive CREATED/UPDATED/REMOVED
    # for their own action — their local UI already reflects it. REACTION_TOGGLED is
    # the exception: it IS sent to the actor so their other tabs stay in sync.
    actor = await client.get_default_user()
    thread = await create_email_thread(creator_id=actor.id, organization_id=actor.organization_id)
    comment = await create_email_thread_comment(email_thread_id=thread.id, user_id=actor.id, content="Mine")
    topic = Topic("email_thread_comments", email_thread_id=thread.id)

    async with client.connect_channel(topic) as websocket:
        # CREATED, UPDATED (content edit), and REMOVED all carry the actor's author_id
        # and are skipped. The first event the actor receives is the reaction toggle
        # (no author_id), proving all three skip paths dropped their events.
        await topic.broadcast(new_comment_id=str(comment.id), author_id=str(actor.id))
        await topic.broadcast(edited_comment_id=str(comment.id), author_id=str(actor.id))
        await topic.broadcast(deleted_comment_id=str(comment.id), author_id=str(actor.id))

        # Reaction toggle carries no author_id and is delivered to the actor.
        await topic.broadcast(updated_comment_id=str(comment.id))

        event = await receive_event(websocket, ChannelEventResource.EMAIL_THREAD_COMMENT)
        assert event["action"] == ChannelEventAction.REACTION_TOGGLED
        assert event["data"]["comment_id"] == str(comment.id)
