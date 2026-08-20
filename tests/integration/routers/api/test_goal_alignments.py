from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi import status
from freezegun import freeze_time

from app.models.accounts import User
from app.models.collaboration.content import Content, IndexMetadata, SearchableData
from app.models.collaboration.workspace import Event
from app.models.workspaces.goals import GoalAlignment
from app.routers.api.goal_alignments import (
    TimelineProgressEvent,
    TimelineStatusChange,
    _timeline_data,
    _week_start,
)
from config.enums import ContentCategory, ContentType, EventAction, GoalStatus, Sharing, SignalStrength
from tests.helpers.app import AppClient
from tests.helpers.factories import create_content, create_goal, create_goal_update, create_group, create_user


async def org_member(**kwargs) -> User:
    return await create_user(email="alignments-admin@example.com", **kwargs)


async def create_alignment(goal, content: Content, organization, signal=SignalStrength.STRONG, **kwargs):
    return await GoalAlignment.create(
        goal=goal,
        content=content,
        content_indexed_at=content.last_indexed_at,
        organization=organization,
        signal=signal,
        alignment_score=0.85,
        description="Relevant to the goal",
        **kwargs,
    )


@pytest.mark.asyncio
async def test_overview(client: AppClient):
    user = await org_member()
    client.current_user = user
    org = await user.organization
    group = await create_group(organization_id=user.organization_id, name="Q1 Priorities")
    grouped = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, title="Revenue Growth", group_id=group.id
    )
    ungrouped = await create_goal(organization_id=user.organization_id, creator_id=user.id, title="Hire Engineers")

    c1 = await create_content(organization_id=user.organization_id)
    c2 = await create_content(organization_id=user.organization_id)
    c3 = await create_content(organization_id=user.organization_id)
    await create_alignment(grouped, c1, org, signal=SignalStrength.STRONG)
    await create_alignment(grouped, c2, org, signal=SignalStrength.MEDIUM)
    await create_alignment(ungrouped, c3, org, signal=SignalStrength.STRONG)
    removed = await create_alignment(ungrouped, await create_content(organization_id=user.organization_id), org)
    await removed.soft_delete()

    response = await client.get("/api/goal_alignments")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    assert len(body["groups"]) == 1
    assert body["groups"][0]["name"] == "Q1 Priorities"
    grouped_summary = body["groups"][0]["goals"][0]
    assert grouped_summary["name"] == "Revenue Growth"
    assert grouped_summary["activity"] == 2
    assert grouped_summary["signal_counts"] == {"strong": 1, "medium": 1}
    assert f"/goals/{grouped.id}/alignments" in grouped_summary["url"]

    assert len(body["ungrouped_goals"]) == 1
    ungrouped_summary = body["ungrouped_goals"][0]
    assert ungrouped_summary["name"] == "Hire Engineers"
    # The soft-deleted alignment is excluded from counts.
    assert ungrouped_summary["activity"] == 1
    assert ungrouped_summary["signal_counts"] == {"strong": 1}
    assert ungrouped_summary["group_id"] is None


@pytest.mark.asyncio
async def test_show_list_and_timeline(client: AppClient):
    user = await org_member()
    client.current_user = user
    org = await user.organization
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        activated_at=datetime(2026, 1, 5, tzinfo=UTC),
    )

    content = await create_content(organization_id=user.organization_id, title="Q1 Sales Report")
    hidden = await create_content(organization_id=user.organization_id, title="Hidden Report")
    alignment = await create_alignment(goal, content, org, pinned_by=user)
    removed = await create_alignment(goal, hidden, org)
    await removed.soft_delete()

    # Same content aligned across two index runs -> one card after dedupe.
    dup_content = await create_content(organization_id=user.organization_id, title="Recurring Report")
    for indexed_at in (datetime(2026, 1, 6, tzinfo=UTC), datetime(2026, 1, 13, tzinfo=UTC)):
        await GoalAlignment.create(
            goal=goal,
            content=dup_content,
            content_indexed_at=indexed_at,
            organization=org,
            signal=SignalStrength.STRONG,
            alignment_score=0.85,
            description="Recurring",
        )

    response = await client.get(f"/api/goals/{goal.id}/alignments")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    titles = [a["content"]["title"] for a in body["alignments"]]
    assert "Q1 Sales Report" in titles
    assert "Hidden Report" not in titles
    assert titles.count("Recurring Report") == 1  # deduped by content_id

    pinned_card = next(a for a in body["alignments"] if a["content"]["title"] == "Q1 Sales Report")
    assert pinned_card["pinned"] is True
    assert pinned_card["score"] == 1.0  # pinned overrides alignment_score
    assert pinned_card["alignment_score"] == 0.85
    assert pinned_card["signal"] == SignalStrength.STRONG.value
    assert pinned_card["created_by"] is None
    assert pinned_card["id"] == str(alignment.id)

    timeline = body["timeline"]
    assert {b["week"] for b in timeline["weekly_activity"]}  # non-empty buckets
    assert "today_week_index" in timeline
    assert "progress_events" in timeline
    assert "status_changes" in timeline
    assert timeline["start_date"] == _week_start(goal.activated_at.date()).isoformat()


@pytest.mark.asyncio
@freeze_time("2026-01-19")
async def test_timeline_data(client: AppClient):
    user = await org_member()
    client.current_user = user
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        activated_at=datetime(2026, 1, 5, tzinfo=UTC),
        target_date=date(2026, 3, 31),
        status=GoalStatus.ON_TRACK,
        progress=0.4,
    )
    org = await goal.organization

    content1 = await create_content(
        organization_id=user.organization_id, last_indexed_at=datetime(2026, 1, 6, tzinfo=UTC)
    )
    content2 = await create_content(
        organization_id=user.organization_id, last_indexed_at=datetime(2026, 1, 7, tzinfo=UTC)
    )
    content3 = await create_content(
        organization_id=user.organization_id, last_indexed_at=datetime(2026, 1, 19, tzinfo=UTC)
    )
    alignments = [
        await create_alignment(goal, content1, org),
        await create_alignment(goal, content2, org),
        await create_alignment(goal, content3, org),
    ]

    update = await create_goal_update(
        goal_id=goal.id,
        creator_id=user.id,
        completed_at=datetime(2026, 1, 12, tzinfo=UTC),
        progress=0.3,
        status=GoalStatus.ON_TRACK,
    )

    status_event = await Event.create(
        recordable_id=goal.id,
        recordable_type="Goal",
        action=EventAction.GOAL_UPDATED,
        details={"status": [GoalStatus.ON_TRACK.value, GoalStatus.AT_RISK.value]},
        created_at=datetime(2026, 1, 19, tzinfo=UTC),
        workspace_id=goal.workspace_id,
    )

    result = _timeline_data(goal, alignments, [update], [status_event])

    weeks = [b.week for b in result.weekly_activity]
    counts = {b.week: b.count for b in result.weekly_activity}
    assert weeks[0] == goal.activated_at.date().isoformat()
    assert weeks[-1] >= (goal.target_date - timedelta(days=6)).isoformat()
    assert counts[goal.activated_at.date().isoformat()] == 2
    assert counts[status_event.created_at.date().isoformat()] == 1
    assert counts.get(update.completed_at.date().isoformat(), 0) == 0

    assert result.progress_events == [TimelineProgressEvent(week_index=1, progress=0.3)]
    assert result.status_changes == [TimelineStatusChange(week_index=2, status=GoalStatus.AT_RISK.value)]
    assert result.current_progress == 0.4
    assert result.current_status == GoalStatus.ON_TRACK.value
    assert result.start_date == goal.activated_at.date().isoformat()
    assert result.end_date == goal.target_date.isoformat()
    assert result.today_week_index == next(i for i, w in enumerate(weeks) if w == date(2026, 1, 19).isoformat())

    # An update without explicit progress falls back to goal.progress.
    update.progress = None
    result = _timeline_data(goal, [], [update])
    assert result.progress_events[0].progress == 0.4

    # Malformed status events (no pair / single entry) are skipped.
    malformed1 = await Event.create(
        action=EventAction.GOAL_UPDATED,
        details={"other": "data"},
        workspace_id=goal.workspace_id,
        recordable_id=goal.id,
        recordable_type="Goal",
    )
    malformed2 = await Event.create(
        action=EventAction.GOAL_UPDATED,
        details={"status": [GoalStatus.ON_TRACK.value]},
        workspace_id=goal.workspace_id,
        recordable_id=goal.id,
        recordable_type="Goal",
    )
    result = _timeline_data(goal, [], [], [malformed1, malformed2])
    assert result.status_changes == []

    # No activated_at or target_date falls back to relative date ranges.
    goal.activated_at = None
    goal.target_date = None
    result = _timeline_data(goal, [], [])
    today = date(2026, 1, 19)
    expected_start = _week_start(today - timedelta(weeks=12))
    assert result.start_date == expected_start.isoformat()
    assert result.end_date == (today + timedelta(weeks=4)).isoformat()
    assert all(b.count == 0 for b in result.weekly_activity)


@pytest.mark.asyncio
async def test_search(client: AppClient):
    user = await org_member()
    client.current_user = user
    organization = await user.organization

    post = await create_content(organization=organization)
    await post.indexer.index(
        SearchableData("Quarterly Sales Review", "Sales review", "https://example.com/sales", "Jane Doe"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST, Sharing.ORGANIZATION),
    )

    response = await client.get("/api/goal_alignments/lookup?q=Sales")
    assert response.status_code == status.HTTP_200_OK
    titles = [r["title"] for r in response.json()["results"]]
    assert "Quarterly Sales Review" in titles

    # Below the 2-char minimum -> 422 (semantic validation).
    short = await client.get("/api/goal_alignments/lookup?q=S")
    assert short.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_search_scoring_cutoff(client: AppClient):
    user = await org_member()
    client.current_user = user
    organization = await user.organization
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    scoring_time = datetime(2026, 3, 9, tzinfo=UTC)

    old_content = await create_content(organization=organization)
    await old_content.indexer.index(
        SearchableData("Old Quarterly Review", "Old", "https://example.com/old", "Jane Doe"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST,
            Sharing.ORGANIZATION,
            created_at=scoring_time - timedelta(days=1),
        ),
    )
    new_content = await create_content(organization=organization)
    await new_content.indexer.index(
        SearchableData("New Quarterly Review", "New", "https://example.com/new", "Jane Doe"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.POST,
            Sharing.ORGANIZATION,
            created_at=scoring_time + timedelta(days=1),
        ),
    )

    # No scoring run yet -> cutoff bypassed, both searchable.
    before = await client.get("/api/goal_alignments/lookup?q=Quarterly Review")
    titles = [r["title"] for r in before.json()["results"]]
    assert "Old Quarterly Review" in titles
    assert "New Quarterly Review" in titles

    # A job-created alignment (created_by_id IS NULL) sets the cutoff.
    scored = await create_content(organization=organization, content_type=ContentType.POST)
    await GoalAlignment.create(
        goal=goal,
        content=scored,
        content_indexed_at=scored.last_indexed_at,
        organization=organization,
        signal=SignalStrength.STRONG,
        alignment_score=0.85,
        description="test",
        created_at=scoring_time,
    )

    after = await client.get("/api/goal_alignments/lookup?q=Quarterly Review")
    titles = [r["title"] for r in after.json()["results"]]
    assert "Old Quarterly Review" in titles
    assert "New Quarterly Review" not in titles


@pytest.mark.asyncio
async def test_create(client: AppClient):
    user = await org_member()
    client.current_user = user
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    content = await create_content(organization_id=user.organization_id, content_type=ContentType.POST)

    response = await client.post(
        f"/api/goals/{goal.id}/alignments",
        json={"content_id": str(content.id), "description": "Very relevant"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["description"] == "Very relevant"
    assert body["signal"] == SignalStrength.STRONG.value
    assert body["score"] == 1.0
    assert body["pinned"] is True
    assert body["created_by"]["id"] == str(user.id)
    assert body["content"]["id"] == str(content.id)

    alignment = await GoalAlignment.get(goal_id=goal.id, content_id=content.id)
    assert alignment.created_by_id == user.id

    # Duplicate live alignment -> 409.
    duplicate = await client.post(
        f"/api/goals/{goal.id}/alignments",
        json={"content_id": str(content.id), "description": "again"},
    )
    assert duplicate.status_code == status.HTTP_409_CONFLICT

    # Missing content -> 404.
    missing = await client.post(
        f"/api/goals/{goal.id}/alignments",
        json={"content_id": str(goal.id), "description": "nope"},
    )
    assert missing.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_restores_soft_deleted(client: AppClient):
    user = await org_member()
    client.current_user = user
    org = await user.organization
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    content = await create_content(organization_id=user.organization_id, content_type=ContentType.POST)
    alignment = await create_alignment(goal, content, org)
    original_updated_at = alignment.updated_at
    await alignment.soft_delete()

    response = await client.post(
        f"/api/goals/{goal.id}/alignments",
        json={"content_id": str(content.id), "description": "Re-added"},
    )
    # A restore refreshes an existing resource -> 200, not 201.
    assert response.status_code == status.HTTP_200_OK

    await alignment.refresh_from_db()
    assert alignment.deleted_at is None
    assert alignment.description == "Re-added"
    assert alignment.pinned_by_id == user.id
    assert alignment.updated_at > original_updated_at  # the save bumped updated_at


@pytest.mark.asyncio
async def test_delete(client: AppClient):
    user = await org_member()
    client.current_user = user
    org = await user.organization
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    content = await create_content(organization_id=user.organization_id)
    alignment = await create_alignment(goal, content, org)

    response = await client.delete(f"/api/goals/{goal.id}/alignments/{alignment.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    await alignment.refresh_from_db()
    assert alignment.deleted_at is not None

    # Idempotent: deleting an already-deleted alignment still returns 204.
    again = await client.delete(f"/api/goals/{goal.id}/alignments/{alignment.id}")
    assert again.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_patch_pin(client: AppClient):
    user = await org_member()
    client.current_user = user
    org = await user.organization
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    content = await create_content(organization_id=user.organization_id)
    alignment = await create_alignment(goal, content, org)
    assert alignment.pinned_by_id is None

    pinned = await client.patch(f"/api/goals/{goal.id}/alignments/{alignment.id}", json={"pinned": True})
    assert pinned.status_code == status.HTTP_200_OK
    assert pinned.json()["pinned"] is True
    assert pinned.json()["score"] == 1.0
    await alignment.refresh_from_db()
    assert alignment.pinned_by_id == user.id

    unpinned = await client.patch(f"/api/goals/{goal.id}/alignments/{alignment.id}", json={"pinned": False})
    assert unpinned.status_code == status.HTTP_200_OK
    assert unpinned.json()["pinned"] is False
    assert unpinned.json()["score"] == 0.85  # falls back to alignment_score when unpinned
    await alignment.refresh_from_db()
    assert alignment.pinned_by_id is None

    # Empty body has no recognised fields -> 422.
    empty = await client.patch(f"/api/goals/{goal.id}/alignments/{alignment.id}", json={})
    assert empty.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_non_superuser_allowed(client: AppClient):
    # Goal alignments are open to any authenticated org member — no superuser gating.
    member = await create_user()
    client.current_user = member
    goal = await create_goal(organization_id=member.organization_id, creator_id=member.id)

    paths = [
        "/api/goal_alignments",
        f"/api/goals/{goal.id}/alignments",
        "/api/goal_alignments/lookup?q=hi",
    ]
    for path in paths:
        response = await client.get(path)
        assert response.status_code == status.HTTP_200_OK, path


@pytest.mark.asyncio
async def test_missing_and_cross_org_goal_404(client: AppClient):
    user = await org_member()
    client.current_user = user

    missing = await client.get(f"/api/goals/{user.id}/alignments")
    assert missing.status_code == status.HTTP_404_NOT_FOUND

    other_user = await create_user(email="other-admin@example.com")
    other_goal = await create_goal(organization_id=other_user.organization_id, creator_id=other_user.id)
    cross_org = await client.get(f"/api/goals/{other_goal.id}/alignments")
    assert cross_org.status_code == status.HTTP_404_NOT_FOUND
