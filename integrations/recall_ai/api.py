from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from app.models.accounts import User
from app.models.workspaces.meetings import Meeting
from app.routers.dependencies import (
    Channel,
    get_current_user,
    get_meeting,
    handle_stream,
)
from config.enums import ChannelEventAction, ChannelEventResource, Integration
from infra.messaging import Topic
from integrations.recall_ai.client import RecallAIClient
from integrations.recall_ai.helpers import recall_substatus_description
from integrations.recall_ai.models import (
    RecallAIBotStatusCodes,
    RecallAICalendarPreferences,
    RecallAICalendarUser,
    RecallAIMeeting,
)
from integrations.recall_ai.presenters import RecallAIBotStatusPresenter

router = APIRouter()


#
# Response & request models
#


class MeetingBotResponse(BaseModel):
    bot_id: str | None
    bot_status: str
    bot_sub_status: str | None
    is_processing_transcript: bool
    is_recording_in_progress: bool
    is_failed: bool
    will_record: bool
    is_schedulable: bool
    is_supported_meeting_platform: bool
    has_calendar_event: bool
    status_display: str
    failure_reason: str | None


class UpdateBotRequest(BaseModel):
    # Required (no default) so a body missing `will_record` returns 422.
    will_record: bool


CalendarPreferenceLiteral = Literal["all", "none"]


class CalendarResponse(BaseModel):
    calendar_connected: bool
    provider: Literal["google", "microsoft"] | None
    preference: CalendarPreferenceLiteral
    calendar_user_id: str | None
    # True when the user is not a Microsoft-SSO user — the prerequisite for
    # initiating the Google Calendar OAuth handshake, matching how the connect
    # routes are gated on `is_microsoft`. The UI gates the Connect Calendar
    # prompt on this flag.
    is_google_authenticated: bool


class UpdateCalendarRequest(BaseModel):
    preference: CalendarPreferenceLiteral


#
# Serializers
#


_PROVIDER_MAP: dict[str, Literal["google", "microsoft"]] = {
    "google_calendar": "google",
    "microsoft_outlook": "microsoft",
}


def _calendar_provider(calendar_user: RecallAICalendarUser | None) -> Literal["google", "microsoft"] | None:
    if not calendar_user:
        return None
    for connection in calendar_user.connections:
        if connection.get("connected") and (provider := connection.get("provider")):
            if mapped := _PROVIDER_MAP.get(str(provider)):
                return mapped
    return None


def _calendar_preference(calendar_user: RecallAICalendarUser | None) -> CalendarPreferenceLiteral:
    if not calendar_user:
        return "none"
    try:
        name = calendar_user.preference_name
    except ValueError:
        return "none"
    if name == RecallAICalendarPreferences.ALL:
        return "all"
    return "none"


def _calendar_response(user: User, calendar_user: RecallAICalendarUser | None) -> CalendarResponse:
    return CalendarResponse(
        calendar_connected=user.is_integrated_with(Integration.RECALL_AI_CALENDAR),
        provider=_calendar_provider(calendar_user),
        preference=_calendar_preference(calendar_user),
        calendar_user_id=calendar_user.id if calendar_user else None,
        is_google_authenticated=not user.authentication.is_microsoft,
    )


def _status_display(
    recall_ai_meeting: RecallAIMeeting,
    presenter: RecallAIBotStatusPresenter,
    has_transcript: bool,
) -> str:
    # Collapses the bot-state branch table into one pre-formatted string so the
    # React island doesn't reproduce the conditionals client-side.
    if presenter.is_successful and not has_transcript:
        return "Convictional's meeting bot is currently processing the recording."
    if presenter.is_failed:
        description = recall_substatus_description(recall_ai_meeting.bot_sub_status)
        return description or "The recording could not be completed."
    status_code = recall_ai_meeting.bot_status
    if status_code == RecallAIBotStatusCodes.SCHEDULED:
        return "Convictional's meeting bot is scheduled to join this meeting."
    if status_code == RecallAIBotStatusCodes.UNSCHEDULABLE:
        return "Convictional's meeting bot is unable to join this meeting."
    if status_code == RecallAIBotStatusCodes.IN_CALL_RECORDING:
        return "This meeting is currently being recorded."
    if status_code and status_code != RecallAIBotStatusCodes.DONE:
        return "Convictional's meeting bot is currently processing the recording."
    if recall_ai_meeting.will_record:
        return "This meeting will be recorded by Convictional."
    if not recall_ai_meeting.is_supported_meeting_platform:
        return "This meeting cannot be recorded. Convictional supports Zoom, Google Meet, and Microsoft Teams."
    if not recall_ai_meeting.is_schedulable:
        return "This meeting cannot be recorded because it is scheduled to start within 20 minutes."
    return ""


async def _bot_response(meeting: Meeting) -> MeetingBotResponse | None:
    recall_ai_meeting = await RecallAIMeeting.get_or_none(meeting_id=meeting.id).prefetch_related("meeting")
    if recall_ai_meeting is None:
        return None
    bot_status_presenter = await RecallAIBotStatusPresenter.create(recall_ai_meeting)
    has_transcript = meeting.processed_transcript is not None
    bot_sub_status = recall_ai_meeting.bot_sub_status
    return MeetingBotResponse(
        bot_id=recall_ai_meeting.bot_id,
        bot_status=str(recall_ai_meeting.bot_status),
        bot_sub_status=str(bot_sub_status) if bot_sub_status else None,
        is_processing_transcript=bot_status_presenter.is_successful and not has_transcript,
        is_recording_in_progress=recall_ai_meeting.bot_status == RecallAIBotStatusCodes.IN_CALL_RECORDING,
        is_failed=bot_status_presenter.is_failed,
        will_record=recall_ai_meeting.will_record,
        is_schedulable=recall_ai_meeting.is_schedulable,
        is_supported_meeting_platform=recall_ai_meeting.is_supported_meeting_platform,
        has_calendar_event=recall_ai_meeting.meeting.ical_uid is not None,
        status_display=_status_display(recall_ai_meeting, bot_status_presenter, has_transcript),
        failure_reason=recall_substatus_description(recall_ai_meeting.bot_sub_status)
        if bot_status_presenter.is_failed
        else None,
    )


#
# Endpoints
#


# Bot state lives on its own endpoint (rather than on the MeetingResponse from
# api/meetings.py) because the integrations layer cannot be imported from app/ —
# the React island fetches the show payload and bot state in parallel on mount,
# matching the existing /recording and /transcript sibling-endpoint pattern.
@router.get("/meetings/{meeting_id}/bot", response_model=MeetingBotResponse)
async def api_meetings_bot_show(meeting: Meeting = Depends(get_meeting)):
    state = await _bot_response(meeting)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Recall.ai bot for this meeting.",
        )
    return state


@router.patch("/meetings/{meeting_id}/bot", response_model=MeetingBotResponse)
async def api_meetings_bot_update(
    body: UpdateBotRequest,
    meeting: Meeting = Depends(get_meeting),
    current_user: User = Depends(get_current_user),
):
    recall_ai_meeting = await RecallAIMeeting.get_or_none(meeting_id=meeting.id).prefetch_related("meeting")
    if recall_ai_meeting is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This meeting does not have a Recall.ai bot configured.",
        )

    if not recall_ai_meeting.is_supported_meeting_platform:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Meeting platform not supported. Convictional supports Zoom, Google Meet, and Microsoft Teams.",
        )

    if recall_ai_meeting.meeting.ical_uid is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This meeting is not linked to a calendar event and cannot be recorded.",
        )

    # Recall.ai recording is toggled per calendar event, which lives on a single
    # user's connected calendar. Only that owner can change it — other workspace
    # collaborators see the same meeting but can't drive recording.
    if not current_user.is_integrated_with(Integration.RECALL_AI_CALENDAR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting's calendar owner can change recording.",
        )

    client = RecallAIClient()
    calendar_events = await client.list_calendar_events(
        user_id=current_user.id, ical_uid=recall_ai_meeting.meeting.ical_uid
    )
    if not calendar_events:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the meeting's calendar owner can change recording.",
        )

    success = await client.update_calendar_event_recording(
        user_id=current_user.id,
        event_id=calendar_events[0].id,
        override_should_record=body.will_record,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Failed to update recording status with Recall.ai.",
        )

    recall_ai_meeting.will_record = body.will_record
    await recall_ai_meeting.save(update_fields=["will_record"])

    await Topic("meeting_bot", meeting_id=meeting.id).broadcast()

    state = await _bot_response(meeting)
    assert state is not None  # recall_ai_meeting exists, so state is non-null
    return state


async def get_calendar_user_or_none(
    current_user: User = Depends(get_current_user),
) -> RecallAICalendarUser | None:
    return await RecallAICalendarUser.get_or_none(user_id=current_user.id)


@router.get("/users/me/calendar", response_model=CalendarResponse)
async def api_users_me_calendar_show(
    current_user: User = Depends(get_current_user),
    calendar_user: RecallAICalendarUser | None = Depends(get_calendar_user_or_none),
):
    return _calendar_response(current_user, calendar_user)


@router.patch("/users/me/calendar", response_model=CalendarResponse)
async def api_users_me_calendar_update(
    body: UpdateCalendarRequest,
    current_user: User = Depends(get_current_user),
):
    await RecallAIClient().update_calendar_user_recording_preferences(
        user_id=current_user.id,
        recording_preference=RecallAICalendarPreferences(body.preference),
    )
    # Refetch post-update so the response reflects the new preference.
    calendar_user = await RecallAICalendarUser.get_or_none(user_id=current_user.id)
    return _calendar_response(current_user, calendar_user)


@router.delete("/users/me/calendar", status_code=status.HTTP_204_NO_CONTENT)
async def api_users_me_calendar_delete(
    current_user: User = Depends(get_current_user),
    calendar_user: RecallAICalendarUser | None = Depends(get_calendar_user_or_none),
):
    if calendar_user is None:
        # Idempotent: nothing connected, nothing to disconnect.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    await RecallAIClient().delete_calendar_user(user_id=current_user.id)
    await calendar_user.delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


#
# Channel
#


@handle_stream("meeting_bot")
async def handle_meeting_bot_json_events(channel: Channel, **data: object) -> None:
    meeting_id = channel.get_param("meeting_id")
    if not meeting_id:
        return
    meeting = await Meeting.get_or_none(id=meeting_id).prefetch_related(
        "workspace__collaborators__user",
    )
    if not meeting or not meeting.collaboration.can_be_accessed_by(channel.current_user):
        return
    state = await _bot_response(meeting)
    if state is None:
        return
    await channel.send_event(
        ChannelEventResource.MEETING_BOT,
        ChannelEventAction.UPDATED,
        state=state.model_dump(mode="json"),
    )
