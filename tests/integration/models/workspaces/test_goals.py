import pytest

from app.models.collaboration.workspace import Collaborator, Subscription
from app.models.workspaces.goals import Goal, GoalComment
from config.enums import GoalStatus
from infra.db import transaction
from tests.helpers.factories import (
    create_goal,
    create_goal_comment,
    create_group,
    create_group_member,
    create_user,
)


@pytest.mark.asyncio
async def test_goal_comment_threading_and_state():
    user = await create_user()
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)

    parent = await create_goal_comment(goal_id=goal.id, user_id=user.id)
    assert parent.is_top_level and parent.is_open

    reply = await create_goal_comment(goal_id=goal.id, user_id=user.id, parent_id=parent.id)
    assert reply.is_reply and reply.parent_id == parent.id

    await parent.fetch_related("replies")
    assert parent.replies[0].id == reply.id

    await parent.close()
    assert parent.is_closed
    await parent.open()
    assert parent.is_open

    await parent.soft_delete()
    assert await GoalComment.filter(id=parent.id).count() == 0


@pytest.mark.asyncio
async def test_group_member_removal_preserves_goal_subscription_rows():
    creator = await create_user()
    member = await create_user(organization_id=creator.organization_id)
    group = await create_group(organization_id=creator.organization_id)
    group_member = await create_group_member(group_id=group.id, user_id=member.id)

    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)
    await goal.fetch_related("workspace")

    # Member is a collaborator (for access), not a subscriber-by-row.
    collaborator = await Collaborator.get_or_none(workspace_id=goal.workspace_id, user_id=member.id)
    assert collaborator is not None
    assert await Subscription.get_or_none(workspace_id=goal.workspace_id, subscriber_id=member.id) is None

    # If the member explicitly subscribes, the row persists across group removal.
    await goal.workspace.subscribe(member.id)
    row = await Subscription.get(workspace_id=goal.workspace_id, subscriber_id=member.id)
    assert row.wants_all

    await group_member.delete()
    await row.refresh_from_db()
    assert row.wants_all


@pytest.mark.asyncio
async def test_top_goal_for_user():
    user = await create_user()
    org_id = user.organization_id
    base_qs = Goal.filter(Goal.filters.by_active_open(org_id))

    # No goals → returns (None, 0)
    goal, pool_size = await Goal.top_goal_for_user(base_qs, user_id=user.id, group_ids=[])
    assert goal is None and pool_size == 0

    # Single owned goal → returned with pool_size = 1
    owned = await create_goal(creator_id=user.id, organization_id=org_id, owner_id=user.id)
    goal, pool_size = await Goal.top_goal_for_user(base_qs, user_id=user.id, group_ids=[])
    assert goal is not None and goal.id == owned.id and pool_size == 1

    # Multiple owned goals → highest priority returned, pool_size = total owned
    await create_goal(creator_id=user.id, organization_id=org_id, owner_id=user.id, status=GoalStatus.OFF_TRACK)
    goal, pool_size = await Goal.top_goal_for_user(base_qs, user_id=user.id, group_ids=[])
    assert goal is not None and goal.status == GoalStatus.OFF_TRACK and pool_size == 2

    # Group goal fallback when user owns nothing — pool_size reflects the group pool
    other_user = await create_user(organization_id=org_id)
    group = await create_group(organization_id=org_id)
    group_goal = await create_goal(creator_id=other_user.id, organization_id=org_id, group_id=group.id)
    goal, pool_size = await Goal.top_goal_for_user(base_qs, user_id=other_user.id, group_ids=[group.id])
    assert goal is not None and goal.id == group_goal.id and pool_size == 1

    # Owned goals win over group goals even when both exist
    await create_goal(creator_id=other_user.id, organization_id=org_id, owner_id=other_user.id)
    goal, pool_size = await Goal.top_goal_for_user(base_qs, user_id=other_user.id, group_ids=[group.id])
    assert goal is not None and goal.owner_id == other_user.id and pool_size == 1


@pytest.mark.asyncio
async def test_top_goals_for_users():
    owner = await create_user()
    org_id = owner.organization_id
    other_user = await create_user(organization_id=org_id)
    group = await create_group(organization_id=org_id)
    await create_group_member(group_id=group.id, user_id=other_user.id)

    await create_goal(creator_id=owner.id, organization_id=org_id, owner_id=owner.id)
    await create_goal(creator_id=owner.id, organization_id=org_id, owner_id=owner.id)
    group_goal = await create_goal(creator_id=owner.id, organization_id=org_id, group_id=group.id)

    top_goals, extra_counts = await Goal.top_goals_for_users([owner, other_user], org_id)

    # Owner gets highest priority owned goal, extra_count reflects remaining
    assert owner.id in top_goals
    assert extra_counts[owner.id] == 1

    # other_user owns no goals → falls back to group goal
    assert top_goals[other_user.id].id == group_goal.id
    assert extra_counts.get(other_user.id, 0) == 0

    # User with no goals at all is absent from results
    no_goals_user = await create_user(organization_id=org_id)
    top_goals, _ = await Goal.top_goals_for_users([no_goals_user], org_id)
    assert no_goals_user.id not in top_goals


@pytest.mark.asyncio
async def test_next_position_in_scope():
    user = await create_user()
    top_level_scope = Goal.filter(organization_id=user.organization_id, parent_id=None)

    async with transaction() as connection:
        # Returns 1 for empty scope
        assert await Goal.next_position_in_scope(top_level_scope, connection) == 1

    # Create goals with specific positions
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, position=10)
    await create_goal(organization_id=user.organization_id, creator_id=user.id, parent_id=parent.id, position=3)
    subgoal_scope = Goal.filter(parent_id=parent.id)

    async with transaction() as connection:
        # Returns max + 1 for top-level goals
        assert await Goal.next_position_in_scope(top_level_scope, connection) == 11
        # Respects scope filter for subgoals
        assert await Goal.next_position_in_scope(subgoal_scope, connection) == 4


@pytest.mark.asyncio
async def test_select_highest_priority():
    user = await create_user()
    org_id = user.organization_id

    # Lower position wins when status is equal
    first = await create_goal(creator_id=user.id, organization_id=org_id, position=0)
    second = await create_goal(creator_id=user.id, organization_id=org_id, position=1)
    assert Goal.select_highest_priority([first, second]).id == first.id

    # Sorts internally — input order doesn't matter
    assert Goal.select_highest_priority([second, first]).id == first.id

    # Off track at a middle position outweighs on track at the top
    off_track = await create_goal(creator_id=user.id, organization_id=org_id, position=1, status=GoalStatus.OFF_TRACK)
    assert Goal.select_highest_priority([first, off_track, second]).id == off_track.id

    # At risk beats on track at same position
    at_risk = await create_goal(creator_id=user.id, organization_id=org_id, position=0, status=GoalStatus.AT_RISK)
    assert Goal.select_highest_priority([first, at_risk]).id == at_risk.id
