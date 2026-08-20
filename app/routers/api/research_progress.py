from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.accounts import User
from app.models.commands import ResearchQuestion
from app.routers.dependencies import Channel, get_current_user, handle_stream
from config.enums import ChannelEventAction, ChannelEventResource

router = APIRouter(tags=["research"])


class PendingResearchQuestion(BaseModel):
    id: str
    title: str
    research_created_at: datetime | None


class ResearchProgressResponse(BaseModel):
    pending_research_questions: list[PendingResearchQuestion]


async def _get_pending_research_questions(user: User) -> list[ResearchQuestion]:
    return (
        await ResearchQuestion.filter(ResearchQuestion.filters.by_creator(user.id))
        .filter(ResearchQuestion.filters.not_completed)
        .prefetch_related("research")
        .all()
    )


def _build_response(pending: list[ResearchQuestion]) -> ResearchProgressResponse:
    return ResearchProgressResponse(
        pending_research_questions=[
            PendingResearchQuestion(
                id=str(q.id),
                title=q.title or "Untitled",
                research_created_at=q.research.created_at if q.research else None,
            )
            for q in pending
        ],
    )


@router.get("/research_progress", response_model=ResearchProgressResponse)
async def api_research_progress_show(current_user: User = Depends(get_current_user)) -> ResearchProgressResponse:
    pending = await _get_pending_research_questions(current_user)
    return _build_response(pending)


@handle_stream("research_progress")
async def research_progress_json_broadcast(channel: Channel, **data) -> None:
    pending = await _get_pending_research_questions(channel.current_user)
    await channel.send_event(
        ChannelEventResource.RESEARCH_PROGRESS,
        ChannelEventAction.UPDATED,
        **_build_response(pending).model_dump(mode="json"),
    )
