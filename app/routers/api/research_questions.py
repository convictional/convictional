from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, field_validator

from app.jobs.research import start_research_from_question
from app.models.accounts import User
from app.models.commands import ResearchQuestion
from app.routers.dependencies import get_current_user
from config.enums import ResearchSource
from infra.db import transaction

router = APIRouter(tags=["research"])


class ResearchQuestionCreateRequest(BaseModel):
    body: str

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped


class ResearchQuestionResponse(BaseModel):
    id: str
    body: str
    title: str | None
    created_at: datetime


@router.post(
    "/research_questions",
    response_model=ResearchQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_research_questions_create(
    payload: ResearchQuestionCreateRequest,
    current_user: User = Depends(get_current_user),
) -> ResearchQuestionResponse:
    async with transaction() as connection:
        question = await ResearchQuestion.create(
            body=payload.body,
            sources=[ResearchSource.INTERNAL],
            creator_id=current_user.id,
            using_db=connection,
        )
        question.creator = current_user
        await start_research_from_question(question, connection)

    return ResearchQuestionResponse(
        id=str(question.id),
        body=question.body,
        title=question.title,
        created_at=question.created_at,
    )
