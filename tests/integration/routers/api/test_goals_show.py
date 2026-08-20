import pytest
from fastapi import status

from app.models.workspaces.goals import Goal, GoalComment
from config.enums import EventAction, GoalStatus
from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_goal_update, create_mailbox_entry, create_user


async def _create_goal_with_event(client: AppClient, **kwargs) -> Goal:
    """Create a goal via factory and record a GOAL_CREATED event so the timeline has data."""
    user = await client.get_default_user()
    defaults = {"organization_id": user.organization_id, "creator_id": user.id, "description": "Test goal"}
    goal = await create_goal(**{**defaults, **kwargs})
    await goal.fetch_related("workspace")
    async with goal.workspace.record(EventAction.GOAL_CREATED, creator_id=user.id):
        pass
    return goal


@pytest.mark.asyncio
async def test_timeline_returns_events_with_correct_structure(client: AppClient):
    goal = await _create_goal_with_event(client)

    response = await client.get(f"/api/goals/{goal.id}/timeline")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Timeline is content-only; seen-by / last-seen are derived client-side from the
    # collaborators view_state (no readers / last_seen_event_id / is_new fields here).
    assert "events" in data
    assert "last_seen_event_id" not in data

    assert len(data["events"]) >= 1
    created_event = data["events"][0]
    assert created_event["action"] == EventAction.GOAL_CREATED.value
    assert isinstance(created_event["details"], dict)
    assert created_event["replies"] == []
    assert created_event["comment"] is None
    assert created_event["goal_update"] is None


@pytest.mark.asyncio
async def test_timeline_comment_events_with_reply_grouping(client: AppClient):
    user = await client.get_default_user()
    goal = await _create_goal_with_event(client)

    parent_comment = await GoalComment.create(goal_id=goal.id, user_id=user.id, content="Parent comment")
    async with goal.workspace.record(EventAction.GOAL_COMMENTED, recordable=parent_comment, creator_id=user.id):
        pass

    reply_comment = await GoalComment.create(
        goal_id=goal.id, user_id=user.id, content="Reply", parent_id=parent_comment.id
    )
    async with goal.workspace.record(EventAction.GOAL_COMMENTED, recordable=reply_comment, creator_id=user.id):
        pass

    response = await client.get(f"/api/goals/{goal.id}/timeline")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    comment_events = [e for e in data["events"] if e["action"] == EventAction.GOAL_COMMENTED.value]
    assert len(comment_events) == 1

    parent_event = comment_events[0]
    assert parent_event["comment"]["content"] == "Parent comment"
    assert len(parent_event["replies"]) == 1
    assert parent_event["replies"][0]["comment"]["content"] == "Reply"


@pytest.mark.asyncio
async def test_timeline_goal_update_events(client: AppClient):
    user = await client.get_default_user()
    goal = await _create_goal_with_event(client)

    update = await create_goal_update(
        goal_id=goal.id,
        creator_id=user.id,
        question_text="How's it going?",
        answer_text="Great progress!",
        status=GoalStatus.ON_TRACK,
        progress=0.5,
    )
    async with goal.workspace.record(EventAction.GOAL_UPDATE_POSTED, recordable=update, creator_id=user.id):
        pass

    response = await client.get(f"/api/goals/{goal.id}/timeline")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    update_events = [e for e in data["events"] if e["action"] == EventAction.GOAL_UPDATE_POSTED.value]
    assert len(update_events) == 1

    update_event = update_events[0]
    assert update_event["goal_update"]["question_text"] == "How's it going?"
    assert update_event["goal_update"]["answer_text"] == "Great progress!"
    assert update_event["goal_update"]["status"] == GoalStatus.ON_TRACK.value
    assert update_event["goal_update"]["progress"] == 0.5


# Seen-by ("readers") and the "New activity" divider (last-seen) are no longer in the timeline
# response — they're derived client-side from the collaborators view_state query. Backend coverage
# for that view_state lives in tests/integration/routers/api/test_workspace_collaborators.py; the
# client derivation is covered by tests/javascript/react/features/goalShow/useGoalViewState.test.ts.


@pytest.mark.asyncio
async def test_show_resolves_mailbox_entry_from_query_param(client: AppClient):
    # A goal opened from the inbox carries ?mailbox_entry_id=; the show endpoint
    # resolves that (owner-scoped) entry so the island can render the MailboxActionBar.
    user = await client.get_default_user()
    goal = await _create_goal_with_event(client)
    entry = await create_mailbox_entry(
        resource_gid=goal.global_id,
        owner_id=user.id,
        organization_id=user.organization_id,
    )

    without_param = await client.get(f"/api/goals/{goal.id}")
    assert without_param.status_code == status.HTTP_200_OK
    assert without_param.json()["mailbox_entry"] is None

    with_param = await client.get(f"/api/goals/{goal.id}?mailbox_entry_id={entry.id}")
    assert with_param.status_code == status.HTTP_200_OK
    body = with_param.json()["mailbox_entry"]
    assert body["id"] == str(entry.id)
    assert body["is_unread"] is True
    assert body["is_archived"] is False

    # An entry the requester doesn't own resolves to null, not another user's state.
    other_user = await create_user(organization_id=user.organization_id)
    other_entry = await create_mailbox_entry(
        resource_gid=goal.global_id,
        owner_id=other_user.id,
        organization_id=user.organization_id,
    )
    not_owned = await client.get(f"/api/goals/{goal.id}?mailbox_entry_id={other_entry.id}")
    assert not_owned.status_code == status.HTTP_200_OK
    assert not_owned.json()["mailbox_entry"] is None


@pytest.mark.asyncio
async def test_timeline_access_control(client: AppClient):
    await client.get_default_user()
    other_org_user = await create_user()
    goal = await create_goal(
        organization_id=other_org_user.organization_id,
        creator_id=other_org_user.id,
        description="Other org goal",
    )

    response = await client.get(f"/api/goals/{goal.id}/timeline")
    assert response.status_code == status.HTTP_404_NOT_FOUND
