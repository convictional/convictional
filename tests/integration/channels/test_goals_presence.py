import pytest

from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_goals_presence_broadcast(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    topic = Topic("goals_presence", organization_id=user.organization_id, view="active")

    async with client.connect_channel(topic) as websocket:
        response = await receive_event(websocket, ChannelEventResource.GOALS_PRESENCE)
        assert response["action"] == ChannelEventAction.UPDATED
        assert any(u["id"] == str(user.id) for u in response["data"]["users"])


@pytest.mark.asyncio
async def test_goals_presence_unauthorized(client: AppClient, use_postgres_cache):
    await client.get_default_user()
    other_user = await create_user(name="Other Org User")
    topic = Topic("goals_presence", organization_id=other_user.organization_id, view="active")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {"type": ChannelMessageType.SUBSCRIBE, "topic_stream": topic.stream, "topic_params": topic.params}
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
