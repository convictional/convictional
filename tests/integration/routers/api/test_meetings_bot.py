from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import status

from config.enums import Integration
from integrations.recall_ai.models import (
    RECALL_AI_PREFERENCE_MAPPING,
    RecallAIBotStatusCodes,
    RecallAIBotStatusSubCodes,
    RecallAICalendarEvent,
    RecallAICalendarUser,
    RecallAIMeeting,
    RecallAIPlatform,
)
from tests.helpers.app import AppClient
from tests.helpers.factories import create_meeting, create_organization, create_user


def _fake_calendar_event(ical_uid: str) -> RecallAICalendarEvent:
    return RecallAICalendarEvent(
        id="evt-1",
        title="Test event",
        start_time=datetime.now(UTC) + timedelta(hours=2),
        end_time=datetime.now(UTC) + timedelta(hours=3),
        attendees=[],
        attendee_emails=[],
        will_record=False,
        will_record_reason="",
        is_external=False,
        is_hosted_by_me=True,
        is_recurring=False,
        organizer_email="x@example.com",
        ical_uid=ical_uid,
    )


@pytest.mark.asyncio
async def test_bot_show_and_patch_happy_path(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    meeting = await create_meeting(
        title="Test meeting",
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
        ical_uid="ical-1",
    )

    show = await client.get(f"/api/meetings/{meeting.id}/bot")
    assert show.status_code == status.HTTP_200_OK
    body = show.json()
    assert body["will_record"] is False
    assert body["is_schedulable"] is True
    assert body["is_supported_meeting_platform"] is True
    assert body["is_recording_in_progress"] is False
    assert body["is_processing_transcript"] is False
    assert body["is_failed"] is False
    assert body["has_calendar_event"] is True
    assert body["failure_reason"] is None
    assert "status_display" in body

    await user.add_integration(Integration.RECALL_AI_CALENDAR)
    monkeypatch.setattr(
        "integrations.recall_ai.client.RecallAIClient.list_calendar_events",
        AsyncMock(return_value=[_fake_calendar_event("ical-1")]),
    )
    monkeypatch.setattr(
        "integrations.recall_ai.client.RecallAIClient.update_calendar_event_recording",
        AsyncMock(return_value=True),
    )

    patched = await client.patch(f"/api/meetings/{meeting.id}/bot", json={"will_record": True})
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["will_record"] is True

    recall_meeting = await RecallAIMeeting.get(meeting_id=meeting.id)
    assert recall_meeting.will_record is True


@pytest.mark.asyncio
async def test_bot_patch_409_unsupported_platform(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.WEBEX,
        ical_uid="ical-2",
    )

    response = await client.patch(f"/api/meetings/{meeting.id}/bot", json={"will_record": True})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "not supported" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bot_patch_422_no_calendar_event_on_meeting(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
    )

    response = await client.patch(f"/api/meetings/{meeting.id}/bot", json={"will_record": True})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert "calendar event" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bot_patch_403_when_user_has_no_calendar(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
        ical_uid="ical-no-cal",
    )

    response = await client.patch(f"/api/meetings/{meeting.id}/bot", json={"will_record": True})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "calendar owner" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bot_patch_403_when_user_is_not_event_owner(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    await user.add_integration(Integration.RECALL_AI_CALENDAR)
    meeting = await create_meeting(
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
        ical_uid="ical-not-owned",
    )
    monkeypatch.setattr(
        "integrations.recall_ai.client.RecallAIClient.list_calendar_events",
        AsyncMock(return_value=[]),
    )

    response = await client.patch(f"/api/meetings/{meeting.id}/bot", json={"will_record": True})
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "calendar owner" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bot_patch_409_when_recall_update_fails(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    await user.add_integration(Integration.RECALL_AI_CALENDAR)
    meeting = await create_meeting(
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
        ical_uid="ical-fail",
    )
    monkeypatch.setattr(
        "integrations.recall_ai.client.RecallAIClient.list_calendar_events",
        AsyncMock(return_value=[_fake_calendar_event("ical-fail")]),
    )
    monkeypatch.setattr(
        "integrations.recall_ai.client.RecallAIClient.update_calendar_event_recording",
        AsyncMock(return_value=False),
    )

    response = await client.patch(f"/api/meetings/{meeting.id}/bot", json={"will_record": True})
    assert response.status_code == status.HTTP_409_CONFLICT
    assert "failed to update" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_bot_patch_422_missing_field(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
    )

    response = await client.patch(f"/api/meetings/{meeting.id}/bot", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_bot_show_404_cross_org(client: AppClient):
    other_org = await create_organization()
    other_creator = await create_user(organization_id=other_org.id)
    meeting = await create_meeting(
        creator_id=other_creator.id,
        organization_id=other_org.id,
        scheduled_at=datetime.now(UTC) + timedelta(hours=2),
    )

    response = await client.get(f"/api/meetings/{meeting.id}/bot")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_bot_state_reflects_failure(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(
        scheduled_at=datetime.now(UTC) - timedelta(hours=1),
        creator_id=user.id,
        organization_id=user.organization_id,
        meeting_platform=RecallAIPlatform.GOOGLE_MEET,
    )
    recall_meeting = await RecallAIMeeting.get(meeting_id=meeting.id)
    recall_meeting.bot_status = RecallAIBotStatusCodes.FATAL
    recall_meeting.bot_sub_status = RecallAIBotStatusSubCodes.MEETING_NOT_FOUND
    await recall_meeting.save()

    response = await client.get(f"/api/meetings/{meeting.id}/bot")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["is_failed"] is True
    assert body["failure_reason"] is not None
    assert "no meeting was found" in body["status_display"].lower()


@pytest.mark.asyncio
async def test_calendar_get_disconnected(client: AppClient):
    response = await client.get("/api/users/me/calendar")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body == {
        "calendar_connected": False,
        "provider": None,
        "preference": "none",
        "calendar_user_id": None,
        "is_google_authenticated": True,
    }


@pytest.mark.asyncio
async def test_calendar_get_connected(client: AppClient):
    user = await client.get_default_user()
    await user.add_integration(Integration.RECALL_AI_CALENDAR)
    await RecallAICalendarUser.create(
        id="cal-user-1",
        external_id="ext-1",
        user_id=user.id,
        connections=[{"provider": "google_calendar", "connected": True}],
        preferences=RECALL_AI_PREFERENCE_MAPPING["all"],
    )

    response = await client.get("/api/users/me/calendar")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["calendar_connected"] is True
    assert body["provider"] == "google"
    assert body["preference"] == "all"
    assert body["calendar_user_id"] == "cal-user-1"


@pytest.mark.asyncio
async def test_calendar_patch_updates_preference(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    await user.add_integration(Integration.RECALL_AI_CALENDAR)
    cal_user = await RecallAICalendarUser.create(
        id="cal-user-2",
        external_id="ext-2",
        user_id=user.id,
        connections=[{"provider": "microsoft_outlook", "connected": True}],
        preferences=RECALL_AI_PREFERENCE_MAPPING["none"],
    )

    async def fake_update(self, user_id, recording_preference):
        cal_user.preferences = RECALL_AI_PREFERENCE_MAPPING[recording_preference.value]
        await cal_user.save(update_fields=["preferences"])
        return True

    monkeypatch.setattr(
        "integrations.recall_ai.client.RecallAIClient.update_calendar_user_recording_preferences",
        fake_update,
    )

    response = await client.patch("/api/users/me/calendar", json={"preference": "all"})
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["preference"] == "all"
    assert body["provider"] == "microsoft"


@pytest.mark.asyncio
async def test_calendar_delete_removes_integration(client: AppClient, monkeypatch):
    user = await client.get_default_user()
    await user.add_integration(Integration.RECALL_AI_CALENDAR)
    await RecallAICalendarUser.create(
        id="cal-user-3",
        external_id="ext-3",
        user_id=user.id,
        connections=[{"provider": "google_calendar", "connected": True}],
        preferences=RECALL_AI_PREFERENCE_MAPPING["none"],
    )

    # Mirrors the real client which removes the integration as a side effect.
    async def fake_delete(self, user_id):
        target = await user.__class__.get(id=user_id)
        await target.remove_integration(Integration.RECALL_AI_CALENDAR)
        return True

    monkeypatch.setattr(
        "integrations.recall_ai.client.RecallAIClient.delete_calendar_user",
        fake_delete,
    )

    response = await client.delete("/api/users/me/calendar")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    await user.refresh_from_db()
    assert not user.is_integrated_with(Integration.RECALL_AI_CALENDAR)
    assert await RecallAICalendarUser.get_or_none(user_id=user.id) is None
