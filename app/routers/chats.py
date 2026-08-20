from contextvars import ContextVar
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.jobs.content import ContentIndexingJob
from app.models.accounts import User
from app.models.workspaces.chat import Chat, ChatMessage
from app.routers.dependencies import get_current_user
from infra.jobs import enqueue_job

#
# Dependencies
#
#

chat_context: ContextVar[Chat | None] = ContextVar("chat_context", default=None)


async def get_chat(chat_id: UUID, current_user: User = Depends(get_current_user)) -> Chat:
    chat = await Chat.get_or_none(id=chat_id).prefetch_related("workspace__collaborators__user__avatar_file")
    if not chat or not chat.collaboration.can_be_accessed_by(current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return chat


async def get_chat_with_indexing(chat: Chat = Depends(get_chat)) -> Chat:
    chat_context.set(chat)
    return chat


async def index_chat(request: Request):
    yield
    if request.method.lower() in ["post", "put", "patch", "delete"]:
        if chat := chat_context.get():
            job = ContentIndexingJob.from_model(chat.organization_id, chat)
            job.unique = True
            await enqueue_job(job)


async def get_chat_message(message_id: UUID, chat: Chat = Depends(get_chat)) -> ChatMessage:
    return await ChatMessage.get(id=message_id, chat_id=chat.id).prefetch_related("user", "link_preview")


#
# Router
#
#

# The chat index and show pages are served by the SPA shell (see app/routers/spa.py,
# where the chats_index/chats_show route names now live). This router keeps only the
# shared dependencies (get_chat and the indexing helpers) that back the chat JSON API
# and the attachment download; it registers no page routes of its own.
router = APIRouter(tags=["chat"], dependencies=[Depends(index_chat, scope="function")])
