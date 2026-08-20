from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.accounts import User
from app.models.collaboration.workspace import Attachment
from app.models.workspaces.chat import Chat, ChatMessage
from app.routers.chats import get_chat
from app.routers.dependencies import Helpers, get_current_user, get_helpers

router = APIRouter()


@router.get("/chats/{chat_id}/attachments/{attachment_id}/download")
async def chat_attachments_download(
    attachment_id: UUID,
    chat: Chat = Depends(get_chat),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    attachment = (
        await Attachment.filter(Attachment.filters.by_organization(chat.organization_id), id=attachment_id)
        .prefetch_related("file")
        .first()
    )

    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    if attachment.comment_gid:
        await ChatMessage.get(id=attachment.comment_gid.record_id, chat_id=chat.id)
    elif attachment.user_id != current_user.id:
        # Unclaimed attachments are only downloadable by the uploader (for composer previews)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return helpers.redirect_to(await attachment.file.url(), status_code=status.HTTP_302_FOUND)
