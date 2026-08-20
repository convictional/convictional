import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any, Self
from uuid import UUID, uuid4

from anthropic.types import RawContentBlockDeltaEvent, TextDelta
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from app.jobs.research import (
    PreparedScheduledResearch,
    PrepareScheduledResearchJob,
    ScheduledResearchJob,
)
from app.models.accounts import User
from app.models.commands import (
    SCHEDULED_RESEARCH_DEFAULT_TITLE,
    ResearchQuestion,
    ScheduledResearch,
)
from app.prompts import build_prompt
from app.prompts.engine import current_user_context
from app.routers.api.schemas import PaginatedResponse
from app.routers.dependencies import Channel, get_current_user, handle_stream
from config import logger
from config.enums import (
    ChannelEventAction,
    ChannelEventResource,
    LLMMessageRole,
    ResearchSource,
    ScheduledResearchFrequency,
)
from infra.cache import cache
from infra.db import Pagination, transaction
from infra.jobs import enqueue_job
from infra.llm import LLMMessage
from infra.messaging import Topic

router = APIRouter(tags=["scheduled research"])

PREVIEW_CACHE_PREFIX = "scheduled_research_preview:"
PREVIEW_CACHE_TTL = timedelta(minutes=10)

# Strong references to running stream tasks — asyncio only weakly refs scheduled tasks, so without this
# a GC pass mid-stream can raise "Task was destroyed but it is pending!" and drop the generation.
_preview_tasks: set[asyncio.Task] = set()


#
# Response models
#
#


class ScheduledResearchResponse(BaseModel):
    id: str
    title: str
    prompt: str
    frequency: ScheduledResearchFrequency
    hour: int
    day_of_week: str | None
    schedule_description: str
    next_run_at: datetime | None
    last_delivered_at: datetime | None
    preparation_failed_at: datetime | None
    created_at: datetime


class ScheduledResearchListResponse(PaginatedResponse):
    scheduled_researches: list[ScheduledResearchResponse]


class ScheduledResearchPreviewResponse(BaseModel):
    preview_id: str
    expires_at: datetime


class ScheduledResearchPrefillResponse(BaseModel):
    prompt: str


class ScheduledResearchRunNowResponse(BaseModel):
    enqueued: bool


#
# Request models
#
#


class ScheduledResearchCreateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    frequency: ScheduledResearchFrequency
    hour: int = Field(ge=0, le=23)
    day_of_week: str | None = None


class ScheduledResearchUpdateRequest(BaseModel):
    prompt: str | None = Field(default=None, min_length=1)
    frequency: ScheduledResearchFrequency | None = None
    hour: int | None = Field(default=None, ge=0, le=23)
    day_of_week: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("must set at least one field")
        return self


class ScheduledResearchPreviewRequest(BaseModel):
    prompt: str = Field(min_length=1)


#
# Helpers
#
#


def _scheduled_research_response(schedule: ScheduledResearch) -> ScheduledResearchResponse:
    return ScheduledResearchResponse(
        id=str(schedule.id),
        title=schedule.title,
        prompt=schedule.prompt,
        frequency=schedule.frequency,
        hour=schedule.hour,
        day_of_week=schedule.day_of_week,
        schedule_description=schedule.schedule_description,
        next_run_at=schedule.next_run_at,
        last_delivered_at=schedule.last_delivered_at,
        preparation_failed_at=schedule.preparation_failed_at,
        created_at=schedule.created_at,
    )


async def get_scheduled_research(
    scheduled_research_id: UUID,
    current_user: User = Depends(get_current_user),
) -> ScheduledResearch:
    schedule = await ScheduledResearch.get_or_none(
        id=scheduled_research_id, creator_id=current_user.id
    ).prefetch_related("creator", "organization")
    if not schedule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return schedule


def _validate_and_set_schedule(
    schedule: ScheduledResearch,
    frequency: ScheduledResearchFrequency,
    hour: int,
    day_of_week: str | None,
) -> None:
    error = schedule.validate_schedule(frequency, hour, day_of_week)
    if error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=error)
    schedule.set_schedule(frequency, hour, day_of_week)


#
# CRUD + run_now + prefill
#
#


@router.get("/scheduled_research", response_model=ScheduledResearchListResponse)
async def api_scheduled_research_index(
    cursor: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    queryset = ScheduledResearch.filter(ScheduledResearch.filters.by_creator(current_user.id)).prefetch_related(
        "creator"
    )
    pagination = await Pagination.create(ScheduledResearch, cursor=cursor, queryset=queryset)

    return ScheduledResearchListResponse(
        scheduled_researches=[_scheduled_research_response(s) for s in pagination.results],
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@router.post(
    "/scheduled_research",
    response_model=ScheduledResearchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_scheduled_research_create(
    body: ScheduledResearchCreateRequest,
    current_user: User = Depends(get_current_user),
):
    schedule = ScheduledResearch(
        title=SCHEDULED_RESEARCH_DEFAULT_TITLE,
        prompt=body.prompt,
        sources=[ResearchSource.INTERNAL],
        creator_id=current_user.id,
        organization_id=current_user.organization_id,
    )
    _validate_and_set_schedule(schedule, body.frequency, body.hour, body.day_of_week)

    async with transaction() as connection:
        await schedule.save(using_db=connection)
        await enqueue_job(PrepareScheduledResearchJob(scheduled_research_id=schedule.id), using_db=connection)

    await schedule.fetch_related("creator")
    return _scheduled_research_response(schedule)


@router.get("/scheduled_research/prefill", response_model=ScheduledResearchPrefillResponse)
async def api_scheduled_research_prefill(
    from_research_question: UUID = Query(...),
    current_user: User = Depends(get_current_user),
):
    question = await ResearchQuestion.get_or_none(id=from_research_question, creator_id=current_user.id)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return ScheduledResearchPrefillResponse(prompt=question.body)


@router.get("/scheduled_research/{scheduled_research_id}", response_model=ScheduledResearchResponse)
async def api_scheduled_research_show(
    schedule: ScheduledResearch = Depends(get_scheduled_research),
    current_user: User = Depends(get_current_user),
):
    return _scheduled_research_response(schedule)


@router.patch("/scheduled_research/{scheduled_research_id}", response_model=ScheduledResearchResponse)
async def api_scheduled_research_update(
    body: ScheduledResearchUpdateRequest,
    schedule: ScheduledResearch = Depends(get_scheduled_research),
    current_user: User = Depends(get_current_user),
):
    prompt_changed = body.prompt is not None and body.prompt != schedule.prompt

    if body.prompt is not None:
        schedule.prompt = body.prompt

    needs_schedule_update = any(v is not None for v in (body.frequency, body.hour, body.day_of_week))
    if needs_schedule_update:
        frequency = body.frequency or schedule.frequency
        hour = body.hour if body.hour is not None else schedule.hour
        day_of_week = body.day_of_week if body.day_of_week is not None else schedule.day_of_week
        _validate_and_set_schedule(schedule, frequency, hour, day_of_week)

    async with transaction() as connection:
        await schedule.save(using_db=connection)
        if prompt_changed:
            await enqueue_job(PrepareScheduledResearchJob(scheduled_research_id=schedule.id), using_db=connection)

    return _scheduled_research_response(schedule)


@router.delete(
    "/scheduled_research/{scheduled_research_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_scheduled_research_delete(schedule: ScheduledResearch = Depends(get_scheduled_research)):
    await schedule.soft_delete()


@router.post(
    "/scheduled_research/{scheduled_research_id}/run_now",
    response_model=ScheduledResearchRunNowResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def api_scheduled_research_run_now(schedule: ScheduledResearch = Depends(get_scheduled_research)):
    await enqueue_job(ScheduledResearchJob(scheduled_research_id=schedule.id, force=True))
    return ScheduledResearchRunNowResponse(enqueued=True)


#
# Preview
#
#


@router.post(
    "/scheduled_research/preview",
    response_model=ScheduledResearchPreviewResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def api_scheduled_research_preview_initiate(
    body: ScheduledResearchPreviewRequest,
    current_user: User = Depends(get_current_user),
):
    # Stash the raw prompt; the Haiku split runs later inside the stream handler so the POST
    # returns immediately and the user sees the preview dialog without blocking.
    preview_id = str(uuid4())
    await cache.write_json(
        f"{PREVIEW_CACHE_PREFIX}{preview_id}",
        {
            "prompt": body.prompt,
            "sources": [ResearchSource.INTERNAL.value],
            "owner_user_id": str(current_user.id),
        },
        PREVIEW_CACHE_TTL,
    )

    return ScheduledResearchPreviewResponse(
        preview_id=preview_id,
        expires_at=datetime.now(UTC) + PREVIEW_CACHE_TTL,
    )


@handle_stream("scheduled_research_preview")
async def handle_scheduled_research_preview_stream(channel: Channel, **data: Any):
    action = data.get("action")
    preview_id = channel.get_param("preview_id")
    if not preview_id:
        return

    if action == "start":
        payload = await cache.read_json(f"{PREVIEW_CACHE_PREFIX}{preview_id}")
        if not payload:
            await _send_preview_event(channel, "error", error="Preview session expired")
            return
        if payload.get("owner_user_id") != str(channel.current_user.id):
            return
        task = asyncio.create_task(_stream_preview(channel, preview_id, payload))
        _preview_tasks.add(task)
        task.add_done_callback(_preview_tasks.discard)
    elif action == "delta":
        await _send_preview_event(channel, "delta", text=data.get("text", ""))
    elif action == "complete":
        await _send_preview_event(channel, "complete")
    elif action == "error":
        await _send_preview_event(channel, "error", error=data.get("error", ""))


async def _send_preview_event(channel: Channel, preview_action: str, **extra: Any) -> None:
    await channel.send_event(
        ChannelEventResource.SCHEDULED_RESEARCH_PREVIEW,
        ChannelEventAction.UPDATED,
        preview_action=preview_action,
        **extra,
    )


async def _stream_preview(channel: Channel, preview_id: str, payload: dict) -> None:
    # Once generation starts we let it run to completion even if the subscriber disconnects. Cancelling
    # mid-stream would need cross-process coordination; for a short LLM call we'd rather eat the
    # wasted tokens on rare user-cancels than carry that state.
    topic = Topic("scheduled_research_preview", preview_id=preview_id, user_id=str(channel.current_user.id))
    try:
        try:
            prepared = await PreparedScheduledResearch.generate(channel.current_user.organization, payload["prompt"])
            topic_prompt = prepared.topic_prompt
            formatting_prompt = prepared.formatting_prompt
        except Exception:
            logger.exception("Preview preparation failed; falling back to raw prompt")
            topic_prompt = payload["prompt"]
            formatting_prompt = None

        context = await current_user_context(channel.current_user)
        system_prompt = build_prompt(
            "scheduled_research/preview.md.jinja",
            topic_prompt=topic_prompt,
            formatting_prompt=formatting_prompt,
            sources=payload["sources"],
            **context,
        )

        user_message = LLMMessage(
            id=str(uuid4()),
            role=LLMMessageRole.USER,
            content="Please generate the preview described in the system prompt.",
        )

        async for event in channel.current_user.organization.llm.chat_completion(
            system_prompt=system_prompt,
            prior_messages=[user_message],
            temperature=0.0,
            stream=True,
        ):
            if isinstance(event, RawContentBlockDeltaEvent) and isinstance(event.delta, TextDelta):
                if event.delta.text:
                    await topic.broadcast(action="delta", text=event.delta.text)

        await topic.broadcast(action="complete")
    except Exception:
        logger.exception("Preview stream failed for preview_id=%s", preview_id)
        await topic.broadcast(action="error", error="Sorry, an error occurred while generating the preview.")
    finally:
        await cache.delete(f"{PREVIEW_CACHE_PREFIX}{preview_id}")
