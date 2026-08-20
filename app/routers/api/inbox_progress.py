from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.accounts import User
from app.routers.dependencies import Channel, get_current_user, handle_stream
from config.enums import ChannelEventAction, ChannelEventResource, Integration

router = APIRouter(tags=["inbox"])


class InboxProgressResponse(BaseModel):
    is_onboarding_mailbox_sync_complete: bool
    onboarding_mailbox_sync_started_at: datetime | None
    has_gmail_integration: bool
    has_calendar_integration: bool
    # True when the user can use Google integrations (i.e. is not a Microsoft-SSO user).
    is_google_authenticated: bool


def _build_response(user: User) -> InboxProgressResponse:
    return InboxProgressResponse(
        is_onboarding_mailbox_sync_complete=user.is_onboarding_mailbox_sync_complete,
        onboarding_mailbox_sync_started_at=user.onboarding_mailbox_sync_started_at,
        has_gmail_integration=Integration.GMAIL in user.integrations,
        has_calendar_integration=Integration.RECALL_AI_CALENDAR in user.integrations,
        is_google_authenticated=not user.authentication.is_microsoft,
    )


@router.get("/inbox_progress", response_model=InboxProgressResponse)
async def api_inbox_progress_show(current_user: User = Depends(get_current_user)) -> InboxProgressResponse:
    return _build_response(current_user)


@handle_stream("inbox_progress")
async def inbox_progress_json_broadcast(channel: Channel, **data) -> None:
    # `channel.current_user` is loaded at WebSocket connect and is stale for the fields
    # we render off — `is_onboarding_mailbox_sync_complete` and `onboarding_*_at` —
    # so reload before serializing. Without this the React banner re-renders with
    # stale state instead of clearing on sync completion (commit 7d29cd50d).
    user = await User.get_or_none(id=channel.current_user.id).prefetch_related("oauth_tokens")
    if not user:
        return
    await channel.send_event(
        ChannelEventResource.INBOX_PROGRESS,
        ChannelEventAction.UPDATED,
        **_build_response(user).model_dump(mode="json"),
    )
