import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, Literal, Protocol, Self
from uuid import UUID

from anthropic import BadRequestError
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, model_validator
from tortoise.queryset import QuerySet

from app.models.accounts import User
from app.models.collaboration.mailbox import (
    Mailbox,
    MailboxEntry,
    MailboxEntryFilters,
    MailboxView,
    MailboxViewCache,
    MailboxViewIdentifier,
    MailboxViewSource,
)
from app.models.workspaces.goals import Goal
from app.presenters.mailbox_entries import MailboxEntryPresenter
from app.presenters.mailbox_view import (
    LLMMailboxRankResponse,
    LLMMailboxViewResponse,
    LLMRankedEntry,
    LLMViewSection,
    MailboxViewPresenter,
    ViewSection,
    ViewSectionPresenter,
)
from app.prompts import build_prompt
from app.routers.api.goals import GoalSummary, comment_prefetch, goal_summary
from app.routers.dependencies import Channel, get_current_user, handle_stream
from config import logger
from config.enums import ChannelEventAction, ChannelEventResource, MailboxViewLayout
from config.logging import LoggingContext
from infra.messaging import Topic
from lib.uuid import parse_uuid

router = APIRouter(tags=["mailbox views"])

TITLE_MODEL = "claude-haiku-4-5"
# Most-recent-first slice of the inbox handed to the structure pass. The per-entry
# prompt payload is small enough that 250 entries stay well inside the model's context while
# covering far more of a busy inbox. Inboxes larger than this are truncated by recency, and the
# index endpoint surfaces "considered N of M" so the truncation is explicit rather than silent.
MAILBOX_VIEW_MAX_ENTRIES = 250
MAILBOX_VIEW_MIN_ENTRIES = 5

# Ranked generation writes a partial ordering to the shared cache every this many newly-scored
# entries (plus a final write at completion). Keeps a refresh mid-sort from blanking while bounding
# cache churn over the course of generation.
RANKED_PARTIAL_WRITE_INTERVAL = 10


# `generating=True` marks a partial mid-stream write; partials carry a stable `cached_at` so the
# new-messages baseline doesn't drift across them.
class CacheWriter(Protocol):
    async def __call__(
        self, sections: list[dict], *, generating: bool = False, cached_at: datetime | None = None
    ) -> object: ...


# Maximum length for an LLM-generated mailbox view title before persistence.
# Defense-in-depth: even with a bounded view_request, the model can return arbitrarily long output.
MAX_TITLE_LENGTH = 120


def _ai_inbox_queryset(user: User) -> QuerySet[MailboxEntry]:
    """Inbox entries eligible for view generation. Shared by the candidate query and the coverage
    count so the "considered N of M" notice can never diverge from what generation actually sees.
    """
    return Mailbox(user=user).filters.inbox.filter(MailboxEntryFilters.ai_included())


class MailboxViewSummary(BaseModel):
    id: str
    title: str
    view_request: str
    # "grouped" (custom view) or "ranked" (custom sort). Clients split the list by this field.
    layout: MailboxViewLayout
    created_at: datetime


class ViewSectionResponse(BaseModel):
    title: str
    description: str
    mailbox_entry_ids: list[str]
    goal: GoalSummary | None = None


class ActiveMailboxView(BaseModel):
    kind: Literal["template", "view"]
    # `id` and `channel_id` carry the same opaque identifier — `to_channel_id()` for views,
    # which is `template:<name>` for templates and the bare UUID string for saved views.
    # Symmetry lets React clients use either field interchangeably regardless of `kind`.
    id: str
    title: str | None
    view_request: str | None
    channel_id: str
    requires_goals: bool
    # "grouped" renders LLM sections; "ranked" renders one flat score-ordered list.
    layout: MailboxViewLayout


class MailboxViewIndexResponse(BaseModel):
    all_views: list[MailboxViewSummary]
    active: ActiveMailboxView | None
    cached_sections: list[ViewSectionResponse] | None
    cached_entry_ids: list[str]
    # True when `cached_sections` is a partial ordering still being generated (a refresh landed
    # mid-sort). The client renders it but keeps the spinner and channel subscription, then
    # reconciles to the authoritative order on the `complete` event.
    generating: bool = False
    has_goals_for_view: bool
    # In-band rather than a 404 by design: when a view is deleted in another tab, the React
    # island still needs the rest of the response (all_views, etc.) to render the sidebar.
    is_not_found: bool
    # Coverage transparency: generation organizes at most `considered_entry_count` of
    # `eligible_entry_count` inbox items, most recent first. When considered < eligible the UI
    # tells the user older items aren't included. Both null when no view is active.
    eligible_entry_count: int | None = None
    considered_entry_count: int | None = None


class CreateMailboxViewRequest(BaseModel):
    title: str | None = None
    view_request: str
    layout: MailboxViewLayout = MailboxViewLayout.GROUPED


class UpdateMailboxViewRequest(BaseModel):
    title: str | None = None
    view_request: str | None = None
    layout: MailboxViewLayout | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.title is None and self.view_request is None and self.layout is None:
            raise ValueError("must set title, view_request, and/or layout")
        return self


class MailboxViewMutationResponse(BaseModel):
    view: MailboxViewSummary
    redirect_to: str


def _summary(view: MailboxView) -> MailboxViewSummary:
    return MailboxViewSummary(
        id=str(view.id),
        title=view.title,
        view_request=view.view_request,
        layout=view.layout,
        created_at=view.created_at,
    )


def _section_response(section_presenter: ViewSectionPresenter) -> ViewSectionResponse:
    section = section_presenter.section
    return ViewSectionResponse(
        title=section.title,
        description=section.description,
        mailbox_entry_ids=section.mailbox_entry_ids,
        goal=goal_summary(section_presenter.goal) if section_presenter.goal else None,
    )


def _active_from_presenter(presenter: MailboxViewPresenter) -> ActiveMailboxView | None:
    if presenter.active_template:
        identifier = presenter.active_template
        channel_id = identifier.to_channel_id()
        return ActiveMailboxView(
            kind="template",
            id=channel_id,
            title=identifier.title,
            view_request=identifier.view_request,
            channel_id=channel_id,
            requires_goals=identifier.requires_goals,
            layout=identifier.layout,
        )
    if presenter.active:
        view = presenter.active
        channel_id = str(view.id)
        return ActiveMailboxView(
            kind="view",
            id=channel_id,
            title=view.title,
            view_request=view.view_request,
            channel_id=channel_id,
            requires_goals=False,
            layout=view.layout,
        )
    return None


async def _resolve_cached_sections(presenter: MailboxViewPresenter, user: User) -> list[ViewSectionResponse] | None:
    """Resolve cached section dicts (with mailbox_entry_ids only) into JSON sections with goal data.

    The cached payload references entries and goals by id; we hydrate just enough goal data here so
    the React badge can render without a follow-up fetch. Mailbox entries are listed via the
    /api/mailbox_entries endpoint, so we only return the ids in this response.
    """
    if presenter.cached_sections is None:
        return None

    sections = [ViewSection(**section) for section in presenter.cached_sections]
    # Skip any goal_id that isn't a valid UUID. New caches are sanitized at write time, but caches
    # written before that fix can still hold a mangled id (e.g. a truncated UUID); passing one to
    # Goal.filter(id__in=...) raises a bind error that 500s the whole view until the cache expires.
    goal_ids = [s.goal_id for s in sections if s.goal_id and parse_uuid(s.goal_id)]

    goals_by_id: dict[str, Goal] = {}
    if goal_ids:
        # Defense-in-depth org scope: cached goal ids originate from LLM output and could
        # theoretically reference foreign UUIDs via cache tampering or prompt injection.
        goals = (
            await Goal.filter(id__in=goal_ids, organization_id=user.organization_id)
            .select_related("owner__avatar_file", "group", "workspace")
            .prefetch_related(comment_prefetch())
        )
        goals_by_id = {str(g.id): g for g in goals}

    presenters = [
        ViewSectionPresenter.create(section, entries_by_id={}, goals_by_id=goals_by_id) for section in sections
    ]
    return [_section_response(p) for p in presenters]


ByGoalRejection = Literal["missing_id", "not_found", "closed"]


async def _resolve_by_goal(
    goal_id: UUID | None, user: User, *, with_relations: bool = False
) -> tuple[Goal | None, ByGoalRejection | None]:
    """Resolve the goal a "by_goal" ranked sort targets, org-scoped. Returns (goal, rejection).

    Shared by the HTTP index (maps the rejection to 404/422) and the channel generator (maps it to
    a broadcast) so the org-scope check and the closed/missing distinction can't drift between the
    two entry points. `with_relations` eager-loads owner/group for the ranked prompt.
    """
    if goal_id is None:
        return None, "missing_id"
    query = Goal.get_or_none(id=goal_id, organization_id=user.organization_id)
    if with_relations:
        # Load the exact relation set the prompt templates read (owner/group/subgoals) via the shared
        # constant, so this loader can't drift from Goal.for_user. A missing relation raises
        # NoValuesFetched deep inside the Jinja render and silently kills generation.
        query = query.prefetch_related(*Goal.PROMPT_CONTEXT_RELATIONS)
    goal = await query
    if goal is None:
        return None, "not_found"
    if goal.is_closed:
        return goal, "closed"
    return goal, None


async def _validate_by_goal(goal_id: UUID | None, current_user: User) -> Goal:
    """Validate the goal targeted by a "by_goal" ranked sort and return it.

    404 for a missing/foreign goal (org-scoped, mirrors the get_goal dependency to avoid leaking
    existence); 422 for a goal that is owned but closed or a missing goal_id. Never 403. The
    returned goal lets the caller label the active view with the goal's title.
    """
    goal, rejection = await _resolve_by_goal(goal_id, current_user)
    if rejection == "missing_id":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="goal_id is required for the by_goal sort"
        )
    if rejection == "not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if rejection == "closed":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Goal is closed")
    if goal is None:
        # Unreachable: a None rejection means _resolve_by_goal returned a goal. Raise rather than
        # assert so it survives `python -O` and narrows the return type for mypy.
        raise RuntimeError("_resolve_by_goal returned no goal without a rejection")
    return goal


async def get_api_mailbox_view(view_id: UUID, current_user: User = Depends(get_current_user)) -> MailboxView:
    view = await MailboxView.get_or_none(
        id=view_id, user_id=current_user.id, organization_id=current_user.organization_id
    )
    if not view:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return view


@router.get("/mailbox_views", response_model=MailboxViewIndexResponse)
async def api_mailbox_views_index(
    current_user: User = Depends(get_current_user),
    view_id: UUID | None = Query(None),
    template: str | None = Query(None),
    goal_id: UUID | None = Query(None),
):
    template_identifier = MailboxViewIdentifier.for_template(template) if template else None
    by_goal_target: Goal | None = None
    if template_identifier and template_identifier.targets_single_goal:
        by_goal_target = await _validate_by_goal(goal_id, current_user)

    presenter = await MailboxViewPresenter.create(
        current_user, mailbox_view_id=view_id, mailbox_view_template=template, goal_id=goal_id
    )
    active = _active_from_presenter(presenter)
    # Surface which goal a "by_goal" sort targets so the header reflects it on load, before the
    # client lazy-loads the goals list. The template's own title is the generic "By goal".
    if active is not None and by_goal_target is not None:
        active = active.model_copy(update={"title": by_goal_target.title})
    cached_sections = await _resolve_cached_sections(presenter, current_user)

    eligible_entry_count: int | None = None
    considered_entry_count: int | None = None
    if active is not None:
        eligible_entry_count = await _ai_inbox_queryset(current_user).count()
        considered_entry_count = min(eligible_entry_count, MAILBOX_VIEW_MAX_ENTRIES)

    return MailboxViewIndexResponse(
        all_views=[_summary(v) for v in presenter.all_views],
        active=active,
        cached_sections=cached_sections,
        cached_entry_ids=presenter.cached_entry_ids,
        generating=presenter.generating,
        has_goals_for_view=presenter.has_goals_for_view,
        is_not_found=presenter.is_not_found,
        eligible_entry_count=eligible_entry_count,
        considered_entry_count=considered_entry_count,
    )


@router.post("/mailbox_views", response_model=MailboxViewMutationResponse, status_code=status.HTTP_201_CREATED)
async def api_mailbox_views_create(
    body: CreateMailboxViewRequest,
    current_user: User = Depends(get_current_user),
):
    if not body.view_request.strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="view_request is required")

    title = body.title
    if not title:
        title_prompt = build_prompt(
            "mailbox_views/generate_title.md.jinja",
            view_request=body.view_request,
            current_user=current_user,
            organization=current_user.organization,
        )
        try:
            generated_title = await current_user.organization.llm.string_completion(
                system_prompt=title_prompt,
                user_prompt="Generate a title for this mailbox view.",
                model=TITLE_MODEL,
                temperature=0.0,
            )
            title = generated_title.strip().strip('"').strip("'")
        except Exception:
            # Title generation is cosmetic — don't block view creation on provider failures.
            logger.exception("Failed to generate mailbox view title")
            title = body.view_request[:80].strip() or "Untitled view"
        # Cap LLM-generated output only; explicit user-supplied titles pass through unchanged
        # to match the HTML route.
        title = title[:MAX_TITLE_LENGTH]

    view = await MailboxView.create(
        user_id=current_user.id,
        organization_id=current_user.organization_id,
        title=title,
        view_request=body.view_request,
        layout=body.layout,
    )
    return MailboxViewMutationResponse(view=_summary(view), redirect_to=f"/?mailbox_view_id={view.id}")


@router.patch("/mailbox_views/{view_id}", response_model=MailboxViewMutationResponse)
async def api_mailbox_views_update(
    body: UpdateMailboxViewRequest,
    view: MailboxView = Depends(get_api_mailbox_view),
    current_user: User = Depends(get_current_user),
):
    if body.title:
        view.title = body.title
    if body.view_request is not None and body.view_request != view.view_request:
        view.view_request = body.view_request
        # Cache reflects the prior view_request — invalidate so the next load regenerates.
        await MailboxViewCache(view).delete()
    if body.layout is not None and body.layout != view.layout:
        view.layout = body.layout
        # A layout flip (grouped<->ranked) changes the cached shape entirely. Invalidate with its
        # own delete — the view_request branch above may not fire on a layout-only PATCH.
        await MailboxViewCache(view).delete()
    await view.save()
    return MailboxViewMutationResponse(view=_summary(view), redirect_to=f"/?mailbox_view_id={view.id}")


@router.post("/mailbox_views/{identifier}/refresh", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_views_refresh(
    identifier: str,
    current_user: User = Depends(get_current_user),
):
    # `identifier` is the opaque active-view id: a bare UUID for a saved view or `template:<name>`
    # (optionally `:<goal_id>`) for a built-in sort. Both must be refreshable — built-in sorts show
    # the same "new conversations not included" banner but have no MailboxView row to key on.
    parsed = MailboxViewIdentifier.from_string(identifier)
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if parsed.is_template():
        # Cache is per-user and keyed by template + goal_id, so a delete only ever clears the
        # caller's own entry; no goal-ownership check is needed for a refresh.
        await parsed.delete_cache(current_user.id)
    elif parsed.view_id is not None:
        view = await get_api_mailbox_view(parsed.view_id, current_user)
        await MailboxViewCache(view).delete()
    else:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    logger.info("mailbox_view refreshed identifier=%s user_id=%s", identifier, current_user.id)


@router.delete("/mailbox_views/{view_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_mailbox_views_delete(
    view: MailboxView = Depends(get_api_mailbox_view),
    current_user: User = Depends(get_current_user),
):
    view_id = view.id
    await view.delete()
    logger.info("mailbox_view deleted view_id=%s user_id=%s", view_id, current_user.id)


#
# Channels (JSON-mode broadcast handlers)
#


class SectionBroadcast(BaseModel):
    kind: Literal["section"] = "section"
    section: ViewSection
    section_index: int = 0


class CompleteBroadcast(BaseModel):
    kind: Literal["complete"] = "complete"


class ErrorBroadcast(BaseModel):
    kind: Literal["error"] = "error"
    error: str = "An error occurred"


class CacheExpiredBroadcast(BaseModel):
    kind: Literal["cache_expired"] = "cache_expired"


class NewMessagesBroadcast(BaseModel):
    kind: Literal["new_messages"] = "new_messages"
    new_messages_count: int
    view_id: str | None = None


class RegeneratingBroadcast(BaseModel):
    kind: Literal["regenerating"] = "regenerating"
    attempt: int


# Ranked sorts stream one of these per candidate rather than re-broadcasting the whole section: the
# client maintains a locally-sorted list and inserts each entry by score (tiebreak recency/id). This
# is the same per-entry delta protocol the custom-views refactor uses for live updates, so the client
# handler is built once.
class EntryScoredBroadcast(BaseModel):
    kind: Literal["entry_scored"] = "entry_scored"
    entry_id: str
    score: float
    # Recency ordinal (index in the candidate list) the client tie-breaks equal scores on, mirroring
    # order_candidates so the live order matches the cached order without reshuffling on hydration.
    rank: int


# A single frame assigning one shared score to many entries. Used for the sentinel tail-flush so the
# candidates the LLM never scored ship in one broadcast rather than one Postgres NOTIFY each (up to
# ~250 back-to-back). The client applies `score` to every id, same as a run of `entry_scored`.
class EntriesScoredBroadcast(BaseModel):
    kind: Literal["entries_scored"] = "entries_scored"
    entry_ids: list[str]
    # Recency ordinals aligned to entry_ids, so the sentinel tail tie-breaks identically to the
    # per-entry deltas (and to order_candidates).
    ranks: list[int]
    score: float

    @model_validator(mode="after")
    def ranks_aligned(self) -> Self:
        if len(self.ranks) != len(self.entry_ids):
            raise ValueError(f"ranks length {len(self.ranks)} != entry_ids length {len(self.entry_ids)}")
        return self


MailboxViewBroadcast = Annotated[
    SectionBroadcast
    | CompleteBroadcast
    | ErrorBroadcast
    | CacheExpiredBroadcast
    | NewMessagesBroadcast
    | RegeneratingBroadcast
    | EntryScoredBroadcast
    | EntriesScoredBroadcast,
    Field(discriminator="kind"),
]

_broadcast_adapter: TypeAdapter[MailboxViewBroadcast] = TypeAdapter(MailboxViewBroadcast)


def _classify_broadcast(data: dict) -> MailboxViewBroadcast | None:
    """Map a broadcast payload onto a typed variant.

    Producers tagged with `kind` are dispatched via the discriminated union. Untagged
    producers (section/complete/error) are matched by key presence as a fallback.
    """
    if "kind" in data:
        try:
            return _broadcast_adapter.validate_python(data)
        except ValidationError:
            return None
    if "section" in data:
        return SectionBroadcast.model_validate(data)
    if "complete" in data:
        return CompleteBroadcast.model_validate(data)
    if "error" in data:
        return ErrorBroadcast.model_validate(data)
    if data.get("cache_expired"):
        return CacheExpiredBroadcast()
    if "new_messages_count" in data:
        return NewMessagesBroadcast.model_validate(data)
    return None


@handle_stream("mailbox_view")
async def mailbox_view_json_broadcast(channel: Channel, **data) -> None:
    if data.get("action") == "start_generation":
        view_id = channel.get_param("view_id")
        if view_id:
            # Replay before kicking off generation: a late subscriber (mid-stream refresh,
            # second tab) broadcasts its own start_generation from on_subscribe; if a session
            # is already in flight we push its collected sections so the new subscriber's UI
            # catches up. Duplicate emits to clients that already have these sections are
            # idempotent on the React side.
            await _replay_session_sections(channel, view_id)
            await _handle_start_generation(channel, view_id)
        return
    event = _classify_broadcast(data)
    match event:
        case SectionBroadcast():
            await _emit_section(channel, event)
        case CompleteBroadcast():
            await _emit(channel, type="complete")
        case ErrorBroadcast():
            await _emit(channel, type="error", message=event.error)
        case CacheExpiredBroadcast():
            await _emit(channel, type="cache_expired")
        case NewMessagesBroadcast():
            await _emit(
                channel,
                type="new_messages",
                count=event.new_messages_count,
                view_id=event.view_id or channel.get_param("view_id"),
            )
        case RegeneratingBroadcast():
            await _emit(channel, type="regenerating", attempt=event.attempt)
        case EntryScoredBroadcast():
            await _emit(channel, type="entry_scored", entry_id=event.entry_id, score=event.score, rank=event.rank)
        case EntriesScoredBroadcast():
            await _emit(
                channel, type="entries_scored", entry_ids=event.entry_ids, ranks=event.ranks, score=event.score
            )
        case None:
            return


async def _emit_section(channel: Channel, event: SectionBroadcast) -> None:
    section = event.section
    user = channel.current_user
    goals_by_id: dict[str, Goal] = {}
    if section.goal_id:
        # Defense-in-depth org scope: section.goal_id originates from LLM output.
        goal = (
            await Goal.get_or_none(id=section.goal_id, organization_id=user.organization_id)
            .select_related("owner__avatar_file", "group", "workspace")
            .prefetch_related(comment_prefetch())
        )
        if goal:
            goals_by_id[str(goal.id)] = goal

    presenter = ViewSectionPresenter.create(section, entries_by_id={}, goals_by_id=goals_by_id)
    await _emit(
        channel,
        type="section",
        section_index=event.section_index,
        section=_section_payload(presenter),
    )


async def _emit(channel: Channel, **payload) -> None:
    """Send a MAILBOX_VIEW event with `type` as the broadcast-level discriminator."""
    await channel.send_event(ChannelEventResource.MAILBOX_VIEW, ChannelEventAction.UPDATED, **payload)


def _section_payload(presenter: ViewSectionPresenter) -> dict:
    section = presenter.section
    goal = goal_summary(presenter.goal) if presenter.goal else None
    return {
        "title": section.title,
        "description": section.description,
        "mailbox_entry_ids": section.mailbox_entry_ids,
        "goal": goal.model_dump(mode="json") if goal else None,
    }


#
# LLM generation
#


GENERIC_GENERATION_ERROR = "Something went wrong. Please try again."
CONTEXT_OVERFLOW_ERROR = "Your inbox is too large to organize right now. Archive some conversations and try again."
# Shown when a non-trivial inbox produces zero usable sections — surfaced explicitly instead of
# silently completing with blank "Nothing in this category" sections.
EMPTY_GENERATION_ERROR = "We couldn't organize your inbox right now. Please refresh to try again."

# Candidates the LLM never scored sort below every scored item (in recency order) so a ranked sort
# stays a complete set of the <=250 candidates rather than silently dropping the unscored ones.
SENTINEL_RANK_SCORE = -1.0

# A ranked sort emits one {entry_number, score} object PER candidate, so the output budget scales
# with the inbox. The flat 4096-token default truncates large inboxes — the unscored tail then
# silently falls to SENTINEL_RANK_SCORE and is cached as if complete. Size the budget to the
# candidate count instead: small inboxes stay well under the old default (cheaper, and the partial
# parser is O(N²) in buffer length), and a full 250-item set gets the headroom it needs.
RANK_OUTPUT_TOKENS_BASE = 512
RANK_OUTPUT_TOKENS_PER_ENTRY = 24


def _rank_output_max_tokens(candidate_count: int) -> int:
    return RANK_OUTPUT_TOKENS_BASE + RANK_OUTPUT_TOKENS_PER_ENTRY * candidate_count


def _resolve_entry_numbers(entry_numbers: list[int], entries_by_number: dict[int, str]) -> list[str]:
    """Map the 1-based item numbers the LLM returns back to real mailbox entry ids.

    Out-of-range numbers (hallucinated or off-by-one) are dropped and duplicates are collapsed
    while preserving order. This is the reconciliation point that keeps fabricated references out
    of the cache and broadcast payloads.
    """
    ids: list[str] = []
    seen: set[str] = set()
    for number in entry_numbers:
        entry_id = entries_by_number.get(number)
        if entry_id is not None and entry_id not in seen:
            seen.add(entry_id)
            ids.append(entry_id)
    return ids


def _log_entry_coverage(
    *,
    view_id: str,
    layout: MailboxViewLayout,
    candidate_count: int,
    placed_count: int,
    emitted_numbers: list[int],
) -> None:
    # Ranked views sentinel-score every candidate the LLM left unscored, so a shortfall there is
    # recoverable telemetry (how much the LLM under-scores) rather than lost entries — info, not a
    # warning. Grouped views have no such backfill: an unplaced entry never renders, so its shortfall
    # is a genuine loss worth warning on. Full coverage is the norm for both and stays silent.
    dropped_count = candidate_count - placed_count
    out_of_range = sum(1 for number in emitted_numbers if not 1 <= number <= candidate_count)
    if dropped_count == 0 and out_of_range == 0:
        return
    distinct_in_range = len({number for number in emitted_numbers if 1 <= number <= candidate_count})
    with LoggingContext(
        view_id=view_id,
        layout=layout.value,
        candidate_count=candidate_count,
        emitted_total=len(emitted_numbers),
        emitted_distinct_in_range=distinct_in_range,
        emitted_out_of_range=out_of_range,
        placed_count=placed_count,
        dropped_count=dropped_count,
    ):
        if layout == MailboxViewLayout.RANKED:
            logger.info(
                "mailbox view LLM under-scored [%s]: scored %d of %d candidates, %d sentinel-filled, "
                "%d out-of-range refs",
                layout.value,
                placed_count,
                candidate_count,
                dropped_count,
                out_of_range,
            )
        else:
            logger.warning(
                "mailbox view generation came back short [%s]: %d of %d sent items missing, %d out-of-range refs",
                layout.value,
                dropped_count,
                candidate_count,
                out_of_range,
            )


def _coerce_entry_numbers(value: object) -> list[int]:
    """Keep the values that read as usable 1-based item numbers, dropping anything malformed.

    Only reached for the self-nested repair path (see `_as_llm_section`), where raw unvalidated
    dicts arrive. A single bad element (a fractional float, a non-numeric string) would otherwise
    fail `list[int]` validation and drop the whole section, so we salvage the valid numbers and let
    `_resolve_entry_numbers` discard any that fall out of range.
    """
    if not isinstance(value, list):
        return []
    numbers: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            numbers.append(item)
        elif isinstance(item, float) and item.is_integer():
            numbers.append(int(item))
        elif isinstance(item, str) and item.strip().lstrip("-").isdigit():
            numbers.append(int(item.strip()))
    return numbers


def _as_llm_section(item: object) -> LLMViewSection | None:
    """Coerce a streamed section into an `LLMViewSection`.

    Instructor normally hands us validated `LLMViewSection` instances. But when Sonnet self-nests
    the response as `{"sections": {"sections": [...]}}`, the unwrap repair in `infra.llm` hoists the
    inner list as raw dicts that were never validated. Validate those here so a self-nested response
    still yields sections instead of silently completing with none.
    """
    if isinstance(item, LLMViewSection):
        return item
    if isinstance(item, dict):
        # Salvage the entry numbers before validating so one malformed number doesn't sink the
        # whole section — the entire reason this PR moved off hand-transcribed UUIDs.
        candidate = {**item, "entry_numbers": _coerce_entry_numbers(item.get("entry_numbers"))}
        try:
            return LLMViewSection.model_validate(candidate)
        except ValidationError:
            return None
    return None


def _view_section_from_llm(llm_section: LLMViewSection, entries_by_number: dict[int, str]) -> ViewSection:
    # goal_id is the one reference the LLM still transcribes as a raw 36-char UUID rather than an
    # "Item N" number, so it gets the same truncation/mangling that pushed entry ids onto numbers
    # (see LLMViewSection). Drop anything that doesn't parse as a UUID: a malformed id would
    # otherwise be cached and crash every later Goal.filter(id__in=...) read with a bind error.
    valid_goal_id = parse_uuid(llm_section.goal_id)
    return ViewSection(
        title=llm_section.title,
        description=llm_section.description,
        mailbox_entry_ids=_resolve_entry_numbers(llm_section.entry_numbers, entries_by_number),
        goal_id=str(valid_goal_id) if valid_goal_id else None,
    )


def _gated_section(raw: object, entries_by_number: dict[int, str]) -> ViewSection | None:
    """Coerce a streamed section to a `ViewSection` with resolved ids, or None if it fails to
    validate or doesn't clear the streaming gate (a section needs a title and at least one real
    item — a section whose numbers were all hallucinated resolves to no ids and is dropped).
    """
    llm_section = _as_llm_section(raw)
    if llm_section is None:
        return None
    section = _view_section_from_llm(llm_section, entries_by_number)
    if not section.title or not section.mailbox_entry_ids:
        return None
    return section


@dataclass
class ViewGenerationSession:
    """
    Coordinates a single mailbox view LLM generation across multiple subscribers.

    Only exists during active generation. Cache is checked BEFORE creating a session.
    Self-destructs after generation completes and results are cached.
    """

    view_id: str
    topic: Topic
    sections: list[ViewSection] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _generation_task: asyncio.Task | None = field(default=None, init=False)

    async def start_generation_with_request(
        self,
        view_request: str,
        mailbox_entries: list[MailboxEntryPresenter],
        current_user: User,
        cache_writer: CacheWriter,
        cache_clearer: Callable[[], Awaitable[object]],
        goals: list[Goal] | None = None,
        layout: MailboxViewLayout = MailboxViewLayout.GROUPED,
    ):
        """Start LLM generation with a view_request string. Idempotent."""
        async with self._lock:
            if self._generation_task is not None:
                return
            self._generation_task = asyncio.create_task(
                self._generate_sections_from_request(
                    view_request, mailbox_entries, current_user, cache_writer, cache_clearer, goals, layout
                )
            )

    async def _generate_sections_from_request(
        self,
        view_request: str,
        mailbox_entries: list[MailboxEntryPresenter],
        current_user: User,
        cache_writer: CacheWriter,
        cache_clearer: Callable[[], Awaitable[object]],
        goals: list[Goal] | None = None,
        layout: MailboxViewLayout = MailboxViewLayout.GROUPED,
    ):
        # Ranked sorts (custom sorts) score each item and render one flat list; their generation
        # engine is kept separate from the grouped section pipeline (and self-contained with its own
        # try/finally) so the custom-views refactor can lift it wholesale. The ranked branch must win
        # *before* the goals fork below, or a goal-targeted ranked sort would fall into the grouped
        # organize_by_goals prompt.
        if layout.is_ranked:
            await self._generate_ranked_section(
                view_request, mailbox_entries, current_user, cache_writer, cache_clearer, goals
            )
            return

        # The LLM references items by their 1-based position in the prompt list; map those numbers
        # back to real ids here so cached/broadcast sections always carry valid candidate UUIDs.
        entries_by_number = {number: str(entry.id) for number, entry in enumerate(mailbox_entries, start=1)}

        emitted_sections: set[int] = set()
        last_partial = None
        failed = False
        # Stable baseline reused across partial writes so the "new messages since" count doesn't
        # reset on each one; the final write stamps a fresh `cached_at`.
        started_at = datetime.now(UTC)
        partial_written_count = 0

        async def on_retry(attempt: int) -> None:
            nonlocal partial_written_count
            emitted_sections.clear()
            self.sections.clear()
            partial_written_count = 0
            await self.topic.broadcast(kind="regenerating", attempt=attempt)

        try:
            # Build the prompt inside the guard: template rendering reads model relations that can
            # raise (e.g. an unfetched goal.subgoals → NoValuesFetched). An unguarded raise here would
            # kill the generation task silently — no error broadcast, no cleanup, UI stuck "Organizing…".
            if goals is not None:
                system_prompt = build_prompt(
                    "mailbox/organize_by_goals.md.jinja",
                    mailbox_entries=mailbox_entries,
                    goals=goals,
                    current_user=current_user,
                    organization=current_user.organization,
                )
            else:
                system_prompt = build_prompt(
                    "mailbox/customize_list.md.jinja",
                    mailbox_entries=mailbox_entries,
                    customization_request=view_request,
                    current_user=current_user,
                    organization=current_user.organization,
                )
            async for partial in current_user.organization.llm.streaming_partial_json_completion(
                user_prompt="Organize the inbox items according to my request.",
                system_prompt=system_prompt,
                response_model=LLMMailboxViewResponse,
                temperature=0.0,
                on_retry=on_retry,
            ):
                last_partial = partial
                if not partial.sections:
                    continue

                # Emit a section as soon as instructor promotes it from a partial dict to a
                # validated `LLMViewSection` — that happens the moment the closing `}` of the
                # section's JSON is parsed, which is the earliest reliable signal that the LLM
                # has finished writing it. Previously we required section[i+1] to *start*
                # before emitting section[i], which held every section back by a full LLM
                # round trip and delayed the final section until the entire stream ended.
                for i, raw_section in enumerate(partial.sections):
                    if i in emitted_sections:
                        continue
                    section = _gated_section(raw_section, entries_by_number)
                    if section is None:
                        continue
                    self.sections.append(section)
                    await self.topic.broadcast(section_index=i, section=section.model_dump())
                    emitted_sections.add(i)

                # Persist the sections accumulated so far as a partial, so a refresh mid-generation
                # renders them instead of blanking until the whole stream completes.
                if len(self.sections) > partial_written_count:
                    partial_written_count = len(self.sections)
                    await cache_writer(
                        [section.model_dump() for section in self.sections],
                        generating=True,
                        cached_at=started_at,
                    )

            # Defensive tail-flush: if the very last section never reached the "has ids" gate
            # during streaming (e.g. the LLM closed the array but stopped immediately), emit it
            # now from the final partial so the user still sees it.
            if last_partial and last_partial.sections:
                last_idx = len(last_partial.sections) - 1
                if last_idx not in emitted_sections:
                    section = _gated_section(last_partial.sections[last_idx], entries_by_number)
                    if section is not None:
                        self.sections.append(section)
                        await self.topic.broadcast(section_index=last_idx, section=section.model_dump())

            emitted_numbers: list[int] = []
            for raw_section in last_partial.sections if last_partial and last_partial.sections else []:
                llm_section = _as_llm_section(raw_section)
                if llm_section is not None:
                    emitted_numbers.extend(llm_section.entry_numbers)
            placed_ids = {entry_id for section in self.sections for entry_id in section.mailbox_entry_ids}
            _log_entry_coverage(
                view_id=self.view_id,
                layout=layout,
                candidate_count=len(entries_by_number),
                placed_count=len(placed_ids),
                emitted_numbers=emitted_numbers,
            )

            if self.sections:
                # `self.sections` already holds exactly the gated sections in stream order, so cache
                # those rather than re-coercing and re-resolving the raw partial a second time. An
                # incomplete partial (e.g. mid-section truncation) never made it past the gate and
                # so is absent here, which is what keeps empty headers out of the next page load.
                cacheable_sections = [section.model_dump() for section in self.sections]
                await cache_writer(cacheable_sections)
            else:
                # The candidate set is always >= MAILBOX_VIEW_MIN_ENTRIES (enforced before the
                # session starts), and the number->id map only ever resolves real candidate ids, so
                # zero gated sections means the model returned only empty sections or item numbers
                # that all fell out of range. Surface an explicit error and leave the cache untouched
                # rather than completing with blank "Nothing in this category" sections.
                failed = True
                await self.topic.broadcast(error=EMPTY_GENERATION_ERROR)

        except Exception as e:
            logger.exception("Error generating view sections")
            failed = True
            # Context-overflow detection on BadRequestError relies on Anthropic's message
            # text, which is observed behavior, not officially documented.
            # See: https://docs.anthropic.com/en/api/errors
            is_overflow = isinstance(e, BadRequestError) and "prompt is too long" in str(e).lower()
            await self.topic.broadcast(error=CONTEXT_OVERFLOW_ERROR if is_overflow else GENERIC_GENERATION_ERROR)

        finally:
            if not failed:
                # Signal-only: React already has the streamed sections; new subscribers get a
                # snapshot via _replay_session_sections before the session is cleaned up.
                await self.topic.broadcast(complete=True)
            elif partial_written_count > 0:
                # A partial was cached but generation then failed. Delete it so the next load is a
                # clean cache-miss that regenerates, rather than a stuck `generating=True` partial the
                # cache-hit subscribe path would never refresh.
                await cache_clearer()
            await view_generation_manager.cleanup_session(self.view_id)

    async def _generate_ranked_section(
        self,
        view_request: str,
        mailbox_entries: list[MailboxEntryPresenter],
        current_user: User,
        cache_writer: CacheWriter,
        cache_clearer: Callable[[], Awaitable[object]],
        goals: list[Goal] | None = None,
    ):
        """Stream a single score-ordered section. The LLM scores each candidate; the server sorts."""
        entries_by_number = {number: str(entry.id) for number, entry in enumerate(mailbox_entries, start=1)}
        # Candidates arrive most-recent-first; this index is the recency tiebreak for equal scores.
        candidate_ids = list(entries_by_number.values())
        candidate_rank = {entry_id: index for index, entry_id in enumerate(candidate_ids)}

        # Stable baseline reused across every partial write so the "new messages since" count
        # doesn't reset on each throttled write; the final write stamps a fresh `cached_at`.
        started_at = datetime.now(UTC)
        # `scored` doubles as the already-emitted set: each id is recorded + broadcast exactly once.
        scored: dict[str, float] = {}
        # How many scores were in the last partial cache write, so we only rewrite once enough new
        # ones have accumulated to be worth the cache round-trip.
        last_written_count = 0
        failed = False

        def order_candidates() -> list[str]:
            # Unscored candidates fall to a sentinel so the section stays a complete set; equal
            # scores are broken deterministically by recency then id so the order is stable/paginatable.
            return sorted(
                candidate_ids,
                key=lambda entry_id: (-scored.get(entry_id, SENTINEL_RANK_SCORE), candidate_rank[entry_id], entry_id),
            )

        def ranked_section() -> ViewSection:
            return ViewSection(title="", description="", mailbox_entry_ids=order_candidates(), goal_id=None)

        def resolve(entry: LLMRankedEntry | dict) -> tuple[str, float] | None:
            # Instructor hands us partial entries mid-stream — skip any without both fields. The
            # trailing entry of a partial isn't finalized into an LLMRankedEntry until a later entry
            # proves it complete, so the final partial's last element (the one the tail-flush reads)
            # can still be a raw dict. Read both shapes, mirroring `_as_llm_section` for grouped views.
            if isinstance(entry, dict):
                entry_number, score = entry.get("entry_number"), entry.get("score")
            else:
                entry_number, score = entry.entry_number, entry.score
            if entry_number is None or score is None:
                return None
            entry_id = entries_by_number.get(entry_number)
            return (entry_id, score) if entry_id is not None else None

        async def ingest_scored(entry_id: str, score: float) -> None:
            # Record + broadcast a scored entry once. The client maintains its own sorted list and
            # inserts by score, so the per-entry frame is all it needs; `self.sections` is built once
            # at the end (for the cache) rather than re-sorted on every delta — and ranked
            # generation intentionally emits no section frames mid-stream.
            if entry_id in scored:
                return
            scored[entry_id] = score
            # `rank` is the recency ordinal the server tie-breaks on (see order_candidates). The client
            # mirrors that tuple so its live order matches the cached order exactly — without it, the
            # client would have to fall back to a different tiebreak (hydrated last_activity_at) that
            # reshuffles equal-score rows as entries load in.
            await self.topic.broadcast(
                kind="entry_scored", entry_id=entry_id, score=score, rank=candidate_rank[entry_id]
            )

        async def on_retry(attempt: int) -> None:
            nonlocal last_written_count
            scored.clear()
            self.sections.clear()
            last_written_count = 0
            await self.topic.broadcast(kind="regenerating", attempt=attempt)

        last_partial = None
        try:
            # Build the prompt inside the guard: rendering reads goal relations (e.g. goal.subgoals)
            # that can raise NoValuesFetched. An unguarded raise here would kill the generation task
            # silently — no error broadcast, no cleanup — leaving the UI stuck on "Organizing…".
            system_prompt = build_prompt(
                "mailbox/rank_list.md.jinja",
                mailbox_entries=mailbox_entries,
                customization_request=view_request,
                goals=goals,
                current_user=current_user,
                organization=current_user.organization,
            )
            async for partial in current_user.organization.llm.streaming_partial_json_completion(
                user_prompt="Score the inbox items against my request.",
                system_prompt=system_prompt,
                response_model=LLMMailboxRankResponse,
                max_tokens=_rank_output_max_tokens(len(mailbox_entries)),
                temperature=0.0,
                on_retry=on_retry,
            ):
                last_partial = partial
                # A malformed stream can momentarily parse `entries` as a non-list (e.g. an object
                # like `{"entries": {...}}`); skip those partials so the bad attempt streams through
                # to its final ValidationError + retry rather than crashing the consumer here.
                if not isinstance(partial.entries, list) or not partial.entries:
                    continue
                # Stream a delta per entry as soon as its {entry_number, score} object is final. An
                # object is final once a LATER entry has appeared (the array moved on); emitting on
                # "both fields present" alone risks catching a float score mid-parse (0 before 0.8).
                # The trailing entry has no successor yet, so it is deferred to the tail-flush below.
                for entry in partial.entries[:-1]:
                    resolved = resolve(entry)
                    if resolved is not None:
                        await ingest_scored(*resolved)

                # Persist a partial ordering periodically so a refresh mid-sort renders the
                # best-available order (the whole candidate set, sentinels last) instead of blanking.
                # `ranked_section()` already includes every candidate, so the partial is complete in
                # membership — only the ordering refines as more scores land.
                if len(scored) - last_written_count >= RANKED_PARTIAL_WRITE_INTERVAL:
                    last_written_count = len(scored)
                    await cache_writer([ranked_section().model_dump()], generating=True, cached_at=started_at)

            # Tail-flush the final partial's trailing entry (now final), then sentinel-score every
            # candidate the LLM never scored so the ranked set stays complete on the client too.
            if last_partial and isinstance(last_partial.entries, list) and last_partial.entries:
                resolved = resolve(last_partial.entries[-1])
                if resolved is not None:
                    await ingest_scored(*resolved)

            raw_entries = last_partial.entries if last_partial and isinstance(last_partial.entries, list) else []
            emitted_numbers = _coerce_entry_numbers(
                [entry.get("entry_number") if isinstance(entry, dict) else entry.entry_number for entry in raw_entries]
            )
            _log_entry_coverage(
                view_id=self.view_id,
                layout=MailboxViewLayout.RANKED,
                candidate_count=len(candidate_ids),
                placed_count=len(scored),
                emitted_numbers=emitted_numbers,
            )

            if scored:
                # Sentinel-score every candidate the LLM never scored, in one frame, so the ranked
                # set stays complete on the client without a NOTIFY per unscored id.
                unscored = [entry_id for entry_id in candidate_ids if entry_id not in scored]
                if unscored:
                    # Parallel `ranks` array (aligned to entry_ids) carries each sentinel candidate's
                    # recency ordinal so the client tie-breaks the whole sentinel tail identically.
                    await self.topic.broadcast(
                        kind="entries_scored",
                        entry_ids=unscored,
                        ranks=[candidate_rank[entry_id] for entry_id in unscored],
                        score=SENTINEL_RANK_SCORE,
                    )
                # Build the complete ordered section once (scored desc, sentinels last) and cache it
                # as one whole section for the next page load + replay.
                self.sections = [ranked_section()]
                await cache_writer([section.model_dump() for section in self.sections])
            else:
                # The LLM scored nothing usable (every entry number out of range, or no entries at
                # all). Surface an explicit error and leave the cache untouched rather than caching a
                # bare recency-ordered list that never reflected the request.
                failed = True
                await self.topic.broadcast(error=EMPTY_GENERATION_ERROR)

        except Exception as e:
            logger.exception("Error generating ranked view section")
            failed = True
            is_overflow = isinstance(e, BadRequestError) and "prompt is too long" in str(e).lower()
            await self.topic.broadcast(error=CONTEXT_OVERFLOW_ERROR if is_overflow else GENERIC_GENERATION_ERROR)

        finally:
            if not failed:
                await self.topic.broadcast(complete=True)
            elif last_written_count > 0:
                # A partial was cached but generation then failed — delete it so the next load
                # regenerates cleanly instead of resurrecting a stuck `generating=True` partial.
                await cache_clearer()
            await view_generation_manager.cleanup_session(self.view_id)


@dataclass
class ViewGenerationManager:
    """
    Manages active view generation sessions.

    Sessions only exist during in-flight LLM generation.
    Once generation completes and results are cached, sessions self-destruct.
    """

    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _sessions: dict[str, ViewGenerationSession] = field(default_factory=dict, init=False)

    async def get_or_create_session(self, view_id: str, topic: Topic) -> ViewGenerationSession:
        async with self._lock:
            if view_id not in self._sessions:
                self._sessions[view_id] = ViewGenerationSession(view_id=view_id, topic=topic)
            return self._sessions[view_id]

    async def peek_session(self, view_id: str) -> ViewGenerationSession | None:
        async with self._lock:
            return self._sessions.get(view_id)

    async def cleanup_session(self, view_id: str):
        async with self._lock:
            self._sessions.pop(view_id, None)


view_generation_manager = ViewGenerationManager()


async def _replay_session_sections(channel: Channel, view_id_str: str) -> None:
    session = await view_generation_manager.peek_session(view_id_str)
    if not session:
        return
    for i, section in enumerate(session.sections):
        await _emit_section(channel, SectionBroadcast(section_index=i, section=section))


async def _handle_start_generation(channel: Channel, view_id_str: str) -> None:
    """Handle generation start request from channel subscription."""
    identifier = MailboxViewIdentifier.from_string(view_id_str)
    if not identifier:
        return

    user = channel.current_user
    topic = Topic("mailbox_view", view_id=view_id_str, user_id=str(user.id))

    source = await MailboxViewSource.resolve(identifier, user)
    if not source:
        return

    goals: list[Goal] | None = None
    if source.requires_goals:
        if identifier.goal_id is not None:
            # "By goal" targets a single chosen goal carried on the identifier. Resolve it
            # org-scoped (defense-in-depth; the API surface already returned 404/422 for a
            # foreign/closed goal) with the relations the ranked prompt injects. Must populate
            # `goals` before the guard below — a by_goal template has no view_request.
            goal, rejection = await _resolve_by_goal(identifier.goal_id, user, with_relations=True)
            if rejection is not None or goal is None:
                # The goal was valid at request time; reaching here means it was deleted or closed
                # since. Surface that specifically rather than the plural "create a goal first"
                # prompt, which is misleading for a single-goal sort.
                message = (
                    "This goal was closed. Pick another goal or sort."
                    if rejection == "closed"
                    else "This goal is no longer available."
                )
                await topic.broadcast(error=message)
                return
            goals = [goal]
        else:
            goals = await Goal.for_user(user)
            if not goals:
                await topic.broadcast(
                    error="Create a goal first, then come back to see your inbox organized by goals."
                )
                return

    if not source.view_request and not goals:
        return

    # Order explicitly rather than leaning on Meta.ordering: when the inbox exceeds the cap this is
    # what decides which entries are kept, so the recency selection must be intentional and not
    # silently change if the model's default ordering ever does.
    entries = await _ai_inbox_queryset(user).order_by("-last_activity_at").limit(MAILBOX_VIEW_MAX_ENTRIES)
    mailbox_entries = await MailboxEntryPresenter.create_from_list(entries, user.email, include_body=True)

    if len(mailbox_entries) < MAILBOX_VIEW_MIN_ENTRIES:
        await topic.broadcast(error="There aren't enough emails to organize. Try again when your inbox fills up.")
        return

    session = await view_generation_manager.get_or_create_session(view_id_str, topic)
    await session.start_generation_with_request(
        source.view_request or "",
        mailbox_entries,
        user,
        source.write_cache,
        source.clear_cache,
        goals=goals,
        layout=source.layout,
    )
