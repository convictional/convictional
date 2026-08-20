from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from config.enums import Integration
from integrations.recall_ai.client import RecallAIClient
from integrations.recall_ai.models import (
    RecallAICalendarPreferences,
    RecallAICalendarUser,
    RecallAIChatMessages,
)
from integrations.recall_ai.transcript import RecallAITranscript
from tests.helpers.factories import create_user

# NOTE: All tests in this file require the RECALL_AI_API_KEY environment variable to be set
# See docs/integrations.md for more information on Recall AI configuration


@pytest.fixture(scope="function")
def recall_client(monkeypatch):
    client = RecallAIClient()
    # NOTE:if you need to re-record casettes, you will need to set the token to a valid calendar auth token
    # To do this, you can grab your user ID from production and use the Recall API explorer to get a token
    # https://docs.recall.ai/reference/calendar_authenticate_create
    # The valid token should not be committed to Git!
    mock_calendar_auth_token = AsyncMock(return_value={"token": "test"})
    monkeypatch.setattr(client, "_calendar_auth", mock_calendar_auth_token)
    return client


@pytest.fixture(scope="function")
def recall_user_id():
    # NOTE: When re-recording calendar tests, change this to the same user ID you used to get the token
    return UUID("65e8cc1e-a789-4af6-a287-1908d927ff67")


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_recall_client_create_google_meet_bot(recall_client: RecallAIClient):
    # Note: When re-recording this test, you will need to use a new meeting URL
    meeting_url = "https://meet.google.com/azj-itsc-jpo"
    response = await recall_client.create_bot(meeting_url)
    assert response
    assert isinstance(response, dict)

    assert "id" in response.keys()
    response_meeting_url = response.get("meeting_url")
    assert response_meeting_url
    assert isinstance(response_meeting_url, dict)
    assert response_meeting_url.get("platform", "") == "google_meet"


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_recall_client_schedule_google_meet_bot(recall_client: RecallAIClient):
    # Note: When re-recording this test, you will need to use a new meeting URL
    meeting_url = "https://meet.google.com/azj-itsc-jpp"
    join_at = datetime.now() + timedelta(hours=20)
    response = await recall_client.create_scheduled_bot(meeting_url, join_at)
    assert response
    assert isinstance(response, dict)

    assert "id" in response.keys()


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_recall_client_get_transcript(recall_client: RecallAIClient):
    bot_id = "a4f9a809-8798-418f-b8ab-585c32267f44"
    transcript = await recall_client.get_bot_transcript(bot_id)
    assert transcript

    assert isinstance(transcript, RecallAITranscript)
    assert len(transcript.chunks) > 0
    assert transcript.chunks[0].speaker in transcript.to_text()


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_recall_client_get_chat_messages(recall_client: RecallAIClient):
    bot_id = "80f4b607-1477-4c07-9962-1c4b8378048b"
    response = await recall_client.get_meeting_chat_messages(bot_id)
    assert response

    assert isinstance(response, RecallAIChatMessages)
    assert len(response.results) > 0


@pytest.mark.asyncio
async def test_transcript_to_text():
    example = [
        {
            "words": [
                {
                    "text": "two three",
                    "start_timestamp": 0.0,
                    "end_timestamp": 0.3142361342906952,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Dana Holbrook",
            "speaker_id": 100,
            "language": "en-us",
        },
        {
            "words": [
                {
                    "text": "four",
                    "start_timestamp": 0.6260281801223755,
                    "end_timestamp": 1.463371992111206,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Dana Holbrook",
            "speaker_id": 100,
            "language": "en-us",
        },
        {
            "words": [
                {
                    "text": "five six seven eight",
                    "start_timestamp": 1.8732972145080566,
                    "end_timestamp": 6.3268351554870605,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Dana Holbrook",
            "speaker_id": 100,
            "language": "en-us",
        },
        {
            "words": [
                {
                    "text": "nine",
                    "start_timestamp": 6.6361823081970215,
                    "end_timestamp": 7.458316326141357,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Dana Holbrook",
            "speaker_id": 100,
            "language": "en-us",
        },
        {
            "words": [
                {
                    "text": "10",
                    "start_timestamp": 8.479044914245605,
                    "end_timestamp": 9.72338581085205,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Dana Holbrook",
            "speaker_id": 100,
            "language": "en-us",
        },
        {
            "words": [
                {
                    "text": "You know how to count!",
                    "start_timestamp": 11.479044914245605,
                    "end_timestamp": 9.72338581085205,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Another Speaker",
            "speaker_id": 100,
            "language": "en-us",
        },
    ]
    transcript = RecallAITranscript(chunks=example)

    expected = [
        "Dana Holbrook: two three four five six seven eight nine 10",
        "Another Speaker: You know how to count!",
    ]
    assert transcript.to_text() == "\n".join(expected)


@pytest.mark.asyncio
async def test_transcript_without_speaker_id():
    chunks = [
        {
            "words": [
                {
                    "text": "Hello everyone",
                    "start_timestamp": 0.0,
                    "end_timestamp": 1.0,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Alice",
            "language": "en-us",
        },
        {
            "words": [
                {
                    "text": "Welcome to the meeting",
                    "start_timestamp": 1.5,
                    "end_timestamp": 3.0,
                    "language": None,
                    "confidence": None,
                }
            ],
            "speaker": "Bob",
            "language": "en-us",
        },
    ]
    transcript = RecallAITranscript(chunks=chunks)

    assert transcript.to_text() == "Alice: Hello everyone\nBob: Welcome to the meeting"
    assert transcript.chunks[0].speaker_id is None
    assert transcript.chunks[1].speaker_id is None


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_recall_get_calendar_user(recall_client: RecallAIClient, recall_user_id: UUID):
    user = await create_user(id=recall_user_id)
    assert not user.is_integrated_with(Integration.RECALL_AI_CALENDAR)

    recall_ai_user = await recall_client.get_calendar_user(user_id=recall_user_id)
    assert recall_ai_user
    assert isinstance(recall_ai_user, RecallAICalendarUser)

    await user.refresh_from_db()
    assert user.is_integrated_with(Integration.RECALL_AI_CALENDAR)


@pytest.mark.requires_config
@pytest.mark.asyncio
async def test_updating_user_recording_preferences(recall_client: RecallAIClient, recall_user_id: UUID):
    user = await create_user(id=recall_user_id)
    assert user
    assert user.id == recall_user_id

    calendar_user = await recall_client.get_calendar_user(user_id=recall_user_id)
    assert calendar_user
    await calendar_user.save()
    initial_preferences = calendar_user.preference_name

    await recall_client.update_calendar_user_recording_preferences(
        user_id=user.id, recording_preference=RecallAICalendarPreferences.ALL
    )
    await calendar_user.refresh_from_db()
    assert calendar_user.preference_name == RecallAICalendarPreferences.ALL

    await recall_client.update_calendar_user_recording_preferences(
        user_id=user.id, recording_preference=RecallAICalendarPreferences.NONE
    )
    await calendar_user.refresh_from_db()
    assert calendar_user.preference_name == RecallAICalendarPreferences.NONE

    # Reset the user's preferences
    if initial_preferences:
        await recall_client.update_calendar_user_recording_preferences(
            user_id=user.id, recording_preference=initial_preferences
        )
