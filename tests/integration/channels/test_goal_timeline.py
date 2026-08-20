import asyncio

import pytest
from fastapi import status

from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_goal, create_goal_comment, create_user


@pytest.mark.asyncio
async def test_goal_timeline_broadcasts_on_comment(client: AppClient):
    """Comment creation broadcasts a JSON timeline event to subscribers."""
    user = await client.get_default_user()
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    topic = Topic("goal_timeline", goal_id=goal.id)

    async with client.connect_channel(topic) as websocket:
        await client.post(f"/api/goals/{goal.id}/comments", json={"content": "Live comment"})
        response = await receive_event(websocket, ChannelEventResource.GOAL_TIMELINE)
        assert response["action"] == ChannelEventAction.UPDATED
        assert "events" in response["data"]


@pytest.mark.asyncio
async def test_goal_timeline_single_broadcast_on_combined_comment_patch(client: AppClient):
    """A combined content+closed comment PATCH fires exactly one timeline event, not one per mutation."""
    user = await client.get_default_user()
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Original")
    topic = Topic("goal_timeline", goal_id=goal.id)

    async with client.connect_channel(topic) as websocket:
        response = await client.patch(
            f"/api/goals/{goal.id}/comments/{comment.id}",
            json={"content": "Edited", "closed": True},
        )
        assert response.status_code == status.HTTP_200_OK

        event = await receive_event(websocket, ChannelEventResource.GOAL_TIMELINE)
        assert event["action"] == ChannelEventAction.UPDATED
        # The goal update is broadcast once in the handler rather than once per
        # mutation helper, so no duplicate timeline event follows.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(websocket.receive_json(), timeout=0.5)


@pytest.mark.asyncio
async def test_goal_timeline_and_header_broadcast_on_update(client: AppClient):
    """Goal update sends a JSON timeline event."""
    user = await client.get_default_user()
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    topic = Topic("goal_timeline", goal_id=goal.id)

    async with client.connect_channel(topic) as websocket:
        await client.patch(f"/api/goals/{goal.id}", json={"description": "Updated"})
        response = await receive_event(websocket, ChannelEventResource.GOAL_TIMELINE)
        assert response["action"] == ChannelEventAction.UPDATED
        assert "events" in response["data"]


# Recording a visit no longer broadcasts on goal_timeline — view state rides
# workspace_collaborators now (see tests/integration/channels/test_workspace_collaborators.py).


@pytest.mark.asyncio
async def test_goal_timeline_unauthorized(client: AppClient):
    """Users from a different organization cannot subscribe to the timeline."""
    await client.get_default_user()
    other_user = await create_user(name="Other Org User")
    goal = await create_goal(creator_id=other_user.id, organization_id=other_user.organization_id)
    topic = Topic("goal_timeline", goal_id=goal.id)

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {"type": ChannelMessageType.SUBSCRIBE, "topic_stream": topic.stream, "topic_params": topic.params}
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED


@pytest.mark.asyncio
async def test_goal_timeline_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe with another org's goal_id is rejected by the handler.

    This is the security crux of the unsigned-topic model: with no signature gating the
    attempt, the on_subscribe authorization is the only tenant boundary, so it must reject.
    """
    await client.get_default_user()
    other_user = await create_user(name="Other Org User")
    goal = await create_goal(creator_id=other_user.id, organization_id=other_user.organization_id)

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "goal_timeline",
                "topic_params": {"goal_id": str(goal.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
