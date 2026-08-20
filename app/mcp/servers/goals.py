from urllib.parse import urljoin
from uuid import UUID

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from tortoise.expressions import Q

from app.mcp.auth import get_current_user
from app.models.workspaces.goals import Goal as GoalModel
from app.models.workspaces.goals import GoalComment
from app.presenters.goals import GoalCommentMCPPresenter, GoalMCPPresenter
from config import settings

GOAL_PREFETCH = (
    "subgoals__owner",
    "subgoals__group",
    "subgoals__comments__user",
    "subgoals__comments__replies__user",
    "owner",
    "group",
    "comments__user",
    "comments__replies__user",
)

server = FastMCP("Goals")


@server.tool(description="List top-level goals for the organization.")
async def list_goals(
    ctx: Context,
    is_completed: bool | None = None,
    is_closed: bool | None = None,
    status: str | None = None,
    owner_id: UUID | None = None,
    group_id: UUID | None = None,
    has_target_date: bool | None = None,
    target_date_before: str | None = None,
    target_date_after: str | None = None,
    search: str | None = None,
) -> list[GoalMCPPresenter]:
    user = await get_current_user(ctx)

    query = GoalModel.filter(GoalModel.filters.by_organization(user.organization_id) & GoalModel.filters.top_level)

    if is_completed:
        query = query.filter(GoalModel.filters.closed & GoalModel.filters.completed)
    elif is_closed:
        query = query.filter(GoalModel.filters.closed)
    else:
        query = query.exclude(GoalModel.filters.closed)

    if status:
        query = query.filter(status=status)
    if owner_id:
        query = query.filter(owner_id=owner_id)
    if group_id:
        query = query.filter(group_id=group_id)
    if has_target_date is True:
        query = query.filter(target_date__isnull=False)
    elif has_target_date is False:
        query = query.filter(target_date__isnull=True)
    if target_date_before:
        query = query.filter(target_date__lt=target_date_before)
    if target_date_after:
        query = query.filter(target_date__gt=target_date_after)
    if search:
        query = query.filter(Q(description__icontains=search) | Q(title__icontains=search))

    goals = await query.prefetch_related(*GOAL_PREFETCH)
    return GoalMCPPresenter.from_goals(goals)


@server.tool(
    description="Get a specific goal by ID, including its subgoals. "
    f"When given a goal URL like {urljoin(str(settings.base_url), '/goals#goal-{id}')}, "
    "extract the UUID after 'goal-'."
)
async def get_goal(ctx: Context, goal_id: UUID) -> GoalMCPPresenter:
    user = await get_current_user(ctx)

    goal = await GoalModel.get_or_none(
        id=goal_id,
        organization_id=user.organization_id,
    ).prefetch_related(*GOAL_PREFETCH)

    if not goal:
        raise ToolError(f"Goal not found: {goal_id}")

    return GoalMCPPresenter.from_goal(goal)


@server.tool(description="List all subgoals of a goal.")
async def list_subgoals(
    ctx: Context,
    goal_id: UUID,
    recursive: bool = False,
) -> list[GoalMCPPresenter]:
    user = await get_current_user(ctx)

    parent = await GoalModel.get_or_none(
        id=goal_id,
        organization_id=user.organization_id,
    )
    if not parent:
        raise ToolError(f"Goal not found: {goal_id}")

    if recursive:
        all_subgoals = await _get_recursive_subgoals(goal_id, user.organization_id)
        return GoalMCPPresenter.from_goals(all_subgoals)

    subgoals = await GoalModel.filter(
        parent_id=goal_id,
        organization_id=user.organization_id,
    ).prefetch_related(*GOAL_PREFETCH)

    return GoalMCPPresenter.from_goals(list(subgoals))


async def _get_recursive_subgoals(goal_id: UUID, organization_id: UUID) -> list[GoalModel]:
    result: list[GoalModel] = []
    direct_subgoals = await GoalModel.filter(
        parent_id=goal_id,
        organization_id=organization_id,
    ).prefetch_related(*GOAL_PREFETCH)

    for subgoal in direct_subgoals:
        result.append(subgoal)
        nested = await _get_recursive_subgoals(subgoal.id, organization_id)
        result.extend(nested)

    return result


@server.tool(description="Get comments for a goal.")
async def get_goal_comments(
    ctx: Context,
    goal_id: UUID,
    include_closed: bool = False,
) -> list[GoalCommentMCPPresenter]:
    user = await get_current_user(ctx)

    goal = await GoalModel.get_or_none(
        id=goal_id,
        organization_id=user.organization_id,
    ).prefetch_related("comments__user", "comments__replies__user")

    if not goal:
        raise ToolError(f"Goal not found: {goal_id}")

    replies_by_parent: dict[UUID, list[GoalComment]] = {}
    top_level = []

    for c in goal.comments:
        if c.is_top_level:
            if include_closed or not c.is_closed:
                top_level.append(c)
        elif c.parent_id:
            replies_by_parent.setdefault(c.parent_id, []).append(c)

    return GoalCommentMCPPresenter.from_comments(top_level, replies_by_parent)
