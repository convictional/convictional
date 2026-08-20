from datetime import UTC, datetime, timedelta

import pytest

from app.models.workspaces.meetings import Meeting
from config.enums import MeetingAttendeeStatus
from infra.db import allow_soft_deleted
from integrations.recall_ai.client import RecallAIClient
from integrations.recall_ai.jobs import CreateUpcomingMeetingsForUserJob
from integrations.recall_ai.models import (
    RecallAICalendarAttendee,
    RecallAICalendarEvent,
    RecallAIMeeting,
    RecallAIPlatform,
)
from tests.helpers.app import AppClient
from tests.helpers.factories import create_meeting, create_user

BOT_ID = "39970a37-a9b9-4e41-ae6d-747c1aa6b0af"


@pytest.mark.asyncio
async def test_create_upcoming_meetings_for_user_job(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    organizer_user = await create_user(email="organizer@example.com", organization_id=user.organization_id)

    attendees = [
        RecallAICalendarAttendee(email=organizer_user.email, is_organizer=True, status=MeetingAttendeeStatus.ACCEPTED),
        RecallAICalendarAttendee(email=user.email, is_organizer=False, status=MeetingAttendeeStatus.ACCEPTED),
        RecallAICalendarAttendee(email="bob@clams.net", is_organizer=False, status=MeetingAttendeeStatus.ACCEPTED),
    ]

    attendee_emails = [organizer_user.email, user.email, "bob@clams.net"]

    mock_events: list[RecallAICalendarEvent] = [
        RecallAICalendarEvent(
            id="1",
            title="Test event 1",
            start_time="2021-01-01T00:00:00Z",
            end_time="2021-01-01T01:00:00Z",
            attendees=attendees,
            attendee_emails=attendee_emails,
            will_record=False,
            will_record_reason="Not recording this test meeting",
            bot_id=None,
            is_external=False,
            is_hosted_by_me=True,
            is_recurring=False,
            organizer_email=organizer_user.email,
            ical_uid="test-ical-uid",
            meeting_platform=RecallAIPlatform.GOOGLE_MEET,
            meet_invite={"meeting_id": "abc-defg-hij"},
        ),
        RecallAICalendarEvent(
            id="2",
            title="Test event 2",
            start_time="2021-01-02T00:00:00Z",
            end_time="2021-01-02T01:00:00Z",
            attendees=attendees,
            attendee_emails=attendee_emails,
            will_record=True,
            will_record_reason="Test reason",
            bot_id=BOT_ID,
            is_external=False,
            is_hosted_by_me=True,
            is_recurring=False,
            organizer_email=organizer_user.email,
            ical_uid="new-test-ical-uid",
            meeting_platform=RecallAIPlatform.ZOOM,
            zoom_invite={"meeting_id": "1234567890"},
        ),
    ]

    existing_meeting = await create_meeting(
        creator=user, external_id=mock_events[0].unique_event_id(user.organization_id), will_record=True
    )

    # Monkeypatch RecallAIClient.list_calendar_events to return a list of 2 events, including the existing meeting
    async def mock_list_calendar_events(*args, **kwargs):
        return mock_events

    # Monkeypatch RecallAIClient.get_calendar_event to return one of the events
    async def mock_get_calendar_event(self, user_id, event_id):
        for event in mock_events:
            if event.id == event_id:
                return event
        raise ValueError(f"No event found with id {event_id}")

    monkeypatch.setattr(RecallAIClient, "list_calendar_events", mock_list_calendar_events)
    monkeypatch.setattr(RecallAIClient, "get_calendar_event", mock_get_calendar_event)

    job = CreateUpcomingMeetingsForUserJob(user_id=user.id)
    await job.perform()

    # Verify the existing meeting was updated
    await existing_meeting.refresh_from_db()
    assert existing_meeting.title == "Test event 1"
    assert existing_meeting.conferencing_url == "https://meet.google.com/abc-defg-hij"

    # Verify a new meeting was created
    new_recall_meeting = await RecallAIMeeting.get_or_none(
        external_id=mock_events[1].unique_event_id(user.organization_id)
    )
    assert new_recall_meeting
    assert new_recall_meeting is not None
    assert new_recall_meeting.bot_id == BOT_ID

    new_meeting = await Meeting.get(id=new_recall_meeting.meeting_id)
    assert new_meeting.title == "Test event 2"
    assert new_meeting.ical_uid == "new-test-ical-uid"
    assert new_meeting.provider_meeting_id == "1234567890"  # Extracted from zoom_invite
    assert new_meeting.conferencing_url == "https://zoom.us/j/1234567890"

    # Verify attendees were added to the new meeting
    assert len(new_meeting.attendees) == 3
    assert user.id in [attendee.user_id for attendee in new_meeting.attendees]
    assert organizer_user.id in [attendee.user_id for attendee in new_meeting.attendees]
    assert "bob@clams.net" in [attendee.name for attendee in new_meeting.attendees]

    # Verify the organizer was set and creator_id was updated for internal organizer
    organizer = new_meeting.organizer
    assert organizer is not None
    assert organizer.user_id == organizer_user.id
    # The meeting creator should now be the organizer, not the user who processed the calendar
    assert new_meeting.creator_id == organizer_user.id


@pytest.mark.asyncio
async def test_calendar_sync_preserves_bot_id(client: AppClient, monkeypatch):
    """Calendar events are user-scoped — when another user syncs, their event may have bot_id=None.
    The sync must not wipe an existing bot_id, but should allow replacement with a new one."""
    user = await client.get_default_user()
    new_bot_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

    def make_event(bot_id=None, will_record=False):
        return RecallAICalendarEvent(
            id="1",
            title="Recurring standup",
            start_time="2024-06-01T10:00:00Z",
            end_time="2024-06-01T10:30:00Z",
            attendees=[
                RecallAICalendarAttendee(email=user.email, is_organizer=True, status=MeetingAttendeeStatus.ACCEPTED),
            ],
            attendee_emails=[user.email],
            will_record=will_record,
            will_record_reason="Test",
            bot_id=bot_id,
            is_external=False,
            is_hosted_by_me=True,
            is_recurring=True,
            organizer_email=user.email,
            ical_uid="recurring-standup",
            meeting_platform=RecallAIPlatform.GOOGLE_MEET,
            meet_invite={"meeting_id": "abc-defg-hij"},
        )

    current_event = make_event(bot_id=None)

    existing_meeting = await create_meeting(
        creator=user, external_id=current_event.unique_event_id(user.organization_id), will_record=True
    )
    recall_meeting = await RecallAIMeeting.get(meeting_id=existing_meeting.id)
    recall_meeting.bot_id = BOT_ID
    await recall_meeting.save(update_fields=["bot_id"])

    async def mock_list_calendar_events(*args, **kwargs):
        return [current_event]

    async def mock_get_calendar_event(self, user_id, event_id):
        return current_event

    monkeypatch.setattr(RecallAIClient, "list_calendar_events", mock_list_calendar_events)
    monkeypatch.setattr(RecallAIClient, "get_calendar_event", mock_get_calendar_event)

    # Sync with bot_id=None must not wipe the existing bot_id
    job = CreateUpcomingMeetingsForUserJob(user_id=user.id)
    await job.perform()

    await recall_meeting.refresh_from_db()
    assert recall_meeting.bot_id == BOT_ID

    # Sync with a new bot_id should update it
    current_event = make_event(bot_id=new_bot_id, will_record=True)
    await job.perform()

    await recall_meeting.refresh_from_db()
    assert recall_meeting.bot_id == new_bot_id


@pytest.mark.asyncio
async def test_empty_calendar_response_deletes_future_meetings(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    tomorrow = datetime.now(UTC) + timedelta(days=1)
    tomorrow_plus_one_hour = tomorrow + timedelta(hours=1)

    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_id="canceled-event-id",
        scheduled_at=tomorrow,
        scheduled_end_at=tomorrow_plus_one_hour,
    )
    other_meeting = await create_meeting(
        creator_id=other_user.id,
        organization_id=other_user.organization_id,
        external_id="other-event-id",
        scheduled_at=tomorrow,
        scheduled_end_at=tomorrow_plus_one_hour,
    )

    async def mock_list_calendar_events(*args, **kwargs):
        return []

    monkeypatch.setattr(RecallAIClient, "list_calendar_events", mock_list_calendar_events)

    job = CreateUpcomingMeetingsForUserJob(user_id=user.id)
    await job.perform()

    # The user's future meeting should be soft-deleted since it no longer appears in the calendar
    async with allow_soft_deleted():
        updated_meeting = await Meeting.get(id=meeting.id)
    assert updated_meeting.deleted_at is not None

    # The other user's meeting should be unaffected
    other_updated_meeting = await Meeting.get(id=other_meeting.id)
    assert other_updated_meeting.deleted_at is None
