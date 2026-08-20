import pytest

from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_goal, create_user


@pytest.mark.asyncio
async def test_goals_index_broadcasts_on_crud(client: AppClient):
    """Goal CRUD operations broadcast JSON events to the index channel."""
    user = await client.get_default_user()
    topic = Topic("goals_index", organization_id=user.organization_id, view="active")

    async with client.connect_channel(topic) as websocket:
        # Create
        await client.post("/api/goals", json={"description": "New live goal"})
        response = await receive_event(websocket, ChannelEventResource.GOALS_INDEX)
        assert response["action"] == ChannelEventAction.UPDATED
        assert any("New live goal" in g["description"] for g in response["data"]["goals"])

        # Update
        goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
        await client.patch(f"/api/goals/{goal.id}", json={"description": "Updated live"})
        response = await receive_event(websocket, ChannelEventResource.GOALS_INDEX)
        assert response["action"] == ChannelEventAction.UPDATED

        # Delete
        await client.delete(f"/api/goals/{goal.id}")
        response = await receive_event(websocket, ChannelEventResource.GOALS_INDEX)
        assert response["action"] == ChannelEventAction.UPDATED

    # Authorization: different org cannot subscribe
    other_user = await create_user(name="Other Org User")
    other_topic = Topic("goals_index", organization_id=other_user.organization_id, view="active")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": other_topic.stream,
                "topic_params": other_topic.params,
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED


@pytest.mark.asyncio
async def test_goals_index_close_and_complete_broadcast_to_multiple_views(client: AppClient):
    """Closing/completing a goal broadcasts to both the source and destination views."""
    user = await client.get_default_user()
    active_topic = Topic("goals_index", organization_id=user.organization_id, view="active")
    closed_topic = Topic("goals_index", organization_id=user.organization_id, view="closed")
    completed_topic = Topic("goals_index", organization_id=user.organization_id, view="completed")

    # Close (without completing) broadcasts to active + closed
    goal_to_close = await create_goal(creator_id=user.id, organization_id=user.organization_id)

    async with client.connect_channel(active_topic) as ws_active, client.connect_channel(closed_topic) as ws_closed:
        await client.post(f"/api/goals/{goal_to_close.id}/close")
        active_resp = await receive_event(ws_active, ChannelEventResource.GOALS_INDEX)
        closed_resp = await receive_event(ws_closed, ChannelEventResource.GOALS_INDEX)
        assert active_resp["action"] == ChannelEventAction.UPDATED
        assert closed_resp["action"] == ChannelEventAction.UPDATED

    # Complete broadcasts to active + completed
    goal_to_complete = await create_goal(creator_id=user.id, organization_id=user.organization_id)

    async with (
        client.connect_channel(active_topic) as ws_active,
        client.connect_channel(completed_topic) as ws_completed,
    ):
        await client.post(f"/api/goals/{goal_to_complete.id}/close", json={"is_completed": True})
        active_resp = await receive_event(ws_active, ChannelEventResource.GOALS_INDEX)
        completed_resp = await receive_event(ws_completed, ChannelEventResource.GOALS_INDEX)
        assert active_resp["action"] == ChannelEventAction.UPDATED
        assert completed_resp["action"] == ChannelEventAction.UPDATED
