"""JSON-mode channel handler tests for the research_progress stream."""

import pytest

from config.enums import ChannelEventAction, ChannelEventResource
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_research_question


@pytest.mark.asyncio
async def test_research_progress_broadcast_emits_event(client: AppClient):
    user = await client.get_default_user()
    topic = Topic("research_progress", user_id=user.id)

    async with client.connect_channel(topic) as websocket:
        question = await create_research_question(creator_id=user.id, title="Hello")

        event = await receive_event(websocket, ChannelEventResource.RESEARCH_PROGRESS)
        assert event["action"] == ChannelEventAction.UPDATED
        assert any(
            q["id"] == str(question.id) and q["title"] == "Hello" for q in event["data"]["pending_research_questions"]
        )
