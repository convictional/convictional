from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.models.accounts import User
from app.models.workspaces.email.thread import EmailMessage, EmailThread
from app.routers.dependencies import (
    RequestAccessError,
    get_current_user,
)

#
# Dependencies
#
#


async def get_email_thread(email_thread_id: UUID, current_user: User = Depends(get_current_user)) -> EmailThread:
    email_thread = await EmailThread.get(id=email_thread_id).prefetch_related(
        "messages__user",
        "messages__attachments__file",
        "workspace__collaborators__user",
        "workspace__assignee",
        "creator",
    )
    if email_thread.collaboration.can_be_accessed_by(current_user):
        return email_thread

    if email_thread.organization_id == current_user.organization_id:
        raise RequestAccessError(global_id=str(email_thread.global_id))

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Email thread not found")


async def get_email_message(email_message_id: UUID, thread: EmailThread = Depends(get_email_thread)) -> EmailMessage:
    email_message = await EmailMessage.get(id=email_message_id, thread_id=thread.id).prefetch_related(
        "attachments__file"
    )
    return email_message


# This module is dependency-only: get_email_thread / get_email_message above back
# the /api/email_threads/* surface and the attachment/draft flows. The show and
# original-message pages are served by the client-routed SPA shell (see
# app/routers/spa.py → SPA_ROUTES, which owns the email_threads_show /
# email_threads_show_original route names).
