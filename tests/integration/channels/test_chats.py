import pytest

from config.enums import ChannelEventAction, ChannelEventResource
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_chat, create_chat_message, create_collaborator, create_user


@pytest.mark.asyncio
async def test_chat_subscribe_and_reject(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    unauthorized_user = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other_user.id)

    topic = Topic("chat", chat_id=chat.id, workspace_id=chat.workspace_id)

    # Member can subscribe
    client.current_user = user
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Other member can subscribe
    client.current_user = other_user
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    # Non-member is rejected
    client.current_user = unauthorized_user
    with pytest.raises(Exception):
        async with client.connect_channel(topic):
            pass

    # Missing chat_id is rejected
    with pytest.raises(Exception):
        async with client.connect_channel(Topic("chat")):
            pass


@pytest.mark.asyncio
async def test_chat_broadcasts(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other_user.id)

    topic = Topic("chat", chat_id=chat.id, workspace_id=chat.workspace_id)

    async with client.connect_channel(topic) as websocket:
        # Typing indicator sends JSON event with user info
        await topic.broadcast(typing_user_ids=[other_user.id])
        response = await receive_event(websocket, ChannelEventResource.CHAT_TYPING)
        assert response["action"] == ChannelEventAction.TYPING
        assert len(response["data"]["users"]) == 1
        assert response["data"]["users"][0]["id"] == str(other_user.id)

        # Empty typing clears the indicator
        await topic.broadcast(typing_user_ids=[])
        response = await receive_event(websocket, ChannelEventResource.CHAT_TYPING)
        assert response["action"] == ChannelEventAction.TYPING
        assert len(response["data"]["users"]) == 0

        # New message from other user is broadcast as JSON event
        message = await create_chat_message(chat_id=chat.id, user_id=other_user.id, content="Hello from broadcast")
        await topic.broadcast(new_message_id=message.id, author_id=other_user.id)

        response = await receive_event(websocket, ChannelEventResource.CHAT_MESSAGE)
        assert response["resource"] == ChannelEventResource.CHAT_MESSAGE
        assert response["action"] == ChannelEventAction.NEW_MESSAGE
        assert response["data"]["content"] == "Hello from broadcast"

        # Own message also sends JSON event for React clients
        own_message = await create_chat_message(chat_id=chat.id, user_id=user.id, content="My own message")
        await topic.broadcast(new_message_id=own_message.id, author_id=user.id)

        response = await receive_event(websocket, ChannelEventResource.CHAT_MESSAGE)
        assert response["resource"] == ChannelEventResource.CHAT_MESSAGE
        assert response["action"] == ChannelEventAction.NEW_MESSAGE
        assert response["data"]["content"] == "My own message"

        # Message update includes edited content
        message.content = "Edited content"
        await message.save()
        await topic.broadcast(updated_message_id=message.id)

        response = await receive_event(websocket, ChannelEventResource.CHAT_MESSAGE)
        assert response["resource"] == ChannelEventResource.CHAT_MESSAGE
        assert response["action"] == ChannelEventAction.UPDATED_MESSAGE
        assert response["data"]["content"] == "Edited content"

        # Message delete sends the deleted message ID
        await topic.broadcast(deleted_message_id=message.id)

        response = await receive_event(websocket, ChannelEventResource.CHAT_MESSAGE)
        assert response["resource"] == ChannelEventResource.CHAT_MESSAGE
        assert response["action"] == ChannelEventAction.DELETED_MESSAGE
        assert response["data"]["id"] == str(message.id)
