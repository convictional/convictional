from dataclasses import dataclass
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.models.accounts import User
from app.models.collaboration.workspace import Attachment, Workspace
from app.routers.api.schemas import AttachmentUploadListResponse, AttachmentUploadResponse
from app.routers.dependencies import Helpers, get_current_user, get_helpers, get_workspace
from infra.db import transaction
from infra.storage import FileReference, store_file

router = APIRouter()

# Cloud Run buffers request bodies up to ~32 MB before they reach the app, so our
# limit sits below that: an oversized file gets a clear 413 from us instead of the
# platform's opaque rejection. Larger uploads (e.g. recordings) go direct to GCS.
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024


@dataclass
class AttachmentParams:
    files: list[UploadFile]
    current_user: User
    claim_id: UUID | None = None

    @classmethod
    async def create(
        cls,
        files: list[UploadFile] = File(...),
        current_user: User = Depends(get_current_user),
        claim_id: UUID = Form(None),
    ):
        if not files:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No files provided")

        for file in files:
            # Starlette populates size from the parsed multipart part; guard for None
            # so a missing size falls through rather than raising a type error.
            if file.size is not None and file.size > MAX_ATTACHMENT_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    detail=f"Files must be {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB or smaller.",
                )

        return cls(files, current_user, claim_id)


async def upload_attachments(params: AttachmentParams, workspace_id: UUID | None = None):
    # Store blobs outside the transaction so we don't hold a DB connection during the slow
    # upload I/O. Once everything is on disk, create the rows in a single transaction so a
    # mid-loop DB failure can't leave only some files attached. Orphaned blobs are an
    # acceptable trade-off — they're invisible to the user.
    stored: list[FileReference] = []
    for file in params.files:
        file_ref = await store_file(filename=file.filename, content=file.file, content_type=file.content_type)
        stored.append(file_ref)

    attachments = []
    async with transaction() as connection:
        for file_ref in stored:
            attachment = Attachment(
                workspace_id=workspace_id,
                user_id=params.current_user.id,
                title=file_ref.filename,
                claim_id=params.claim_id,
                file_id=file_ref.id,
            )
            await attachment.save(using_db=connection)
            attachments.append(attachment)

    return attachments


@router.post(
    "/workspaces/attachments",
    name="attachments_upload_global",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachmentUploadListResponse,
)
async def attachments_upload_global(
    params: AttachmentParams = Depends(AttachmentParams.create),
    helpers: Helpers = Depends(get_helpers),
):
    attachments = await upload_attachments(params)

    return AttachmentUploadListResponse(
        attachments=[
            AttachmentUploadResponse(
                download_url=str(helpers.url_for("attachment_download_global", attachment_id=attachment.id))
            )
            for attachment in attachments
        ]
    )


@router.post(
    "/workspaces/{workspace_id}/attachments",
    name="attachments_upload",
    status_code=status.HTTP_201_CREATED,
    response_model=AttachmentUploadListResponse,
)
async def attachments_upload(
    params: AttachmentParams = Depends(AttachmentParams.create),
    workspace: Workspace = Depends(get_workspace),
    helpers: Helpers = Depends(get_helpers),
):
    attachments = await upload_attachments(params, workspace_id=workspace.id)

    return AttachmentUploadListResponse(
        attachments=[
            AttachmentUploadResponse(
                download_url=str(
                    helpers.url_for("attachment_download", workspace_id=workspace.id, attachment_id=attachment.id)
                )
            )
            for attachment in attachments
        ]
    )
