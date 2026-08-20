import pytest

from config.enums import ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_message


@pytest.mark.asyncio
async def test_workspace_events_subscribe_rejects_deleted_resource_cleanly(client: AppClient):
    """Subscribing to workspace_events for a workspace whose resource was soft-deleted rejects
    with the handler's own reason, not the fail-closed guard. The workspace row outlives its
    soft-deleted resource, so authorization must fail cleanly instead of raising DoesNotExist
    out of the handler (which would surface a spurious error to Sentry)."""
    user = await client.get_default_user()
    message = await create_email_message(creator_id=user.id)
    await message.fetch_related("thread")
    topic = Topic("workspace_events", workspace_id=message.thread.workspace_id)

    # Live resource: authorization succeeds and the subscription is confirmed.
    async with client.connect_channel(topic):
        pass

    # Soft-delete the underlying resource; the workspace row remains.
    await message.thread.soft_delete()

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": topic.stream,
                "topic_params": topic.params,
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
        # The handler decided (called reject itself); it did not fall through to the
        # fail-closed guard, whose reason would be "subscription not authorized".
        assert response["error"] == "Unauthorized access to workspace events."
