from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import status

from config.enums import MeetingAttendeeStatus
from infra.jobs import InlineJobs
from infra.messaging import Topic
from integrations.recall_ai.jobs import (
    CreateMeetingFromBotIDJob,
    SyncRecordingFromRecallAIJob,
    SyncTranscriptFromRecallAIJob,
)
from integrations.recall_ai.models import (
    RecallAICalendarAttendee,
    RecallAICalendarEvent,
    RecallAIMeeting,
)
from tests.helpers.app import AppClient
from tests.helpers.factories import create_meeting, create_user


@pytest.mark.asyncio
async def test_recall_ai_bot_status_changed(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    meeting = await create_meeting(
        title="Test meeting",
        scheduled_at=datetime.now(UTC),
        creator_id=user.id,
        organization_id=user.organization_id,
        bot_id="test",
    )

    broadcasts: list[tuple[str, dict]] = []
    original_broadcast = Topic.broadcast

    async def spy_broadcast(self, **data):
        broadcasts.append((self.name, data))
        await original_broadcast(self, **data)

    monkeypatch.setattr(Topic, "broadcast", spy_broadcast)

    sample_payload = {
        "event": "bot.status_change",
        "data": {
            "bot_id": "test",
            "status": {
                "code": "in_waiting_room",
                "created_at": "2021-01-01T00:00:00Z",
                "sub_code": None,
                "message": None,
                "recording_id": None,
            },
        },
    }

    response = await client.post(
        "/integrations/recall_ai/webhooks", json=sample_payload, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == status.HTTP_200_OK

    recall_meeting = await RecallAIMeeting.get_or_none(meeting_id=meeting.id)
    assert recall_meeting is not None
    assert recall_meeting.bot_status == "in_waiting_room"

    # Webhook fans out a meeting_bot NOTIFY so React clients refresh their state.
    expected_topic = f"meeting_bot:meeting_id:{meeting.id}"
    assert any(name == expected_topic for name, _ in broadcasts)


@pytest.mark.asyncio
async def test_recall_ai_bot_done_webhook(client: AppClient, background_jobs: InlineJobs, monkeypatch):
    user = await client.get_default_user()
    monkeypatch.setattr("integrations.recall_ai.jobs.CreateMeetingFromBotIDJob.perform", AsyncMock())
    monkeypatch.setattr("integrations.recall_ai.jobs.SyncTranscriptFromRecallAIJob.perform", AsyncMock())
    monkeypatch.setattr("integrations.recall_ai.jobs.SyncRecordingFromRecallAIJob.perform", AsyncMock())
    bot_id = "7d1b8e53-addd-4817-9960-bbc2ba6d93dc"
    recall_event_id = "49bb310f-14fa-4683-abee-f2341396a6de"
    bot_joining_call_payload = {
        "event": "bot.status_change",
        "data": {
            "bot_id": bot_id,
            "status": {
                "code": "in_call_not_recording",
                "created_at": "2021-01-01T00:00:00Z",
                "sub_code": None,
                "message": None,
                "recording_id": None,
            },
        },
    }

    response = await client.post("/integrations/recall_ai/webhooks", json=bot_joining_call_payload)
    assert response.status_code == status.HTTP_200_OK

    # Create the meeting because we are mocking the job execution
    meeting = await create_meeting(
        title="Test meeting",
        scheduled_at=datetime.now(UTC),
        creator_id=user.id,
        organization_id=user.organization_id,
        external_id=recall_event_id,
        bot_id=bot_id,
    )

    bot_done_payload = {
        "event": "bot.status_change",
        "data": {
            "bot_id": bot_id,
            "status": {
                "code": "done",
                "created_at": "2021-01-01T00:00:00Z",
                "sub_code": None,
                "message": None,
                "recording_id": None,
            },
        },
    }

    response = await client.post("/integrations/recall_ai/webhooks", json=bot_done_payload)
    assert response.status_code == status.HTTP_200_OK

    recall_meeting = await RecallAIMeeting.get_or_none(meeting_id=meeting.id)
    assert recall_meeting is not None
    assert recall_meeting.bot_status == "done"

    assert background_jobs.has_completed_job(CreateMeetingFromBotIDJob)
    assert background_jobs.has_completed_job(SyncTranscriptFromRecallAIJob)
    assert background_jobs.has_completed_job(SyncRecordingFromRecallAIJob)


@pytest.mark.asyncio
async def test_recall_ai_bot_webhook_sets_did_recording_fail(
    client: AppClient, background_jobs: InlineJobs, monkeypatch
):
    monkeypatch.setattr("integrations.recall_ai.jobs.SyncTranscriptFromRecallAIJob.perform", AsyncMock())
    monkeypatch.setattr("integrations.recall_ai.jobs.SyncRecordingFromRecallAIJob.perform", AsyncMock())

    user = await client.get_default_user()

    # Fatal status
    fatal_bot_id = "fatal-bot-id"
    fatal_meeting = await create_meeting(
        title="Meeting with fatal bot",
        scheduled_at=datetime.now(UTC),
        creator_id=user.id,
        organization_id=user.organization_id,
        bot_id=fatal_bot_id,
    )

    response = await client.post(
        "/integrations/recall_ai/webhooks",
        json={
            "event": "bot.status_change",
            "data": {
                "bot_id": fatal_bot_id,
                "status": {
                    "code": "fatal",
                    "created_at": "2021-01-01T00:00:00Z",
                    "sub_code": "meeting_not_found",
                    "message": None,
                    "recording_id": None,
                },
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK
    await fatal_meeting.refresh_from_db()
    assert fatal_meeting.did_recording_fail is True

    # Done with non-successful sub code
    done_bot_id = "done-failed-bot-id"
    done_meeting = await create_meeting(
        title="Meeting with failed done bot",
        scheduled_at=datetime.now(UTC),
        creator_id=user.id,
        organization_id=user.organization_id,
        bot_id=done_bot_id,
    )

    response = await client.post(
        "/integrations/recall_ai/webhooks",
        json={
            "event": "bot.status_change",
            "data": {
                "bot_id": done_bot_id,
                "status": {
                    "code": "done",
                    "created_at": "2021-01-01T00:00:00Z",
                    "sub_code": "timeout_exceeded_noone_joined",
                    "message": None,
                    "recording_id": None,
                },
            },
        },
    )
    assert response.status_code == status.HTTP_200_OK
    await done_meeting.refresh_from_db()
    assert done_meeting.did_recording_fail is True


@pytest.mark.asyncio
async def test_multi_org_meeting(client: AppClient, background_jobs: InlineJobs, monkeypatch):
    # Monkeypatch the job execution to prevent calls to RecallAI API
    monkeypatch.setattr("integrations.recall_ai.jobs.SyncTranscriptFromRecallAIJob.perform", AsyncMock())
    monkeypatch.setattr("integrations.recall_ai.jobs.SyncRecordingFromRecallAIJob.perform", AsyncMock())

    user = await client.get_default_user()
    another_user = await create_user()

    bot_id = "7d1b8e53-addd-4817-9960-bbc2ba6d93dc"
    ical_uid = "test-ical-uid"
    scheduled_at = datetime.now(UTC)

    calendar_event = RecallAICalendarEvent(
        id="1",
        title="Test event 1",
        start_time=scheduled_at,
        end_time=scheduled_at + timedelta(hours=1),
        attendees=[
            RecallAICalendarAttendee(email=user.email, is_organizer=True, status=MeetingAttendeeStatus.ACCEPTED),
            RecallAICalendarAttendee(
                email=another_user.email, is_organizer=False, status=MeetingAttendeeStatus.ACCEPTED
            ),
        ],
        attendee_emails=[user.email, another_user.email],
        will_record=True,
        will_record_reason="This is a test meeting",
        bot_id=bot_id,
        is_external=False,
        is_hosted_by_me=True,
        is_recurring=False,
        organizer_email=user.email,
        ical_uid=ical_uid,
        provider_meeting_id=ical_uid,
    )

    meeting_first_org = await create_meeting(
        creator=user,
        organization_id=user.organization_id,
        ical_uid=ical_uid,
        provider_meeting_id=ical_uid,
        scheduled_at=scheduled_at,
        external_id=calendar_event.unique_event_id(user.organization_id),
        bot_id=bot_id,
    )
    meeting_second_org = await create_meeting(
        creator=another_user,
        organization_id=another_user.organization_id,
        ical_uid=ical_uid,
        provider_meeting_id=ical_uid,
        scheduled_at=scheduled_at,
        external_id=calendar_event.unique_event_id(another_user.organization_id),
        bot_id=bot_id,
    )

    bot_done_payload = {
        "event": "bot.status_change",
        "data": {
            "bot_id": bot_id,
            "status": {
                "code": "done",
                "created_at": "2021-01-01T00:00:00Z",
                "sub_code": None,
                "message": None,
                "recording_id": None,
            },
        },
    }

    response = await client.post("/integrations/recall_ai/webhooks", json=bot_done_payload)
    assert response.status_code == status.HTTP_200_OK

    await meeting_first_org.refresh_from_db()
    await meeting_second_org.refresh_from_db()
    recall_ai_meeting_first_org = await RecallAIMeeting.get_or_none(meeting_id=meeting_first_org.id)
    assert recall_ai_meeting_first_org is not None
    recall_ai_meeting_second_org = await RecallAIMeeting.get_or_none(meeting_id=meeting_second_org.id)
    assert recall_ai_meeting_second_org is not None

    assert recall_ai_meeting_first_org.bot_status == "done"
    assert recall_ai_meeting_second_org.bot_status == "done"

    assert background_jobs.has_completed_job(SyncTranscriptFromRecallAIJob, count=2)
    completed_sync_transcript_jobs = background_jobs.all_completed_jobs_by_type(SyncTranscriptFromRecallAIJob)
    sync_transcript_meeting_ids = [job.job_details["meeting_id"] for job in completed_sync_transcript_jobs]
    assert str(meeting_first_org.id) in sync_transcript_meeting_ids
    assert str(meeting_second_org.id) in sync_transcript_meeting_ids

    assert background_jobs.has_completed_job(SyncRecordingFromRecallAIJob, count=2)
    completed_sync_recording_jobs = background_jobs.all_completed_jobs_by_type(SyncRecordingFromRecallAIJob)
    sync_recording_meeting_ids = [job.job_details["meeting_id"] for job in completed_sync_recording_jobs]
    assert str(meeting_first_org.id) in sync_recording_meeting_ids
    assert str(meeting_second_org.id) in sync_recording_meeting_ids
