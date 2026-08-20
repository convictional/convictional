import uuid
from datetime import UTC, datetime, timedelta

import pytest

from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from integrations.recall_ai.models import (
    RecallAIBotStatusCodes,
    RecallAIMeeting,
    RecallAIPlatform,
)
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_meeting, create_organization, create_user


@pytest.mark.asyncio
async def test_meeting_bot_subscribe_accept_and_reject(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
    )

    topic = Topic("meeting_bot", meeting_id=meeting.id)

    async with client.connect_channel(topic) as websocket:
        assert websocket is not None

    other_org = await create_organization()
    other_user = await create_user(organization_id=other_org.id)
    client.current_user = other_user
    with pytest.raises(Exception):
        async with client.connect_channel(topic):
            pass


@pytest.mark.asyncio
async def test_meeting_bot_broadcast_emits_state(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
    )

    topic = Topic("meeting_bot", meeting_id=meeting.id)
    async with client.connect_channel(topic) as websocket:
        await topic.broadcast()

        response = await receive_event(websocket, ChannelEventResource.MEETING_BOT)
        assert response["action"] == ChannelEventAction.UPDATED
        state = response["data"]["state"]
        assert state["will_record"] is False
        assert state["is_supported_meeting_platform"] is True
        assert state["is_recording_in_progress"] is False
        assert state["is_processing_transcript"] is False

        recall_meeting = await RecallAIMeeting.get(meeting_id=meeting.id)
        recall_meeting.bot_status = RecallAIBotStatusCodes.IN_CALL_RECORDING
        await recall_meeting.save(update_fields=["bot_status"])
        await topic.broadcast()

        response = await receive_event(websocket, ChannelEventResource.MEETING_BOT)
        assert response["data"]["state"]["is_recording_in_progress"] is True


@pytest.mark.asyncio
async def test_meeting_agenda_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe to another org's meeting agenda is rejected at subscribe time."""
    await client.get_default_user()
    other_org = await create_organization()
    other_user = await create_user(organization_id=other_org.id)
    meeting = await create_meeting(
        creator_id=other_user.id,
        organization_id=other_org.id,
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
    )

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "meeting_agenda",
                "topic_params": {"meeting_id": str(meeting.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED


@pytest.mark.asyncio
async def test_meeting_agenda_subscribe_accepts_for_completed_meeting(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=datetime.now(UTC) - timedelta(hours=2),
        scheduled_end_at=datetime.now(UTC) - timedelta(hours=1),
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
    )
    assert meeting.is_completed is True

    topic = Topic("meeting_agenda", meeting_id=meeting.id)
    async with client.connect_channel(topic) as websocket:
        assert websocket is not None


@pytest.mark.asyncio
async def test_meeting_agenda_subscribe_rejects_missing_meeting(client: AppClient):
    await client.get_default_user()

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "meeting_agenda",
                "topic_params": {"meeting_id": str(uuid.uuid4())},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
