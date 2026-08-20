import pytest
from fastapi import status

from app.models.collaboration.workspace import Event, Visit
from app.models.workspaces.goals import GoalComment
from config.enums import EventAction
from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_user


@pytest.mark.asyncio
async def test_workspace_visit_recording(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)

    # Record visit without event
    response = await client.post(f"/api/workspaces/{goal.workspace_id}/visits")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    visit = await Visit.get(user_id=user.id, workspace_id=goal.workspace_id)
    assert visit.last_event_id is None

    # Record visit with event
    comment = GoalComment(goal_id=goal.id, user_id=user.id)
    async with goal.workspace.record(EventAction.COMMENTED, recordable=comment, creator_id=user.id) as recording:
        await comment.save(recording.using_db)
    event = await Event.all().order_by("-created_at").first()
    assert event is not None

    response = await client.post(f"/api/workspaces/{goal.workspace_id}/visits", json={"last_event_id": str(event.id)})
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await visit.refresh_from_db()
    assert visit.last_event_id == event.id

    # An event from another workspace can't be used as this workspace's cursor
    other_user = await create_user()
    other_goal = await create_goal(creator_id=other_user.id, organization_id=other_user.organization_id)
    foreign_comment = GoalComment(goal_id=other_goal.id, user_id=other_user.id)
    async with other_goal.workspace.record(
        EventAction.COMMENTED, recordable=foreign_comment, creator_id=other_user.id
    ) as recording:
        await foreign_comment.save(recording.using_db)
    foreign_event = await Event.filter(workspace_id=other_goal.workspace_id).order_by("-created_at").first()
    assert foreign_event is not None

    response = await client.post(
        f"/api/workspaces/{goal.workspace_id}/visits", json={"last_event_id": str(foreign_event.id)}
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    await visit.refresh_from_db()
    assert visit.last_event_id == event.id  # cursor unchanged by the rejected request

    # Cross-org access denied
    response = await client.post(f"/api/workspaces/{other_goal.workspace_id}/visits")
    assert response.status_code == status.HTTP_404_NOT_FOUND
