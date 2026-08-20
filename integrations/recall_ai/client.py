from datetime import date, datetime
from uuid import UUID

import httpx
from fastapi import status

from app.models.accounts import User
from config import logger, settings
from config.enums import Integration
from infra.db import transaction
from integrations.recall_ai.models import (
    BOT_NAME,
    RECALL_AI_PREFERENCE_MAPPING,
    RecallAIBot,
    RecallAIBotOptions,
    RecallAICalendarEvent,
    RecallAICalendarPreferences,
    RecallAICalendarUser,
    RecallAIChatMessages,
)
from integrations.recall_ai.transcript import RecallAITranscript


class RecallAIClient:
    def __init__(self):
        self.api_key = settings.recall_ai_api_key.get_secret_value()
        self.base_url = "https://us-east-1.recall.ai/api/v1"
        self.calendar_base_url = "https://us-east-1.recall.ai/api/v1"
        self.headers = {
            "Authorization": f"TOKEN {self.api_key}",
            "accept": "application/json",
            "Content-Type": "application/json",
        }
        self.default_timeout = httpx.Timeout(5.0, read=30.0, write=30.0)
        self.get_bot_transcript_timeout = httpx.Timeout(5.0, read=120.0, write=30.0)
        self.list_calendar_events_timeout = httpx.Timeout(5.0, read=180.0, write=30.0)

    async def _validate_response(self, response: httpx.Response, expected_status: int, message: str):
        if response.status_code != expected_status:
            error_text = response.text
            logger.error(f"Failed to {message}: {response.status_code} - {error_text}")
            response.raise_for_status()

    async def create_bot(self, meeting_url: str):
        """
        Create an ad-hoc recall.ai bot - joins meeting immediately.
        """
        url = f"{self.base_url}/bot/"
        payload = RecallAIBotOptions(meeting_url=meeting_url).model_dump()
        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.post(url, json=payload)
            await self._validate_response(response, status.HTTP_201_CREATED, "create bot")
            return response.json()

    async def create_scheduled_bot(self, meeting_url: str, join_at: datetime):
        """
        Create a recall.ai bot, note that the join_at time should be at least 20 minutes
        in the future.

        https://docs.recall.ai/docs/bot-fundamentals
        """
        url = f"{self.base_url}/bot/"
        payload = RecallAIBotOptions(meeting_url=meeting_url, join_at=join_at.isoformat()).model_dump()
        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.post(url, json=payload)
            await self._validate_response(response, status.HTTP_201_CREATED, "create scheduled bot")
            return response.json()

    async def get_bot(self, bot_id: str):
        """
        Retrieve details for a bot.
        """
        url = f"{self.base_url}/bot/{bot_id}"
        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.get(url)
            await self._validate_response(response, status.HTTP_200_OK, f"get bot {bot_id}")
            result = response.json()
            return RecallAIBot(**result)

    async def get_bot_transcript(self, bot_id: str):
        """
        Retrieve the meeting transcript from a bot.
        """
        url = f"{self.base_url}/bot/{bot_id}/transcript"
        async with httpx.AsyncClient(headers=self.headers, timeout=self.get_bot_transcript_timeout) as client:
            response = await client.get(url)
            await self._validate_response(response, status.HTTP_200_OK, f"get transcript for bot {bot_id}")
            transcript = response.json()
            return RecallAITranscript(chunks=transcript)

    async def get_meeting_chat_messages(self, bot_id: str, cursor: str | None = None):
        """
        Retrieve the chat messages from a bot.
        Excludes any messages sent from the bot.
        """
        url = f"{self.base_url}/bot/{bot_id}/chat-messages"
        if cursor:
            url = cursor
        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.get(url)
            await self._validate_response(response, status.HTTP_200_OK, f"get chat messages for bot {bot_id}")
            result = response.json()
            return RecallAIChatMessages(**result)

    async def update_bot(self, bot_id: str, meeting_url: str, join_at: datetime):
        """
        Update a scheduled bot with a new meeting URL or join_at time.
        """
        url = f"{self.base_url}/bot/{bot_id}"
        payload = RecallAIBotOptions(meeting_url=meeting_url, join_at=join_at.isoformat()).model_dump()
        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.patch(url, json=payload)
            await self._validate_response(response, status.HTTP_200_OK, f"update bot {bot_id}")
            return response.json()

    async def delete_bot(self, bot_id: str):
        """
        Delete a bot.

        https://docs.recall.ai/reference/bot_destroy
        """
        url = f"{self.base_url}/bot/{bot_id}"
        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.delete(url)
            await self._validate_response(response, status.HTTP_204_NO_CONTENT, f"delete bot {bot_id}")
            return True

    async def list_bots(self, join_at_after: date | None = None, page: int = 1):
        """
        List bots, optionally filtering by join_at_after datetime.

        https://docs.recall.ai/reference/bot_list
        """
        url = f"{self.base_url}/bot/"
        params: dict[str, str | int] = {}
        if join_at_after:
            params["join_at_after"] = join_at_after.isoformat()
        if page:
            params["page"] = page

        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.get(url, params=params)
            await self._validate_response(response, status.HTTP_200_OK, "list bots")
            return response.json()

    #
    # Calendar Integration (v1 API)
    #
    #

    async def get_calendar_user(self, user_id: UUID) -> RecallAICalendarUser:
        url = f"{self.calendar_base_url}/calendar/user/"
        headers = await self._calendar_headers(user_id)
        async with httpx.AsyncClient(headers=headers, timeout=self.default_timeout) as client:
            response = await client.get(url)
            await self._validate_response(response, status.HTTP_200_OK, f"get calendar user for {user_id}")
            result = response.json()
        async with transaction() as connection:
            calendar_user = await RecallAICalendarUser.get_or_none(user_id=user_id, using_db=connection)
            if not calendar_user:
                calendar_user = await RecallAICalendarUser.create(user_id=user_id, **result, using_db=connection)

            calendar_user.external_id = result["external_id"]
            calendar_user.connections = result["connections"]
            calendar_user.preferences = result["preferences"]
            await calendar_user.save(using_db=connection)

            user = await User.get(id=user_id, using_db=connection)
            if calendar_user.is_connected:
                await user.add_integration(Integration.RECALL_AI_CALENDAR, using_db=connection)
            else:
                await user.remove_integration(Integration.RECALL_AI_CALENDAR, using_db=connection)

            return calendar_user

    async def delete_calendar_user(self, user_id: UUID):
        url = f"{self.calendar_base_url}/calendar/user/"
        headers = await self._calendar_headers(user_id)
        async with httpx.AsyncClient(headers=headers, timeout=self.default_timeout) as client:
            response = await client.delete(url)
            await self._validate_response(response, status.HTTP_204_NO_CONTENT, f"delete calendar user for {user_id}")

            async with transaction() as connection:
                user = await User.get(id=user_id, using_db=connection)
                await user.remove_integration(Integration.RECALL_AI_CALENDAR, using_db=connection)

            return True

    async def list_calendar_events(
        self,
        user_id: UUID,
        start_time_after: datetime | None = None,
        start_time_before: datetime | None = None,
        ical_uid: str | None = None,
    ) -> list[RecallAICalendarEvent]:
        """
        List calendar events for a user.

        https://docs.recall.ai/reference/calendar_meetings_list
        """
        url = f"{self.calendar_base_url}/calendar/meetings/"
        headers = await self._calendar_headers(user_id)
        params = {}
        if start_time_after:
            params["start_time_after"] = start_time_after.isoformat()
        if start_time_before:
            params["start_time_before"] = start_time_before.isoformat()
        if ical_uid:
            params["ical_uid"] = ical_uid

        async with httpx.AsyncClient(headers=headers, timeout=self.list_calendar_events_timeout) as client:
            response = await client.get(url, params=params)
            await self._validate_response(response, status.HTTP_200_OK, f"list calendar events for {user_id}")
            result = response.json()
            events = [RecallAICalendarEvent(**event) for event in result]
            return [event for event in events if not event.is_hidden]

    async def get_calendar_event(self, user_id: UUID, event_id: str) -> RecallAICalendarEvent:
        url = f"{self.calendar_base_url}/calendar/meetings/{event_id}/"
        headers = await self._calendar_headers(user_id)
        async with httpx.AsyncClient(headers=headers, timeout=self.default_timeout) as client:
            response = await client.get(url)
            await self._validate_response(response, status.HTTP_200_OK, f"get calendar event {event_id} for {user_id}")
            result = response.json()
            return RecallAICalendarEvent(**result)

    async def update_calendar_event_recording(
        self, user_id: UUID, event_id: str, override_should_record: bool | None = None
    ):
        """
        Update override_should_record property of the meeting.

        See Recall docs on recording preferences: https://docs.recall.ai/docs/calendar-v1-recording-preferences
        """
        url = f"{self.calendar_base_url}/calendar/meetings/{event_id}/"
        headers = await self._calendar_headers(user_id)
        payload = {"override_should_record": override_should_record}
        async with httpx.AsyncClient(headers=headers, timeout=self.default_timeout) as client:
            response = await client.patch(url, json=payload)
            await self._validate_response(
                response, status.HTTP_200_OK, f"update calendar event recording {event_id} for {user_id}"
            )
            return True

    async def update_calendar_user_recording_preferences(
        self, user_id: UUID, recording_preference: RecallAICalendarPreferences = RecallAICalendarPreferences.ALL
    ) -> bool:
        """Update the user's recording preferences."""
        url = f"{self.calendar_base_url}/calendar/user/"
        headers = await self._calendar_headers(user_id)
        preferences = RECALL_AI_PREFERENCE_MAPPING[recording_preference.value]
        preferences["bot_name"] = BOT_NAME
        payload = {"preferences": preferences}

        async with httpx.AsyncClient(headers=headers, timeout=self.default_timeout) as client:
            response = await client.patch(url, json=payload)
            await self._validate_response(
                response, status.HTTP_200_OK, f"update calendar user recording preferences for {user_id}"
            )
            result = response.json()
            existing_cal_user = await RecallAICalendarUser.get_or_none(user_id=user_id)
            if existing_cal_user:
                await existing_cal_user.update_from_response(result)
            else:
                await RecallAICalendarUser.create(user_id=user_id, **result)
            return True

    async def refresh_calendar_meetings(self, user_id: UUID) -> list[RecallAICalendarEvent]:
        """
        Refresh calendar meetings for a user.

        https://docs.recall.ai/v1.10/reference/calendar_meetings_refresh_create
        """
        url = f"{self.calendar_base_url}/calendar/meetings/refresh/"
        headers = await self._calendar_headers(user_id)
        async with httpx.AsyncClient(headers=headers, timeout=self.default_timeout) as client:
            response = await client.post(url)
            await self._validate_response(response, status.HTTP_200_OK, f"refresh calendar meetings for {user_id}")
            result = response.json()
            events = [RecallAICalendarEvent(**event) for event in result]
            return [event for event in events if not event.is_hidden]

    async def _calendar_headers(self, user_id: UUID):
        token = await self._calendar_auth(user_id)
        return {
            **self.headers,
            "x-recallcalendarauthtoken": token["token"],
        }

    async def _calendar_auth(self, user_id: UUID):
        """
        Generate an authentication token for calendar APIs, scoped to the user.
        Each token has an expiry of 1 day from time of creation.

        https://docs.recall.ai/reference/calendar_authenticate_create
        """
        url = f"{self.calendar_base_url}/calendar/authenticate/"
        payload = {"user_id": str(user_id)}
        async with httpx.AsyncClient(headers=self.headers, timeout=self.default_timeout) as client:
            response = await client.post(url, json=payload)
            await self._validate_response(response, status.HTTP_200_OK, f"get calendar auth token for {user_id}")
            return response.json()
