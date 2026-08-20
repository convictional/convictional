import pytest

from app.models.collaboration.workspace import ViewStateResolver, Visit, Workspace
from config.enums import EventAction
from tests.helpers.factories import create_event, create_goal, create_user


@pytest.mark.asyncio
async def test_for_workspace_returns_visit_derived_state_and_unviewed_default():
    creator = await create_user()
    viewer = await create_user(organization_id=creator.organization_id)
    never_viewed = await create_user(organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    workspace = await Workspace.get(id=goal.workspace_id)
    event = await create_event(workspace, creator_id=creator.id, action=EventAction.GOAL_COMMENTED)
    await Visit.record(user_id=viewer.id, workspace_id=workspace.id, last_event_id=event.id)

    states = await ViewStateResolver.for_workspace(workspace.id, [viewer.id, never_viewed.id])

    viewed = states[viewer.id]
    assert viewed.viewed is True
    assert viewed.last_viewed_at is not None
    assert viewed.last_viewed_event_id == event.id
    # The cursor event's created_at is resolved without a second query (prefetched last_event).
    assert viewed.last_viewed_event_at == event.created_at

    # A collaborator with no Visit resolves to the unviewed default.
    unviewed = states[never_viewed.id]
    assert unviewed.viewed is False
    assert unviewed.last_viewed_at is None
    assert unviewed.last_viewed_event_id is None
    assert unviewed.last_viewed_event_at is None


@pytest.mark.asyncio
async def test_for_user_returns_state_per_workspace():
    creator = await create_user()
    viewer = await create_user(organization_id=creator.organization_id)
    seen_goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)
    unseen_goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    await Visit.record(user_id=viewer.id, workspace_id=seen_goal.workspace_id)

    states = await ViewStateResolver.for_user(viewer.id, [seen_goal.workspace_id, unseen_goal.workspace_id])

    assert states[seen_goal.workspace_id].viewed is True
    assert states[seen_goal.workspace_id].last_viewed_at is not None
    assert states[unseen_goal.workspace_id].viewed is False


@pytest.mark.asyncio
async def test_for_user_in_workspace_returns_single_state():
    creator = await create_user()
    viewer = await create_user(organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)
    await Visit.record(user_id=viewer.id, workspace_id=goal.workspace_id)

    state = await ViewStateResolver.for_user_in_workspace(viewer.id, goal.workspace_id)
    assert state.viewed is True

    missing = await ViewStateResolver.for_user_in_workspace(creator.id, goal.workspace_id)
    assert missing.viewed is False
