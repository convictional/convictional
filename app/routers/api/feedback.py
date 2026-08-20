import re
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, HttpUrl, field_validator

from app.jobs.mailers import SendFeedbackEmailJob
from app.models.accounts import User
from app.routers.dependencies import UnclaimedAttachments, get_current_user
from config import logger
from config.logging import LoggingContext
from infra.jobs import enqueue_job

router = APIRouter(tags=["feedback"])

_SENTRY_HEX_ID = re.compile(r"^[0-9a-f]{32}$")


def _validate_sentry_id(value: str | None) -> str | None:
    if not value:
        return None
    if _SENTRY_HEX_ID.fullmatch(value):
        return value
    with LoggingContext(sentry_id=value):
        logger.warning("Rejected invalid Sentry ID")
    return None


class FeedbackCreateRequest(BaseModel):
    description: str = Field(min_length=1, max_length=10_000)
    attachment_claim_id: UUID | None = None
    sentry_event_id: str | None = Field(default=None, max_length=64)
    current_url: HttpUrl | None = None

    @field_validator("description")
    @classmethod
    def description_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("description must not be blank")
        return v


@router.post("/feedback", status_code=status.HTTP_204_NO_CONTENT)
async def api_feedback_create(
    body: FeedbackCreateRequest,
    current_user: User = Depends(get_current_user),
) -> None:
    attachment_ids: list[UUID] = []
    if body.attachment_claim_id:
        unclaimed = await UnclaimedAttachments.find(body.attachment_claim_id, current_user.id)
        attachment_ids = [attachment.id for attachment in unclaimed.attachments]
        await unclaimed.claim_without_workspace()

    await enqueue_job(
        SendFeedbackEmailJob(
            url=str(body.current_url) if body.current_url else "/",
            user_email=current_user.email,
            description=body.description,
            attachment_ids=attachment_ids,
            sentry_event_id=_validate_sentry_id(body.sentry_event_id),
        )
    )
