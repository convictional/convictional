from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from fastapi import status
from freezegun import freeze_time

from app.models.workspaces.meetings import MeetingAttendee
from config.enums import MeetingAttendeeStatus, Sharing
from config.settings import settings
from tests.helpers.app import AppClient
from tests.helpers.factories import create_meeting, create_meeting_collection, create_organization, create_user


@pytest.mark.asyncio
async def test_empty_envelope(client: AppClient):
    response = await client.get("/api/meetings")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"meetings": [], "next_cursor": None, "has_more": False}


@freeze_time("2026-04-15 12:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_returns_meeting_response_with_list_view_short_circuit(client: AppClient):
    user = await client.get_default_user()
    yesterday = datetime.now(UTC) - timedelta(days=1)
    meeting = await create_meeting(
        title="Past sync",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=yesterday,
        scheduled_end_at=yesterday + timedelta(hours=1),
        agenda="should not appear in list view",
    )

    response = await client.get("/api/meetings")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert len(data["meetings"]) == 1
    item = data["meetings"][0]
    assert item["id"] == str(meeting.id)
    assert item["title"] == "Past sync"
    assert item["source_url"] == f"/meetings/{meeting.id}"
    # for_list_view short-circuit: agenda Y-doc fetch + recurrence neighbor lookups
    # are skipped so a 25-row page doesn't pay 25× show-only round-trips.
    assert item["agenda"] == ""
    assert item["previous_meeting_id"] is None
    assert item["next_meeting_id"] is None


@freeze_time("2026-04-15 12:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_scheduled_window_and_completed_filters(client: AppClient):
    user = await client.get_default_user()
    now = datetime.now(UTC)

    yesterday = now - timedelta(days=1)
    past = await create_meeting(
        title="Yesterday standup",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=yesterday,
        scheduled_end_at=yesterday + timedelta(hours=1),
    )
    in_one_hour = now + timedelta(hours=1)
    today_upcoming = await create_meeting(
        title="Today later",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=in_one_hour,
        scheduled_end_at=in_one_hour + timedelta(minutes=30),
    )
    tomorrow = now + timedelta(days=1)
    future = await create_meeting(
        title="Tomorrow planning",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=tomorrow,
        scheduled_end_at=tomorrow + timedelta(hours=1),
    )

    # Today window (nav-menu shape): scheduled_after start-of-day, scheduled_before tomorrow-start,
    # not-yet-completed only.
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_tomorrow = start_of_today + timedelta(days=1)
    response = await client.get(
        "/api/meetings",
        params={
            "scheduled_after": start_of_today.isoformat(),
            "scheduled_before": start_of_tomorrow.isoformat(),
            "completed": "false",
            "sort": "scheduled_at_asc",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert [m["id"] for m in response.json()["meetings"]] == [str(today_upcoming.id)]

    # Past window: scheduled_before now + completed=true.
    response = await client.get(
        "/api/meetings",
        params={"scheduled_before": now.isoformat(), "completed": "true"},
    )
    assert [m["id"] for m in response.json()["meetings"]] == [str(past.id)]

    # Upcoming window: scheduled_after now.
    response = await client.get(
        "/api/meetings",
        params={"scheduled_after": now.isoformat(), "sort": "scheduled_at_asc"},
    )
    assert [m["id"] for m in response.json()["meetings"]] == [str(today_upcoming.id), str(future.id)]


@pytest.mark.asyncio
async def test_scheduled_window_is_timezone_independent(client: AppClient):
    # A meeting fixed at a UTC instant must be findable via a window built in
    # any timezone, since the comparison is on absolute instants. Locks in that
    # callers in different browser TZs see the same data for the same instant.
    user = await client.get_default_user()
    instant = datetime(2026, 4, 15, 6, 0, tzinfo=UTC)
    meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=instant,
        scheduled_end_at=instant + timedelta(hours=1),
    )

    # Tokyo-local window covering the same UTC instant (15:00 JST = 06:00 UTC).
    tokyo = ZoneInfo("Asia/Tokyo")
    after_tokyo = datetime(2026, 4, 15, 14, 0, tzinfo=tokyo)
    before_tokyo = datetime(2026, 4, 15, 16, 0, tzinfo=tokyo)
    response = await client.get(
        "/api/meetings",
        params={"scheduled_after": after_tokyo.isoformat(), "scheduled_before": before_tokyo.isoformat()},
    )
    assert response.status_code == status.HTTP_200_OK
    assert [m["id"] for m in response.json()["meetings"]] == [str(meeting.id)]

    # Same instant in UTC: should match identically.
    response = await client.get(
        "/api/meetings",
        params={
            "scheduled_after": (instant - timedelta(minutes=30)).isoformat(),
            "scheduled_before": (instant + timedelta(minutes=30)).isoformat(),
        },
    )
    assert [m["id"] for m in response.json()["meetings"]] == [str(meeting.id)]


@pytest.mark.asyncio
async def test_naive_scheduled_window_rejected(client: AppClient):
    # The query parameters are typed AwareDatetime so a naive ISO string
    # (no offset, no Z) can't be misinterpreted against a TIMESTAMPTZ column.
    response = await client.get(
        "/api/meetings",
        params={"scheduled_after": "2026-04-15T12:00:00"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_collection_filter_404s_on_cross_org(client: AppClient):
    user = await client.get_default_user()
    collection = await create_meeting_collection(organization_id=user.organization_id)
    scheduled_at = datetime.now(UTC) - timedelta(days=1)
    in_collection = await create_meeting(
        title="In collection",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        collection_id=collection.id,
    )
    await create_meeting(
        title="Uncategorized",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
    )

    response = await client.get("/api/meetings", params={"collection_id": str(collection.id)})
    assert response.status_code == status.HTTP_200_OK
    assert [m["id"] for m in response.json()["meetings"]] == [str(in_collection.id)]

    other_org = await create_organization()
    cross_org_collection = await create_meeting_collection(organization_id=other_org.id)
    response = await client.get("/api/meetings", params={"collection_id": str(cross_org_collection.id)})
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response = await client.get("/api/meetings", params={"collection_id": str(uuid4())})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_sort_orders_results(client: AppClient):
    user = await client.get_default_user()
    base = datetime.now(UTC) - timedelta(days=10)
    ids = []
    for offset_hours in (0, 24, 48):
        scheduled_at = base + timedelta(hours=offset_hours)
        meeting = await create_meeting(
            title=f"M{offset_hours}",
            creator_id=user.id,
            organization_id=user.organization_id,
            scheduled_at=scheduled_at,
            scheduled_end_at=scheduled_at + timedelta(hours=1),
        )
        ids.append(str(meeting.id))

    response = await client.get("/api/meetings")
    assert [m["id"] for m in response.json()["meetings"]] == list(reversed(ids))

    response = await client.get("/api/meetings", params={"sort": "scheduled_at_asc"})
    assert [m["id"] for m in response.json()["meetings"]] == ids


@pytest.mark.asyncio
async def test_excludes_cross_org_inaccessible_and_declined(client: AppClient):
    user = await client.get_default_user()
    scheduled_at = datetime.now(UTC) - timedelta(days=1)

    visible = await create_meeting(
        title="Visible",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
    )

    # Cross-org meeting: invisible to this user.
    other_org = await create_organization()
    other_user = await create_user(organization_id=other_org.id)
    await create_meeting(
        title="Other org",
        creator_id=other_user.id,
        organization_id=other_org.id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
    )

    # Same-org but private to another collaborator the caller can't access.
    same_org_other = await create_user(organization_id=user.organization_id)
    await create_meeting(
        title="Other private",
        creator_id=same_org_other.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        sharing=Sharing.PRIVATE,
    )

    # Declined by the caller — excluded by the by_not_declined_by query filter.
    await create_meeting(
        title="Declined",
        creator_id=same_org_other.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        sharing=Sharing.ORGANIZATION,
        attendees=[MeetingAttendee(user_id=user.id, name=user.display_name, status=MeetingAttendeeStatus.DECLINED)],
    )

    response = await client.get("/api/meetings")
    assert [m["id"] for m in response.json()["meetings"]] == [str(visible.id)]


@pytest.mark.asyncio
async def test_completed_flag_distinguishes_transcript_and_time(client: AppClient):
    user = await client.get_default_user()
    now = datetime.now(UTC)

    # Completed via transcript even though end_at is in the future.
    upcoming_with_transcript = await create_meeting(
        title="Has transcript",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=now + timedelta(hours=1),
        scheduled_end_at=now + timedelta(hours=2),
        transcript="<recorded>",
    )

    # Not completed: future, no transcript.
    upcoming_plain = await create_meeting(
        title="Future plain",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=now + timedelta(hours=3),
        scheduled_end_at=now + timedelta(hours=4),
    )

    response = await client.get("/api/meetings", params={"completed": "true"})
    assert [m["id"] for m in response.json()["meetings"]] == [str(upcoming_with_transcript.id)]

    response = await client.get("/api/meetings", params={"completed": "false"})
    assert [m["id"] for m in response.json()["meetings"]] == [str(upcoming_plain.id)]


@freeze_time("2026-04-15 12:00:00", tz_offset=0)
@pytest.mark.asyncio
async def test_past_filter_mirrors_legacy_by_past(client: AppClient):
    # `past` is end-time based: ended OR (no end AND has transcript). It diverges
    # from `completed` for meetings with no scheduled_end_at — the /meetings React
    # island uses `past` to stay at parity with the legacy meetings_index page.
    user = await client.get_default_user()
    now = datetime.now(UTC)

    ended = await create_meeting(
        title="Ended",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=now - timedelta(hours=3),
        scheduled_end_at=now - timedelta(hours=2),
    )
    no_end_with_transcript = await create_meeting(
        title="No end, transcribed",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=now - timedelta(hours=4),
        scheduled_end_at=None,
        transcript="<recorded>",
    )
    # No end, no transcript, started long ago: `completed` includes it, `past` does not.
    no_end_plain = await create_meeting(
        title="No end, plain",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=now - timedelta(hours=5),
        scheduled_end_at=None,
    )

    response = await client.get("/api/meetings", params={"past": "true"})
    assert {m["id"] for m in response.json()["meetings"]} == {str(ended.id), str(no_end_with_transcript.id)}

    # The divergence: `completed` additionally surfaces the end-less, transcript-less meeting.
    response = await client.get("/api/meetings", params={"completed": "true"})
    assert {m["id"] for m in response.json()["meetings"]} == {
        str(ended.id),
        str(no_end_with_transcript.id),
        str(no_end_plain.id),
    }


@pytest.mark.asyncio
async def test_include_declined_surfaces_declined_meetings(client: AppClient):
    # The past list opts in to show declined meetings, matching legacy meetings_index;
    # the default (used by the upcoming list + nav pill) hides them.
    user = await client.get_default_user()
    scheduled_at = datetime.now(UTC) - timedelta(days=1)
    same_org_other = await create_user(organization_id=user.organization_id)

    attended = await create_meeting(
        title="Attended",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
    )
    declined = await create_meeting(
        title="Declined",
        creator_id=same_org_other.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        sharing=Sharing.ORGANIZATION,
        attendees=[MeetingAttendee(user_id=user.id, name=user.display_name, status=MeetingAttendeeStatus.DECLINED)],
    )

    response = await client.get("/api/meetings", params={"past": "true"})
    assert [m["id"] for m in response.json()["meetings"]] == [str(attended.id)]

    response = await client.get("/api/meetings", params={"past": "true", "include_declined": "true"})
    assert {m["id"] for m in response.json()["meetings"]} == {str(attended.id), str(declined.id)}


@pytest.mark.asyncio
async def test_uncategorized_filter(client: AppClient):
    # Mirrors the legacy /meetings?filter=uncategorized view: only meetings with
    # no collection. A real collection_id supersedes it, matching the server.
    user = await client.get_default_user()
    collection = await create_meeting_collection(organization_id=user.organization_id)
    scheduled_at = datetime.now(UTC) - timedelta(days=1)

    in_collection = await create_meeting(
        title="In collection",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        collection_id=collection.id,
    )
    uncategorized = await create_meeting(
        title="Uncategorized",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
    )

    response = await client.get("/api/meetings", params={"uncategorized": "true"})
    assert [m["id"] for m in response.json()["meetings"]] == [str(uncategorized.id)]

    # collection_id wins when both are passed.
    response = await client.get(
        "/api/meetings",
        params={"uncategorized": "true", "collection_id": str(collection.id)},
    )
    assert [m["id"] for m in response.json()["meetings"]] == [str(in_collection.id)]


@pytest.mark.asyncio
async def test_declined_filter_does_not_consume_page_slots(client: AppClient):
    # Declined meetings are filtered in the query, not after pagination. A full
    # page of declined meetings ahead of the visible ones must not push the
    # visible meetings off the first page (the pre-fix bug returned an empty
    # first page with has_more=true, stranding the real meetings behind it).
    user = await client.get_default_user()
    same_org_other = await create_user(organization_id=user.organization_id)
    now = datetime.now(UTC)

    # A full page of declined meetings, all more recent so they sort first.
    for i in range(settings.pagination_default_per_page):
        scheduled_at = now - timedelta(days=1, minutes=i)
        await create_meeting(
            title=f"Declined {i}",
            creator_id=same_org_other.id,
            organization_id=user.organization_id,
            scheduled_at=scheduled_at,
            scheduled_end_at=scheduled_at + timedelta(hours=1),
            sharing=Sharing.ORGANIZATION,
            attendees=[
                MeetingAttendee(user_id=user.id, name=user.display_name, status=MeetingAttendeeStatus.DECLINED)
            ],
        )

    older = now - timedelta(days=10)
    visible = await create_meeting(
        title="Visible",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=older,
        scheduled_end_at=older + timedelta(hours=1),
    )

    response = await client.get("/api/meetings", params={"sort": "scheduled_at_desc"})
    body = response.json()
    assert [m["id"] for m in body["meetings"]] == [str(visible.id)]
    assert body["has_more"] is False
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_scope_member_excludes_org_shared_meetings(client: AppClient):
    # The upcoming list passes scope=member to restore the legacy Meeting.by_user
    # scope (creator/collaborator only). An org-shared meeting the caller neither
    # created nor collaborates on is visible under the default org scope but
    # hidden under scope=member.
    user = await client.get_default_user()
    same_org_other = await create_user(organization_id=user.organization_id)
    scheduled_at = datetime.now(UTC) + timedelta(hours=2)

    mine = await create_meeting(
        title="Mine",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
    )
    org_shared = await create_meeting(
        title="Org shared",
        creator_id=same_org_other.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        sharing=Sharing.ORGANIZATION,
    )

    org_scoped = await client.get("/api/meetings")
    assert {m["id"] for m in org_scoped.json()["meetings"]} == {str(mine.id), str(org_shared.id)}

    member_scoped = await client.get("/api/meetings", params={"scope": "member"})
    assert [m["id"] for m in member_scoped.json()["meetings"]] == [str(mine.id)]


@pytest.mark.asyncio
async def test_has_agenda_flag_survives_list_view_blanking(client: AppClient):
    # List rows blank the agenda string to skip the per-row Y-doc fetch, but
    # has_agenda still reports whether a (text or collaborative) agenda exists —
    # the upcoming row's "Agenda set / No agenda" indicator reads it.
    user = await client.get_default_user()
    past = datetime.now(UTC) - timedelta(days=1)

    with_agenda = await create_meeting(
        title="With agenda",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=past,
        scheduled_end_at=past + timedelta(hours=1),
        agenda="Discuss roadmap",
    )
    without_agenda = await create_meeting(
        title="No agenda",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=past - timedelta(hours=1),
        scheduled_end_at=past,
    )

    response = await client.get("/api/meetings", params={"sort": "scheduled_at_desc"})
    by_id = {m["id"]: m for m in response.json()["meetings"]}
    assert by_id[str(with_agenda.id)]["agenda"] == ""
    assert by_id[str(with_agenda.id)]["has_agenda"] is True
    assert by_id[str(without_agenda.id)]["has_agenda"] is False


@pytest.mark.asyncio
async def test_is_declined_flag_reflects_requesting_user(client: AppClient):
    # is_declined is per-requesting-user; with include_declined the upcoming list
    # keeps declined meetings so the row can strike them through.
    user = await client.get_default_user()
    same_org_other = await create_user(organization_id=user.organization_id)
    past = datetime.now(UTC) - timedelta(days=1)

    declined = await create_meeting(
        title="Declined",
        creator_id=same_org_other.id,
        organization_id=user.organization_id,
        scheduled_at=past,
        scheduled_end_at=past + timedelta(hours=1),
        sharing=Sharing.ORGANIZATION,
        attendees=[MeetingAttendee(user_id=user.id, name=user.display_name, status=MeetingAttendeeStatus.DECLINED)],
    )
    attended = await create_meeting(
        title="Attended",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=past - timedelta(hours=1),
        scheduled_end_at=past,
    )

    response = await client.get(
        "/api/meetings", params={"past": "true", "include_declined": "true", "sort": "scheduled_at_desc"}
    )
    by_id = {m["id"]: m for m in response.json()["meetings"]}
    assert by_id[str(declined.id)]["is_declined"] is True
    assert by_id[str(attended.id)]["is_declined"] is False
