from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.models.workspaces.email.thread import EmailAttachment, EmailDraft, EmailThread
from app.routers.api.schemas import EmailDraftAttachmentResponse, PaginatedResponse
from app.routers.api.serializers import attachment_response
from app.routers.dependencies import Helpers, get_email_draft, get_helpers
from app.routers.email_threads import get_email_thread
from infra.db import transaction
from infra.storage import FileReference, store_file

router = APIRouter(tags=["inbox"])


class EmailAttachmentListResponse(PaginatedResponse):
    attachments: list[EmailDraftAttachmentResponse]


@dataclass
class EmailAttachmentUploadParams:
    files: list[UploadFile]

    @classmethod
    async def create(cls, files: list[UploadFile] = File(...)) -> "EmailAttachmentUploadParams":
        if not files:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="No files provided")
        return cls(files=files)


async def get_email_attachment(email_thread_id: UUID, attachment_id: UUID) -> EmailAttachment:
    attachment = await EmailAttachment.get_or_none(id=attachment_id, thread_id=email_thread_id).prefetch_related(
        "file"
    )
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


@router.get(
    "/email_threads/{email_thread_id}/draft/attachments",
    response_model=EmailAttachmentListResponse,
)
async def api_email_attachments_index(
    email_draft: EmailDraft = Depends(get_email_draft),
    helpers: Helpers = Depends(get_helpers),
):
    return EmailAttachmentListResponse(
        attachments=[attachment_response(a, helpers) for a in email_draft.message.attachments],
    )


@router.post(
    "/email_threads/{email_thread_id}/draft/attachments",
    response_model=EmailAttachmentListResponse,
)
async def api_email_attachments_create(
    params: EmailAttachmentUploadParams = Depends(EmailAttachmentUploadParams.create),
    email_draft: EmailDraft = Depends(get_email_draft),
    helpers: Helpers = Depends(get_helpers),
):
    # Store blobs outside the transaction so we don't hold a DB connection during the slow
    # upload I/O. Once everything is on disk, create the rows in a single transaction so a
    # mid-loop DB failure can't leave the draft half-attached. Orphaned blobs are an
    # acceptable trade-off — they're invisible to the user.
    stored: list[tuple[UploadFile, FileReference]] = []
    for file in params.files:
        file_ref = await store_file(
            filename=file.filename,
            content=file.file,
            content_type=file.content_type,
        )
        stored.append((file, file_ref))

    created: list[EmailAttachment] = []
    async with transaction() as connection:
        for file, file_ref in stored:
            # Images dropped/pasted via the rich-text editor become inline parts so the
            # MIME builder can reference them with cid: URLs in the rendered body.
            is_inline = file.content_type.startswith("image/") if file.content_type else False

            attachment = await EmailAttachment.create(
                email_message=email_draft.message,
                file=file_ref,
                content_id=str(file_ref.id) if is_inline else None,
                is_inline=is_inline,
                thread_id=email_draft.thread_id,
                using_db=connection,
            )
            created.append(attachment)

    return EmailAttachmentListResponse(
        attachments=[attachment_response(a, helpers) for a in created],
    )


@router.delete(
    "/email_threads/{email_thread_id}/draft/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_email_attachments_delete(
    attachment: EmailAttachment = Depends(get_email_attachment),
    # get_email_thread already gates access via thread.collaboration.can_be_accessed_by.
    # The heavier get_email_draft dependency isn't needed here — we don't touch the draft
    # message body, just the attachment row scoped by thread_id.
    thread: EmailThread = Depends(get_email_thread),
):
    async with transaction() as connection:
        await attachment.delete(using_db=connection)
