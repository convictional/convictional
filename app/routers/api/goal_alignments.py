from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from typing import Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, model_validator
from tortoise.functions import Count

from app.models.accounts import User
from app.models.collaboration.content import Content, ContentLookup, ContentLookupQuery
from app.models.collaboration.workspace import Event
from app.models.workspaces.goals import Goal, GoalAlignment, GoalUpdate
from app.routers.api.schemas import ContentResponse, PaginatedResponse, UserResponse
from app.routers.api.serializers import content_response, user_response
from app.routers.dependencies import get_current_user, get_goal
from config.enums import ContentType, EventAction, SignalStrength
from infra.db import allow_soft_deleted

router = APIRouter(tags=["goal alignments"])


#
# Response models
#


class GoalAlignmentSummary(BaseModel):
    id: str
    name: str
    description: str | None
    activity: int
    status: str
    group_id: str | None
    group_name: str | None
    url: str
    signal_counts: dict[str, int]


class GoalAlignmentGroup(BaseModel):
    id: str
    name: str
    goals: list[GoalAlignmentSummary]


# Bounded aggregate (all active top-level goals for the org), not a paginable list:
# a single next_cursor/has_more across two disjoint collections would be ambiguous, so
# this doesn't inherit PaginatedResponse.
class GoalAlignmentOverviewResponse(BaseModel):
    groups: list[GoalAlignmentGroup]
    ungrouped_goals: list[GoalAlignmentSummary]


class GoalAlignmentResponse(BaseModel):
    id: str
    content: ContentResponse
    signal: str
    alignment_score: float
    score: float
    pinned: bool
    description: str
    content_indexed_at: datetime
    created_by: UserResponse | None
    created_at: datetime


class WeeklyActivityBucket(BaseModel):
    week: str
    count: int


class TimelineProgressEvent(BaseModel):
    week_index: int
    progress: float


class TimelineStatusChange(BaseModel):
    week_index: int
    status: str


class AlignmentTimelineData(BaseModel):
    weekly_activity: list[WeeklyActivityBucket]
    progress_events: list[TimelineProgressEvent]
    status_changes: list[TimelineStatusChange]
    current_progress: float
    current_status: str
    total_weeks: int
    today_week_index: int
    start_date: str
    end_date: str


# Not a paginable list (and not PaginatedResponse): the timeline buckets every alignment,
# so a paginated first page would produce a wrong chart, and a single cursor across the
# alignments list plus the timeline aggregate would be ambiguous. If pagination is ever
# needed, the timeline moves to its own endpoint.
class GoalAlignmentListResponse(BaseModel):
    alignments: list[GoalAlignmentResponse]
    timeline: AlignmentTimelineData


# Search results are Content rows hydrated from the content_lookup table, which carries
# only the synced columns (no category/preview_content), so they use a slimmer model than
# the full ContentResponse used for an alignment's already-aligned content.
class AlignableContentResponse(BaseModel):
    id: str
    title: str
    author: str | None
    content_type: str
    source_url: str


class AlignableContentListResponse(PaginatedResponse):
    results: list[AlignableContentResponse]


#
# Request models
#


class AlignmentCreateRequest(BaseModel):
    content_id: UUID
    description: str


class AlignmentPatchRequest(BaseModel):
    pinned: bool | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.pinned is None:
            raise ValueError("must set pinned")
        return self


#
# Dependencies & serializers
#


async def get_goal_alignment(alignment_id: UUID, goal: Goal = Depends(get_goal)) -> GoalAlignment:
    alignment = await GoalAlignment.get_or_none(
        id=alignment_id, goal_id=goal.id, organization_id=goal.organization_id
    ).select_related("content", "created_by")
    if not alignment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    return alignment


def _alignment_response(alignment: GoalAlignment, creator: User | None) -> GoalAlignmentResponse:
    return GoalAlignmentResponse(
        id=str(alignment.id),
        content=content_response(alignment.content),
        signal=alignment.signal.value,
        alignment_score=alignment.alignment_score,
        score=alignment.score,
        pinned=alignment.pinned_by_id is not None,
        description=alignment.description,
        content_indexed_at=alignment.content_indexed_at,
        created_by=user_response(creator),
        created_at=alignment.created_at,
    )


def _summary(request: Request, goal: Goal, signal_counts: dict[UUID, dict[str, int]]) -> GoalAlignmentSummary:
    counts = signal_counts.get(goal.id, {})
    return GoalAlignmentSummary(
        id=str(goal.id),
        name=goal.title,
        description=goal.description,
        activity=sum(counts.values()),
        status=goal.status.value,
        group_id=str(goal.group_id) if goal.group_id else None,
        group_name=goal.group.name if goal.group_id and goal.group else None,
        url=str(request.url_for("goal_alignments_show", goal_id=goal.id)),
        signal_counts=dict(counts),
    )


def _overview_response(
    request: Request, goals: list[Goal], signal_counts: dict[UUID, dict[str, int]]
) -> GoalAlignmentOverviewResponse:
    groups_by_id: dict[UUID, GoalAlignmentGroup] = {}
    ungrouped_goals: list[GoalAlignmentSummary] = []

    for goal in goals:
        summary = _summary(request, goal, signal_counts)
        if not goal.group_id:
            ungrouped_goals.append(summary)
            continue
        group = groups_by_id.get(goal.group_id)
        if group is None:
            group = GoalAlignmentGroup(
                id=str(goal.group_id),
                name=goal.group.name if goal.group else "Unknown",
                goals=[],
            )
            groups_by_id[goal.group_id] = group
        group.goals.append(summary)

    return GoalAlignmentOverviewResponse(groups=list(groups_by_id.values()), ungrouped_goals=ungrouped_goals)


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _timeline_data(
    goal: Goal,
    alignments: list[GoalAlignment],
    goal_updates: list[GoalUpdate],
    status_events: Sequence[Event] | None = None,
) -> AlignmentTimelineData:
    today = date.today()
    start = _week_start(goal.activated_at.date()) if goal.activated_at else _week_start(today - timedelta(weeks=12))
    end = goal.target_date if goal.target_date else today + timedelta(weeks=4)

    weeks: list[str] = []
    current = start
    while current <= end:
        weeks.append(current.isoformat())
        current += timedelta(weeks=1)
    if not weeks:
        weeks.append(start.isoformat())

    week_set = set(weeks)
    counts_by_week: dict[str, int] = defaultdict(int)
    for alignment in alignments:
        week = _week_start(alignment.content_indexed_at.date()).isoformat()
        if week in week_set:
            counts_by_week[week] += 1

    weekly_activity = [WeeklyActivityBucket(week=w, count=counts_by_week.get(w, 0)) for w in weeks]

    today_week = _week_start(today).isoformat()
    today_week_index = next((i for i, w in enumerate(weeks) if w == today_week), len(weeks) - 1)

    sorted_updates = sorted(
        (u for u in goal_updates if u.completed_at),
        key=lambda u: u.completed_at or datetime.min,
    )
    progress_events: list[TimelineProgressEvent] = []
    for update in sorted_updates:
        assert update.completed_at is not None
        week = _week_start(update.completed_at.date()).isoformat()
        week_index = next((i for i, w in enumerate(weeks) if w == week), None)
        if week_index is not None:
            progress_events.append(
                TimelineProgressEvent(
                    week_index=week_index,
                    progress=update.progress if update.progress is not None else (goal.progress or 0.0),
                )
            )

    status_changes: list[TimelineStatusChange] = []
    for event in status_events or []:
        status_pair = event.details.get("status")
        if not status_pair or len(status_pair) < 2:
            continue
        week = _week_start(event.created_at.date()).isoformat()
        week_index = next((i for i, w in enumerate(weeks) if w == week), None)
        if week_index is not None:
            status_changes.append(TimelineStatusChange(week_index=week_index, status=status_pair[1]))

    return AlignmentTimelineData(
        weekly_activity=weekly_activity,
        progress_events=progress_events,
        status_changes=status_changes,
        current_progress=goal.progress or 0.0,
        current_status=goal.status.value,
        total_weeks=len(weeks),
        today_week_index=today_week_index,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
    )


#
# Data access & business logic
#


# These are raised by create_manual_alignment so the endpoint can translate them into the
# right status codes (404 for missing content, 409 for an existing alignment).
class AlignmentContentNotFoundError(Exception):
    """The content to align does not exist in the org."""


class AlignmentAlreadyExistsError(Exception):
    """A live (non-deleted) alignment for this content+goal already exists."""


async def fetch_overview_goals(current_user: User) -> tuple[list[Goal], dict[UUID, dict[str, int]]]:
    """Active top-level goals plus their per-signal alignment counts, keyed by goal id."""
    goals = await (
        Goal.filter(Goal.filters.by_active_open_top_level(current_user.organization_id))
        .prefetch_related("group")
        .order_by("title")
    )

    rows = await (
        GoalAlignment.filter(GoalAlignment.filters.by_organization(current_user.organization_id))
        .annotate(count=Count("id"))
        .group_by("goal_id", "signal")
        .values("goal_id", "signal", "count")
    )

    signal_counts_by_goal: dict[UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        signal_counts_by_goal[row["goal_id"]][row["signal"]] = row["count"]

    return goals, signal_counts_by_goal


def dedupe_alignments_by_content(alignments: list[GoalAlignment]) -> list[GoalAlignment]:
    """Dedupe alignments by content_id (keeping the first). A single content can have multiple
    alignment rows across index runs because unique_together is (content_id, goal_id,
    content_indexed_at); without deduping the card list would show the same content twice."""
    seen_content_ids: set[UUID] = set()
    deduped: list[GoalAlignment] = []
    for alignment in alignments:
        if alignment.content_id not in seen_content_ids:
            deduped.append(alignment)
            seen_content_ids.add(alignment.content_id)
    return deduped


async def fetch_timeline_events(goal: Goal) -> tuple[list[GoalUpdate], list[Event]]:
    """Completed goal updates and status-change events feeding the timeline chart."""
    goal_updates = await GoalUpdate.filter(GoalUpdate.filters.completed_for_goal(goal.id)).order_by("completed_at")

    status_events = await Event.filter(
        Event.filters.by_workspace(goal.workspace_id)
        & Event.filters.by_actions([EventAction.GOAL_UPDATED, EventAction.GOAL_UPDATE_POSTED])
    )
    status_events = [e for e in status_events if "status" in e.details]
    return goal_updates, status_events


async def search_alignable_content(query: str, current_user: User) -> list[ContentLookup]:
    """Search content the user can manually align to a goal.

    The most recent job-created alignment (created_by_id IS NULL) proxies for the last scoring
    run; content created after it is excluded so the form can't surface content the weekly
    scorer hasn't seen yet. NOTE: a manually-created alignment whose creator was later deleted
    (SET_NULL) also matches created_by_id IS NULL — a pre-existing imprecision documented, not
    fixed, here. When no job has run, scored_before is None and the cutoff is bypassed.
    """
    organization = await current_user.organization

    last_alignment = (
        await GoalAlignment.filter(
            organization_id=current_user.organization_id,
            created_by_id__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )
    scored_before = last_alignment.created_at if last_alignment else None

    lookup = ContentLookupQuery(
        organization=organization,
        query=query,
        current_user=current_user,
        limit=5,
        content_types=[ContentType.POST, ContentType.MEETING],
        created_before=scored_before,
    )
    return await lookup.execute()


async def create_manual_alignment(
    goal: Goal, content_id: UUID, description: str, user: User
) -> tuple[GoalAlignment, bool]:
    """Create — or restore a soft-deleted — manual alignment. Returns (alignment, created).

    Manual alignments are pinned by default and score 1.0. Raises AlignmentContentNotFoundError if
    the content is missing and AlignmentAlreadyExistsError if a live alignment already exists.
    """
    content = await Content.get_or_none(id=content_id, organization_id=user.organization_id)
    if not content:
        raise AlignmentContentNotFoundError

    async with allow_soft_deleted():
        existing = await GoalAlignment.filter(
            goal_id=goal.id, content_id=content.id, organization_id=user.organization_id
        ).first()

    if existing and not existing.deleted_at:
        raise AlignmentAlreadyExistsError

    if existing:
        existing.deleted_at = None
        existing.description = description
        existing.signal = SignalStrength.STRONG
        existing.alignment_score = 1.0
        existing.created_by_id = user.id
        existing.pinned_by_id = user.id
        # A bare save() lets the set_timestamps pre_save signal bump updated_at; listing
        # "updated_at" in update_fields here would instead suppress the bump.
        await existing.save()
        return existing, False

    alignment = await GoalAlignment.create(
        goal_id=goal.id,
        content_id=content.id,
        content_indexed_at=content.last_indexed_at,
        signal=SignalStrength.STRONG,
        alignment_score=1.0,
        description=description,
        organization_id=user.organization_id,
        created_by_id=user.id,
        pinned_by_id=user.id,
    )
    return alignment, True


#
# Endpoints
#


@router.get("/goal_alignments", response_model=GoalAlignmentOverviewResponse)
async def api_goal_alignments_index(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    goals, signal_counts = await fetch_overview_goals(current_user)
    return _overview_response(request, goals, signal_counts)


@router.get("/goals/{goal_id}/alignments", response_model=GoalAlignmentListResponse)
async def api_goal_alignments_show(
    goal: Goal = Depends(get_goal),
    current_user: User = Depends(get_current_user),
):
    all_alignments = await GoalAlignment.filter(
        GoalAlignment.filters.by_goal(goal.id) & GoalAlignment.filters.by_organization(current_user.organization_id)
    ).select_related("content", "created_by")

    goal_updates, status_events = await fetch_timeline_events(goal)

    return GoalAlignmentListResponse(
        alignments=[
            _alignment_response(alignment, alignment.created_by)
            for alignment in dedupe_alignments_by_content(all_alignments)
        ],
        timeline=_timeline_data(goal, all_alignments, goal_updates, status_events),
    )


# Not nested under a goal: the candidate set is org-wide (the scored_before cutoff is
# org-level), so the goal never filtered results. Co-located with the alignment routes
# rather than promoted to a general /search/lookup because it's a dogfood utility with an
# uncertain future. Returns content candidates, not alignments.
@router.get("/goal_alignments/lookup", response_model=AlignableContentListResponse)
async def api_goal_alignments_lookup(
    q: str = Query(min_length=2),
    current_user: User = Depends(get_current_user),
):
    results = await search_alignable_content(q, current_user)
    return AlignableContentListResponse(
        results=[
            AlignableContentResponse(
                id=str(content.id),
                title=content.title,
                author=content.author,
                content_type=content.content_type.value,
                source_url=content.source_url,
            )
            for content in results
        ]
    )


@router.post(
    "/goals/{goal_id}/alignments",
    response_model=GoalAlignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_goal_alignments_create(
    body: AlignmentCreateRequest,
    response: Response,
    goal: Goal = Depends(get_goal),
    current_user: User = Depends(get_current_user),
):
    try:
        alignment, created = await create_manual_alignment(goal, body.content_id, body.description, current_user)
    except AlignmentContentNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    except AlignmentAlreadyExistsError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Content is already aligned with this goal")

    if not created:
        response.status_code = status.HTTP_200_OK

    await alignment.fetch_related("content")
    return _alignment_response(alignment, current_user)


@router.delete("/goals/{goal_id}/alignments/{alignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_goal_alignments_delete(
    alignment_id: UUID,
    goal: Goal = Depends(get_goal),
    current_user: User = Depends(get_current_user),
):
    # Idempotent: an already-deleted alignment is filtered out by the default manager, so a
    # repeat DELETE finds nothing and still returns 204.
    alignment = await GoalAlignment.get_or_none(
        id=alignment_id, goal_id=goal.id, organization_id=current_user.organization_id
    )
    if alignment:
        await alignment.soft_delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/goals/{goal_id}/alignments/{alignment_id}", response_model=GoalAlignmentResponse)
async def api_goal_alignments_patch(
    body: AlignmentPatchRequest,
    alignment: GoalAlignment = Depends(get_goal_alignment),
    current_user: User = Depends(get_current_user),
):
    alignment.pinned_by_id = current_user.id if body.pinned else None
    await alignment.save(update_fields=["pinned_by_id"])
    return _alignment_response(alignment, alignment.created_by)
