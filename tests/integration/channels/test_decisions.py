import pytest

from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_post, create_post_comment


@pytest.mark.asyncio
async def test_decision_create_and_delete_broadcast_decisions_changed(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id)
    topic = Topic("workspace_events", workspace_id=post.workspace_id)

    async with client.connect_channel(topic) as websocket:
        response = await client.post(
            f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
        )
        decision_id = response.json()["id"]

        # Due to eventual consistency, send pong to trigger the queue to flush.
        pong = {"type": ChannelMessageType.PONG, "data": "test"}
        await websocket.send_json(pong)

        # No sender-skip: the acting tab gets the signal too.
        event = await receive_event(websocket, ChannelEventResource.DECISION)
        assert event["action"] == ChannelEventAction.DECISIONS_CHANGED
        assert event["data"]["actor_id"] == str(creator.id)

        await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision_id}")
        await websocket.send_json(pong)

        event = await receive_event(websocket, ChannelEventResource.DECISION)
        assert event["action"] == ChannelEventAction.DECISIONS_CHANGED
