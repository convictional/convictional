from typing import Self
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, model_validator

from app.helpers.mailbox_focus import MailboxFocus, is_valid_focus_template, resolve_mailbox_focus
from app.models.accounts import User
from app.routers.dependencies import (
    INBOX_SORT_PREFERENCE_COOKIE,
    delete_inbox_sort_preference_cookie,
    get_current_user,
    set_inbox_sort_preference_cookie,
)
from config.enums import MailboxSort

# The inbox focus — which sort, saved view, or view template the inbox opens in — is stored in a
# long-lived httponly cookie, so the client can neither read nor write it via document.cookie:
# hence a resource. It rides /api/users/me/ because it configures no single domain resource; a
# focus is a choice *between* mailbox views, not a property of one.
router = APIRouter(tags=["inbox"])


class MailboxFocusResponse(BaseModel):
    # The resolved focus, already healed: a preference naming a deleted goal or saved view comes
    # back as the default. All-null means the default focus, i.e. the bare inbox URL — `sort` is
    # null rather than "newest" so the fields map 1:1 onto the inbox query params.
    sort: MailboxSort | None
    mailbox_view_template: str | None
    goal_id: str | None
    mailbox_view_id: str | None


class MailboxFocusUpdateRequest(BaseModel):
    sort: MailboxSort | None = None
    mailbox_view_template: str | None = None
    goal_id: UUID | None = None
    mailbox_view_id: UUID | None = None

    @model_validator(mode="after")
    def validate_focus(self) -> Self:
        if not self.focus.cookie_value:
            raise ValueError("one of sort, mailbox_view_template, or mailbox_view_id is required")
        if self.goal_id is not None and self.mailbox_view_template is None:
            raise ValueError("goal_id requires mailbox_view_template")
        if self.mailbox_view_template is not None and not is_valid_focus_template(self.mailbox_view_template):
            raise ValueError(f"unknown mailbox view template: {self.mailbox_view_template}")
        return self

    @property
    def focus(self) -> MailboxFocus:
        return MailboxFocus(
            sort=self.sort,
            mailbox_view_template=self.mailbox_view_template,
            goal_id=self.goal_id,
            mailbox_view_id=self.mailbox_view_id,
        )


@router.get("/users/me/mailbox_focus", response_model=MailboxFocusResponse)
async def api_users_me_mailbox_focus_show(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> MailboxFocusResponse:
    resolved = await resolve_mailbox_focus(request.cookies.get(INBOX_SORT_PREFERENCE_COOKIE), current_user)
    if resolved.stale:
        # Self-heal, so a preference pointing at something deleted stops being re-resolved on
        # every visit for the rest of the cookie's year-long life.
        delete_inbox_sort_preference_cookie(response)

    focus = resolved.focus
    return MailboxFocusResponse(
        sort=focus.sort,
        mailbox_view_template=focus.mailbox_view_template,
        goal_id=str(focus.goal_id) if focus.goal_id else None,
        mailbox_view_id=str(focus.mailbox_view_id) if focus.mailbox_view_id else None,
    )


@router.patch("/users/me/mailbox_focus", status_code=status.HTTP_204_NO_CONTENT)
async def api_users_me_mailbox_focus_update(
    body: MailboxFocusUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> Response:
    # Stamped on the response with the same flags a navigation would use, so a same-origin fetch
    # stores it identically and the cookie stays httponly.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    set_inbox_sort_preference_cookie(response, body.focus.cookie_value)
    return response
