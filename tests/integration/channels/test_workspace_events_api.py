import pytest

from app.models.workspaces.email.thread import EmailThreadComment
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType, EventAction
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_collaborator, create_email_message, create_user


@pytest.mark.asyncio
async def test_workspace_events_json_broadcast(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    message = await create_email_message(creator_id=user.id)
    await message.fetch_related("thread", "thread__workspace")
    await create_collaborator(
        user_id=other_user.id,
        workspace_id=message.thread.workspace_id,
        organization_id=user.organization_id,
    )
    topic = Topic("workspace_events", workspace_id=message.thread.workspace_id)

    async with client.connect_channel(topic) as websocket:
        comment = EmailThreadComment(email_thread_id=message.thread.id, user_id=user.id, content="JSON event")
        async with message.thread.workspace.record(
            EventAction.COMMENTED, recordable=comment, creator_id=user.id
        ) as recording:
            await comment.save(recording.using_db)

        # Trigger the channel queue to flush.
        pong = {"type": ChannelMessageType.PONG, "data": "test"}
        await websocket.send_json(pong)

        event = await receive_event(websocket, ChannelEventResource.WORKSPACE_EVENT)
        assert event["action"] == ChannelEventAction.ADDED
        assert event["data"]["recordable_type"] == "EmailThreadComment"
        assert event["data"]["event_action"] == EventAction.COMMENTED.value
