import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, date, datetime
from itertools import zip_longest
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field
from tortoise import BaseDBAsyncClient
from tortoise.expressions import Q
from tortoise.query_utils import Prefetch
from tortoise.queryset import QuerySet

from app.channels.goals import get_present_users
from app.helpers.users import user_avatar_url
from app.jobs.content import ContentIndexingJob
from app.jobs.goals import GenerateGoalTitleJob
from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Visit
from app.models.workspaces.goals import Goal, GoalComment
from app.presenters.activity import EventPresenter
from app.presenters.goals import GoalTimelinePresenter
from app.routers.api.schemas import (
    GoalMailboxEntryResponse,
    GroupResponse,
    PaginatedResponse,
    TimelineResponse,
    UserResponse,
)
from app.routers.api.serializers import build_timeline_response, group_response, user_response
from app.routers.dependencies import (
    Channel,
    get_current_user,
    get_goal,
    get_mailbox_entry_for_resource,
    handle_stream,
)
from config.enums import ChannelEventAction, ChannelEventResource, EventAction, GoalStatus
from infra.db import Pagination, allow_soft_deleted, transaction
from infra.jobs import enqueue_job
from infra.messaging import Topic
from lib.uuid import filter_valid_uuids

#
# Dependencies & shared querysets
#
#

goal_context: ContextVar[Goal | None] = ContextVar("goal_context", default=None)


def comment_prefetch(path: str = "comments") -> Prefetch:
    reply_qs = GoalComment.all().select_related("user__avatar_file")
    comment_qs = (
        GoalComment.all().select_related("user__avatar_file").prefetch_related(Prefetch("replies", queryset=reply_qs))
    )
    return Prefetch(path, queryset=comment_qs)


def subgoal_prefetch() -> Prefetch:
    subgoal_qs = (
        Goal.all().select_related("owner__avatar_file", "group", "workspace").prefetch_related(comment_prefetch())
    )
    return Prefetch("subgoals", queryset=subgoal_qs)


def parent_prefetch() -> Prefetch:
    # Fold the parent's joins into a Prefetch instead of layering
    # `select_related("parent__owner__avatar_file")` next to
    # `prefetch_related("parent__comments")`: the prefetch re-fetches the parent
    # without the select_related, leaving `parent.owner` as an unresolved QuerySet.
    parent_qs = Goal.all().select_related("owner__avatar_file", "group").prefetch_related(comment_prefetch())
    return Prefetch("parent", queryset=parent_qs)


@dataclass
class GoalFilterParams:
    queryset: QuerySet[Goal]
    current_user: User
    cursor: str | None = None
    is_completed: bool | None = None
    is_closed: bool | None = None
    planning_list_name: str | None = None
    owner_ids: list[str] | None = None
    group_ids: list[str] | None = None

    @classmethod
    async def create(
        cls,
        current_user: User = Depends(get_current_user),
        cursor: str | None = Query(None),
        is_completed: bool | None = Query(None),
        is_closed: bool | None = Query(None),
        planning_list_name: str | None = Query(None),
        owner_ids: list[str] | None = Query(None),
        group_ids: list[str] | None = Query(None),
    ):
        base_queryset = Goal.filter(
            Goal.filters.by_organization(current_user.organization_id) & Goal.filters.top_level
        )
        owner_ids = filter_valid_uuids(owner_ids)
        group_ids = filter_valid_uuids(group_ids)

        return cls(
            queryset=base_queryset,
            current_user=current_user,
            cursor=cursor,
            is_completed=is_completed,
            is_closed=is_closed,
            planning_list_name=planning_list_name,
            owner_ids=owner_ids,
            group_ids=group_ids,
        )

    @property
    def owner_uuids(self) -> list[UUID] | None:
        return [UUID(oid) for oid in self.owner_ids] if self.owner_ids else None

    @property
    def group_uuids(self) -> list[UUID] | None:
        return [UUID(gid) for gid in self.group_ids] if self.group_ids else None

    @property
    def is_filtered(self) -> bool:
        return bool(self.owner_ids or self.group_ids)

    @classmethod
    def from_view(cls, view: str, organization_id: UUID, current_user: User) -> "GoalFilterParams":
        base_queryset = Goal.filter(Goal.filters.by_organization(organization_id) & Goal.filters.top_level)
        params = cls(queryset=base_queryset, current_user=current_user)
        if view == "completed":
            params.is_completed = True
        elif view == "closed":
            params.is_closed = True
        elif view != "active":
            params.planning_list_name = view
        return params

    @property
    def view_name(self) -> str:
        if self.is_completed:
            return "completed"
        if self.is_closed:
            return "closed"
        if self.planning_list_name:
            return self.planning_list_name
        return "active"

    @property
    def is_active_or_planning(self) -> bool:
        return not self.is_completed and not self.is_closed

    def apply_base_filters(self):
        if self.planning_list_name:
            self.queryset = self.queryset.filter(
                Goal.filters.by_planning_list_name(self.planning_list_name) & Goal.filters.draft
            ).order_by("position", "created_at")
        elif self.is_completed:
            self.queryset = self.queryset.filter(Goal.filters.closed & Goal.filters.completed)
            self.queryset = self.queryset.order_by("-completed_at", "-created_at")
        elif self.is_closed:
            self.queryset = self.queryset.filter(Goal.filters.closed)
            self.queryset = self.queryset.order_by("-closed_at", "-created_at")
        else:
            self.queryset = (
                self.queryset.exclude(Goal.filters.closed)
                .filter(Goal.filters.activated)
                .order_by("position", "created_at")
            )

    async def _build_filter_with_parent_inclusion(self) -> Q | None:
        """Build a filter that includes goals matching owner/group criteria, plus parent goals
        that have subgoals matching those criteria (so the subgoals remain visible)."""
        if not self.owner_uuids and not self.group_uuids:
            return None

        direct_filter = Q()
        subgoal_filter = Q()
        if self.owner_uuids:
            direct_filter &= Q(owner_id__in=self.owner_uuids)
            subgoal_filter |= Q(owner_id__in=self.owner_uuids)
        if self.group_uuids:
            direct_filter &= Q(group_id__in=self.group_uuids)
            subgoal_filter |= Q(group_id__in=self.group_uuids)

        parent_ids = await Goal.filter(
            Goal.filters.by_organization(self.current_user.organization_id) & Goal.filters.subgoal & subgoal_filter
        ).values_list("parent_id", flat=True)

        result = direct_filter
        if parent_ids:
            result |= Q(id__in=parent_ids)
        return result

    async def apply(self, *, expand: frozenset[str] = frozenset({"subgoals"})):
        self.apply_base_filters()

        if filter_q := await self._build_filter_with_parent_inclusion():
            self.queryset = self.queryset.filter(filter_q)

        self.queryset = self.queryset.select_related("owner__avatar_file", "group", "workspace")

        prefetches: list[Prefetch] = [comment_prefetch()]
        if "parent" in expand:
            prefetches.append(parent_prefetch())

        if "subgoals" in expand:
            if self.is_filtered:
                # When filtering by owner or group, only prefetch subgoals that match those filters
                subgoal_filter = Q()
                if self.owner_uuids:
                    subgoal_filter &= Q(owner_id__in=self.owner_uuids)
                if self.group_uuids:
                    subgoal_filter &= Q(group_id__in=self.group_uuids)
                filtered_subgoal_qs = (
                    Goal.filter(subgoal_filter)
                    .select_related("owner__avatar_file", "group", "workspace")
                    .prefetch_related(comment_prefetch())
                )
                prefetches.append(Prefetch("subgoals", queryset=filtered_subgoal_qs))
            else:
                prefetches.append(subgoal_prefetch())

        self.queryset = self.queryset.prefetch_related(*prefetches)


async def get_goal_with_indexing(goal: Goal = Depends(get_goal)) -> Goal:
    goal_context.set(goal)
    return goal


async def index_goal(request: Request):
    yield
    if request.method.lower() in ["post", "put", "patch", "delete"]:
        if goal := goal_context.get():
            await enqueue_job(ContentIndexingJob.from_model(goal.organization_id, goal))


router = APIRouter(dependencies=[Depends(index_goal, scope="function")], tags=["goals"])


#
# Response models
#
#


# Slim projection used wherever a goal is referenced from another resource:
# as a subgoal of its parent, as the parent of a subgoal, etc. Holds the fields
# a UI needs to render a reference. The detail-only fields (`start_date`,
# `created_at`, `planning_list_name`, `subgoals`, `parent`) live on
# GoalResponse, which avoids recursion at nesting boundaries.
class GoalSummary(BaseModel):
    id: str
    workspace_id: str
    title: str | None
    description: str
    status: str
    progress: float | None
    target_date: date | None
    is_completed: bool
    is_closed: bool
    is_draft: bool
    owner: UserResponse | None
    group: GroupResponse | None
    open_comment_count: int


class GoalResponse(BaseModel):
    id: str
    workspace_id: str
    title: str | None
    description: str
    status: str
    progress: float | None
    target_date: date | None
    start_date: date | None
    is_completed: bool
    is_closed: bool
    is_draft: bool
    planning_list_name: str | None
    created_at: datetime
    owner: UserResponse | None
    group: GroupResponse | None
    open_comment_count: int
    # FK is always present; clients can identify the parent without paying the prefetch cost.
    parent_id: str | None
    # `parent` and `subgoals` are nullable expansions. `None` means the caller
    # did not request the expansion via `?expand=...`; `[]` for subgoals means
    # "expanded, no children." See `parse_expand`.
    parent: GoalSummary | None
    subgoals: list[GoalSummary] | None


class GoalShowResponse(GoalResponse):
    # Populated only when the request carries ?mailbox_entry_id= (the goal was
    # opened from the inbox); null otherwise. Lets the show island render the
    # MailboxActionBar, mirroring how the post show endpoint resolves its entry.
    mailbox_entry: GoalMailboxEntryResponse | None = None


class GoalListResponse(PaginatedResponse):
    goals: list[GoalResponse]
    planning_list_names: list[str] | None = None


#
# Request models
#
#


class CreateGoalRequest(BaseModel):
    description: str = Field(min_length=1)
    parent_id: UUID | None = None
    planning_list_name: str | None = None
    owner_id: UUID | None = None
    group_id: UUID | None = None
    target_date: date | None = None
    status: GoalStatus | None = None
    subgoal_titles: list[str] = Field(default_factory=list)
    subgoal_owner_ids: list[UUID] = Field(default_factory=list)


class UpdateGoalRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    status: GoalStatus | None = None
    owner_id: UUID | None = None
    clear_owner: bool = False
    group_id: UUID | None = None
    clear_group: bool = False
    target_date: date | None = None
    clear_target_date: bool = False
    is_completed: bool | None = None


class ActivatePlanningListSummary(BaseModel):
    planning_goals_count: int
    completed_count: int
    incomplete_count: int
    open_threads_count: int


class SortGoalsRequest(BaseModel):
    ids: list[UUID]
    view: str = "active"


class SortSubgoalsRequest(BaseModel):
    ids: list[UUID]


class CloseGoalRequest(BaseModel):
    is_completed: bool = False


#
# Helpers
#
#


def _open_comment_count(goal: Goal) -> int:
    return sum(1 for c in goal.comments if c.is_top_level and c.is_open)


ALLOWED_EXPAND_FIELDS = frozenset({"parent", "subgoals"})


def parse_expand(expand: list[str] | None = Query(None)) -> frozenset[str]:
    """Parse the `?expand=` query param. Accepts repeated (`?expand=a&expand=b`)
    and comma-separated (`?expand=a,b`) forms. Rejects unknown fields with 422
    so typos fail loudly instead of silently returning unexpanded responses."""
    if not expand:
        return frozenset()
    fields = {entry.strip() for raw in expand for entry in raw.split(",") if entry.strip()}
    if invalid := fields - ALLOWED_EXPAND_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown expand fields: {sorted(invalid)}. Allowed: {sorted(ALLOWED_EXPAND_FIELDS)}",
        )
    return frozenset(fields)


def goal_summary(goal: Goal) -> GoalSummary:
    return GoalSummary(
        id=str(goal.id),
        workspace_id=str(goal.workspace_id),
        title=goal.title,
        description=goal.description,
        status=goal.status.value,
        progress=goal.progress,
        target_date=goal.target_date,
        is_completed=goal.is_completed,
        is_closed=goal.is_closed,
        is_draft=goal.is_draft,
        owner=user_response(goal.owner),
        group=group_response(goal.group),
        open_comment_count=_open_comment_count(goal),
    )


def _goal_response(goal: Goal, expand: frozenset[str]) -> GoalResponse:
    return GoalResponse(
        id=str(goal.id),
        workspace_id=str(goal.workspace_id),
        title=goal.title,
        description=goal.description,
        status=goal.status.value,
        progress=goal.progress,
        target_date=goal.target_date,
        start_date=goal.start_date,
        is_completed=goal.is_completed,
        is_closed=goal.is_closed,
        is_draft=goal.is_draft,
        planning_list_name=goal.planning_list_name,
        created_at=goal.created_at,
        owner=user_response(goal.owner),
        group=group_response(goal.group),
        open_comment_count=_open_comment_count(goal),
        parent_id=str(goal.parent_id) if goal.parent_id else None,
        parent=goal_summary(goal.parent) if "parent" in expand and goal.parent is not None else None,
        subgoals=[goal_summary(s) for s in goal.subgoals] if "subgoals" in expand else None,
    )


def _with_goal_expand(queryset, expand: frozenset[str]):
    """Apply the select_related and prefetch_related chain a Goal queryset needs
    so `_goal_response(goal, expand)` can serialize without lazy loads. Use this
    anywhere a Goal queryset will be passed to `_goal_response` — keeps the
    expand → prefetch mapping in one place."""
    queryset = queryset.select_related("owner__avatar_file", "group", "workspace")
    prefetches: list[Prefetch] = [comment_prefetch()]
    if "parent" in expand:
        prefetches.append(parent_prefetch())
    if "subgoals" in expand:
        prefetches.append(subgoal_prefetch())
    return queryset.prefetch_related(*prefetches)


async def _fetch_goal_response(goal_id: UUID, expand: frozenset[str]) -> GoalResponse:
    goal = await _with_goal_expand(Goal.get(id=goal_id), expand)
    return _goal_response(goal, expand)


async def fetch_timeline(goal: Goal) -> GoalTimelinePresenter:
    """Build a GoalTimelinePresenter (content only) for the given goal.

    Pure read. Seen-by / last-seen state is not computed here — the client derives it from the
    shared collaborators view_state query. The read cursor is advanced solely by the GoalShow
    island (via POST /api/workspaces/{id}/visits) as new events arrive; there is no server-side
    visit recording on this path.
    """
    async with allow_soft_deleted():
        events = await goal.workspace.events.all()
        activity = await EventPresenter.create_from_list(events)
        return GoalTimelinePresenter(events=activity, goal_status=goal.status)


async def save_new_goal(
    current_user: User,
    description: str,
    parent_id: UUID | None = None,
    planning_list_name: str | None = None,
    owner_id: UUID | None = None,
    group_id: UUID | None = None,
    target_date: date | None = None,
    goal_status: GoalStatus | None = None,
    subgoal_params: list[tuple[str, str]] | None = None,
) -> tuple[Goal, Goal | None]:
    """Create a goal (or subgoal), record its event, and broadcast. Returns (goal, parent)."""
    is_subgoal = parent_id is not None
    parent: Goal | None = None

    if is_subgoal:
        parent = await Goal.get(id=parent_id, organization_id=current_user.organization_id)
        activated_at = datetime.now(UTC) if parent.is_active else None
        target_date = target_date or parent.target_date
        position_scope = Goal.filter(parent_id=parent_id)
    elif planning_list_name:
        activated_at = None
        position_scope = Goal.filter(
            Goal.filters.by_organization(current_user.organization_id)
            & Goal.filters.by_planning_list_name(planning_list_name)
            & Goal.filters.top_level
        )
    else:
        activated_at = datetime.now(UTC)
        position_scope = Goal.filter(
            Goal.filters.by_organization(current_user.organization_id)
            & Goal.filters.activated
            & Goal.filters.top_level
        )

    goal = Goal(
        title="",
        description=description,
        organization_id=current_user.organization_id,
        creator=current_user,
        owner_id=owner_id,
        group_id=group_id,
        parent_id=parent_id,
        target_date=target_date,
        status=goal_status or GoalStatus.ON_TRACK,
        activated_at=activated_at,
        planning_list_name=planning_list_name if not is_subgoal else None,
    )

    if planning_list_name and not is_subgoal:
        recorder = goal.workspace.record(EventAction.GOAL_CREATED, creator_id=current_user.id)
    else:
        notifier = Notifier(goal, current_user)
        recorder = notifier.record_and_notify(recordable=goal, action=EventAction.GOAL_CREATED)

    async with recorder as recording:
        goal.position = await Goal.next_position_in_scope(position_scope, recording.using_db)
        await goal.save(using_db=recording.using_db)

        for subgoal_title, subgoal_owner_id in subgoal_params or []:
            if not subgoal_title:
                continue
            subgoal = Goal(
                parent_id=goal.id,
                title="",
                description=subgoal_title,
                organization_id=current_user.organization_id,
                creator_id=current_user.id,
                owner_id=UUID(subgoal_owner_id) if subgoal_owner_id and isinstance(subgoal_owner_id, str) else None,
                activated_at=activated_at,
            )
            async with subgoal.workspace.record(
                EventAction.GOAL_CREATED, recordable=subgoal, creator_id=current_user.id
            ) as subgoal_recording:
                await subgoal.save(using_db=subgoal_recording.using_db)

    if not is_subgoal:
        await enqueue_job(GenerateGoalTitleJob(goal_id=goal.id))

    if parent:
        await parent.broadcast_update()
    else:
        await goal.broadcast_update()

    return goal, parent


async def save_goal_update(
    goal: Goal,
    current_user: User,
    should_generate_title: bool = False,
) -> None:
    """Persist an edited goal, record its event, and broadcast. Expects field mutations already applied."""
    parent: Goal | None = None
    is_planning_list = bool(goal.planning_list_name)
    if not is_planning_list and goal.parent_id:
        parent = await Goal.get(id=goal.parent_id)
        is_planning_list = bool(parent.planning_list_name)

    if is_planning_list:
        recorder = goal.workspace.record(EventAction.GOAL_UPDATED, creator_id=current_user.id)
    else:
        notifier = Notifier(goal, current_user)
        recorder = notifier.record_and_notify(action=EventAction.GOAL_UPDATED)

    async with recorder as recording:
        await goal.save(using_db=recording.using_db)
        await Visit.record(current_user.id, goal.workspace_id, recording.event.id, using_db=recording.using_db)

    if goal.parent_id:
        if not parent:
            parent = await Goal.get(id=goal.parent_id)
        await parent.broadcast_update()
    else:
        await goal.broadcast_update()

    if should_generate_title:
        await enqueue_job(GenerateGoalTitleJob(goal_id=goal.id))


#
# Endpoints
#
#


@router.get("/goals", response_model=GoalListResponse)
async def api_goals_index(
    filters: GoalFilterParams = Depends(GoalFilterParams.create),
    expand: frozenset[str] = Depends(parse_expand),
):
    await filters.apply(expand=expand)

    pagination = await Pagination.create(Goal, cursor=filters.cursor, queryset=filters.queryset)

    # Only fetch planning list names on the first page
    planning_list_names = None
    if not filters.cursor:
        planning_list_names = list(
            await Goal.filter(Goal.filters.by_organization(filters.current_user.organization_id) & Goal.filters.draft)
            .exclude(planning_list_name__isnull=True)
            .exclude(planning_list_name="")
            .order_by("planning_list_name")
            .distinct()
            .values_list("planning_list_name", flat=True)
        )

    return GoalListResponse(
        goals=[_goal_response(g, expand) for g in pagination.results],
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
        planning_list_names=planning_list_names,
    )


@router.post("/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED)
async def api_goals_create(
    body: CreateGoalRequest,
    expand: frozenset[str] = Depends(parse_expand),
    current_user: User = Depends(get_current_user),
):
    goal, _ = await save_new_goal(
        current_user=current_user,
        description=body.description,
        parent_id=body.parent_id,
        planning_list_name=body.planning_list_name,
        owner_id=body.owner_id,
        group_id=body.group_id,
        target_date=body.target_date,
        goal_status=body.status,
        subgoal_params=list(
            zip_longest(body.subgoal_titles, [str(uid) for uid in body.subgoal_owner_ids], fillvalue="")
        ),
    )

    return await _fetch_goal_response(goal.id, expand)


def _validated_planning_list_name(name: str = Path(..., min_length=1)) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="planning list name is required")
    return trimmed


@router.get("/goals/planning_lists/{name}", response_model=ActivatePlanningListSummary)
async def api_planning_list_show(
    name: str = Depends(_validated_planning_list_name),
    current_user: User = Depends(get_current_user),
):
    planning_goals, active_goals = await asyncio.gather(
        Goal.filter(Goal.filters.by_planning_list(current_user.organization_id, name)).prefetch_related("comments"),
        Goal.filter(Goal.filters.by_active_open_top_level(current_user.organization_id)).all(),
    )

    if not planning_goals:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="planning list not found")

    open_threads_count = sum(
        1 for goal in planning_goals for comment in goal.comments if comment.is_top_level and comment.is_open
    )
    completed_count = sum(1 for g in active_goals if g.is_completed)
    incomplete_count = len(active_goals) - completed_count

    return ActivatePlanningListSummary(
        planning_goals_count=len(planning_goals),
        completed_count=completed_count,
        incomplete_count=incomplete_count,
        open_threads_count=open_threads_count,
    )


async def _close_subgoals(parent: Goal, current_user: User, using_db: BaseDBAsyncClient | None = None) -> None:
    # A closed parent's subgoals must close too, otherwise they linger open and keep
    # generating update requests even though the parent reads as closed. Each subgoal
    # records its own GOAL_CLOSED event so its owner is notified and its timeline reflects
    # the close — hence Notifier per subgoal rather than a bulk update.
    await parent.fetch_related("subgoals__workspace", using_db=using_db)
    for subgoal in parent.subgoals:
        if subgoal.is_open:
            async with Notifier(subgoal, current_user).record_and_notify(
                action=EventAction.GOAL_CLOSED, using_db=using_db
            ) as recording:
                await subgoal.close(using_db=recording.using_db)


@router.post("/goals/planning_lists/{name}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def api_planning_list_activate(
    name: str = Depends(_validated_planning_list_name),
    current_user: User = Depends(get_current_user),
):
    planning_goals = await Goal.filter(
        Goal.filters.by_planning_list(current_user.organization_id, name)
    ).prefetch_related("workspace", "subgoals", "comments")

    if not planning_goals:
        return

    async with transaction() as connection:
        active_goals = await Goal.filter(
            Goal.filters.by_active_open_top_level(current_user.organization_id)
        ).prefetch_related("workspace", "subgoals")

        for goal in active_goals:
            action = EventAction.GOAL_COMPLETED if goal.is_completed else EventAction.GOAL_CLOSED
            async with goal.workspace.record(action, creator_id=current_user.id, using_db=connection):
                await goal.close(using_db=connection)
            await _close_subgoals(goal, current_user, using_db=connection)

        for goal in planning_goals:
            for comment in goal.comments:
                if comment.is_top_level and comment.is_open:
                    await comment.close(using_db=connection)
            async with goal.workspace.record(
                EventAction.GOAL_ACTIVATED, creator_id=current_user.id, using_db=connection
            ):
                await goal.activate(using_db=connection)

    for goal in active_goals + planning_goals:
        await enqueue_job(ContentIndexingJob.from_model(goal.organization_id, goal))

    await Goal.broadcast_index_views(current_user.organization_id, ["active", "closed", "completed", name])


@router.get("/goals/{goal_id}", response_model=GoalShowResponse)
async def api_goals_show(
    goal: Goal = Depends(get_goal),
    expand: frozenset[str] = Depends(parse_expand),
    mailbox_entry: MailboxEntry | None = Depends(get_mailbox_entry_for_resource),
):
    response = await _fetch_goal_response(goal.id, expand)
    mailbox_entry_response = GoalMailboxEntryResponse.from_entry(mailbox_entry) if mailbox_entry else None
    return GoalShowResponse(**response.model_dump(), mailbox_entry=mailbox_entry_response)


@router.get("/goals/{goal_id}/timeline", response_model=TimelineResponse)
async def api_goals_timeline(
    goal: Goal = Depends(get_goal),
):
    timeline = await fetch_timeline(goal)
    return build_timeline_response(timeline)


@router.patch("/goals/{goal_id}", response_model=GoalResponse)
async def api_goals_update(
    body: UpdateGoalRequest,
    goal: Goal = Depends(get_goal_with_indexing),
    expand: frozenset[str] = Depends(parse_expand),
    current_user: User = Depends(get_current_user),
):
    should_generate_title = bool(not goal.title and body.description and body.description != goal.description)

    if body.title is not None:
        goal.title = body.title or goal.title
    if body.description is not None:
        goal.description = body.description or goal.description
    if body.owner_id is not None:
        goal.owner_id = body.owner_id
    if body.clear_owner:
        goal.owner_id = None
    if body.group_id is not None:
        goal.group_id = body.group_id
    if body.clear_group:
        goal.group_id = None
    if body.status is not None:
        goal.status = body.status
    if body.target_date is not None:
        goal.target_date = body.target_date
    if body.clear_target_date:
        goal.target_date = None
    if body.is_completed is not None:
        goal.is_completed = body.is_completed

    await save_goal_update(
        goal,
        current_user,
        should_generate_title=should_generate_title,
    )

    return await _fetch_goal_response(goal.id, expand)


@router.post("/goals/{goal_id}/close", response_model=GoalResponse)
async def api_goals_close(
    body: CloseGoalRequest = CloseGoalRequest(),
    goal: Goal = Depends(get_goal_with_indexing),
    expand: frozenset[str] = Depends(parse_expand),
    current_user: User = Depends(get_current_user),
):
    action = EventAction.GOAL_COMPLETED if body.is_completed else EventAction.GOAL_CLOSED
    notifier = Notifier(goal, current_user)
    async with notifier.record_and_notify(action=action) as recording:
        if body.is_completed:
            await goal.close_as_complete(recording.using_db)
        else:
            await goal.close(recording.using_db)
        await Visit.record(current_user.id, goal.workspace_id, recording.event.id, using_db=recording.using_db)
        await _close_subgoals(goal, current_user, using_db=recording.using_db)

    await goal.broadcast_update(additional_views=["active"])

    return await _fetch_goal_response(goal.id, expand)


@router.post("/goals/{goal_id}/reactivate", response_model=GoalResponse)
async def api_goals_reactivate(
    goal: Goal = Depends(get_goal_with_indexing),
    expand: frozenset[str] = Depends(parse_expand),
    current_user: User = Depends(get_current_user),
):
    notifier = Notifier(goal, current_user)
    async with notifier.record_and_notify(action=EventAction.GOAL_REACTIVATED) as recording:
        await goal.open(recording.using_db)
        await Visit.record(current_user.id, goal.workspace_id, recording.event.id, using_db=recording.using_db)

    await goal.broadcast_update(additional_views=["closed", "completed"])

    return await _fetch_goal_response(goal.id, expand)


@router.post("/goals/{goal_id}/activate", response_model=GoalResponse)
async def api_goals_activate(
    goal: Goal = Depends(get_goal_with_indexing),
    expand: frozenset[str] = Depends(parse_expand),
    current_user: User = Depends(get_current_user),
):
    notifier = Notifier(goal, current_user)
    async with notifier.record_and_notify(action=EventAction.GOAL_ACTIVATED) as recording:
        await goal.activate(using_db=recording.using_db)

    await goal.broadcast_update()

    return await _fetch_goal_response(goal.id, expand)


@router.delete("/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_goals_delete(
    goal: Goal = Depends(get_goal_with_indexing),
    current_user: User = Depends(get_current_user),
):
    notifier = Notifier(goal, current_user)
    async with notifier.record_and_notify(action=EventAction.GOAL_DELETED) as recording:
        await goal.soft_delete(recording.using_db)
        if goal.subgoals:
            for subgoal in goal.subgoals:
                await subgoal.soft_delete(recording.using_db)

    await goal.broadcast_update()


@router.post("/goals/sort", status_code=status.HTTP_204_NO_CONTENT)
async def api_goals_sort(
    body: SortGoalsRequest,
    current_user: User = Depends(get_current_user),
):
    scope = Goal.filter(Goal.filters.by_organization(current_user.organization_id) & Goal.filters.top_level)
    await Goal.reorder_by_ids(ids=body.ids, scope=scope)
    await Topic("goals_index", organization_id=current_user.organization_id, view=body.view).broadcast()


@router.post("/goals/{goal_id}/subgoals/sort", status_code=status.HTTP_204_NO_CONTENT)
async def api_subgoals_sort(
    body: SortSubgoalsRequest,
    goal: Goal = Depends(get_goal),
):
    await Goal.reorder_by_ids(ids=body.ids, scope=goal.subgoals.all())
    await goal.broadcast_update()


#
# Channels
#
#


@handle_stream("goals_index")
async def handle_goals_index_json_events(channel: Channel, **data):
    organization_id = UUID(str(channel.get_param("organization_id")))
    view = channel.get_param("view")

    # The goals_index channel broadcast mirrors the listing response with
    # subgoals expanded — every consumer of this channel renders the goal tree.
    channel_expand = frozenset({"subgoals"})
    filters = GoalFilterParams.from_view(view, organization_id, channel.current_user)
    filters.apply_base_filters()
    filters.queryset = _with_goal_expand(filters.queryset, channel_expand)

    pagination = await Pagination.create(Goal, queryset=filters.queryset)

    goals_data = [_goal_response(g, channel_expand).model_dump(mode="json") for g in pagination.results]

    await channel.send_event(
        ChannelEventResource.GOALS_INDEX,
        ChannelEventAction.UPDATED,
        goals=goals_data,
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@handle_stream("goals_presence")
async def handle_goals_presence_json_events(channel: Channel, **data):
    present_users = await get_present_users(channel, data)

    users_data = [
        UserResponse(id=str(u.id), display_name=u.display_name, picture=user_avatar_url(u)).model_dump(mode="json")
        for u in present_users
    ]

    await channel.send_event(
        ChannelEventResource.GOALS_PRESENCE,
        ChannelEventAction.UPDATED,
        users=users_data,
    )


@handle_stream("goal_timeline")
async def handle_goal_timeline_json_events(channel: Channel, **data):
    # goal_timeline now carries only content changes (comments/updates/status). View-state
    # (seen-by / last-seen) rides workspace_collaborators, so there is no visit-only broadcast
    # to skip here.
    goal_id = channel.get_param("goal_id")
    goal = await Goal.get(id=goal_id).prefetch_related("workspace")

    timeline = await fetch_timeline(goal)
    response = build_timeline_response(timeline)

    await channel.send_event(
        ChannelEventResource.GOAL_TIMELINE,
        ChannelEventAction.UPDATED,
        **response.model_dump(mode="json"),
    )
