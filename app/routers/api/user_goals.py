from typing import cast
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.accounts import Group, User
from app.models.workspaces.goals import Goal
from app.routers.api.goals import (
    GoalResponse,
    _goal_response,
    _with_goal_expand,
    parse_expand,
)
from app.routers.dependencies import get_current_user

# /users/{user_id}/top_goal is a user-scoped goal projection that doesn't fit the
# /goals index contract: it returns a single goal (the user's spotlight pick), not
# a list. It could have been hung off /goals as a special-case query param, but it
# bypasses enough of the index contract that it reads cleaner as its own resource here.

router = APIRouter(tags=["goals"])


class TopGoalForUserResponse(BaseModel):
    top_goal: GoalResponse | None


@router.get("/users/{user_id}/top_goal", response_model=TopGoalForUserResponse)
async def api_users_top_goal(
    user_id: UUID,
    expand: frozenset[str] = Depends(parse_expand),
    current_user: User = Depends(get_current_user),
):
    # Highest-priority active, open, incomplete goal owned by `user_id`,
    # falling back to a goal from one of their groups if they own none.
    base_queryset = _with_goal_expand(
        Goal.filter(Goal.filters.by_active_open(current_user.organization_id) & Goal.filters.incomplete),
        expand,
    )
    group_ids = cast(
        list[UUID],
        await Group.filter(Group.filters.by_member(user_id)).values_list("id", flat=True),
    )
    picked_goal, _ = await Goal.top_goal_for_user(base_queryset, user_id=user_id, group_ids=group_ids)
    return TopGoalForUserResponse(top_goal=_goal_response(picked_goal, expand) if picked_goal else None)
