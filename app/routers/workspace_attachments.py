from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.accounts import User
from app.models.collaboration.workspace import Attachment, Workspace
from app.routers.dependencies import Helpers, get_current_user, get_helpers, get_workspace

router = APIRouter()


@router.get("/workspaces/attachments/{attachment_id}/download")
async def attachment_download_global(
    attachment_id: UUID, current_user: User = Depends(get_current_user), helpers: Helpers = Depends(get_helpers)
):
    attachment = await Attachment.get(id=attachment_id).prefetch_related("file")

    # If the attachment has been associated with a workspace, apply its access control.
    if attachment.workspace_id:
        await get_workspace(attachment.workspace_id, current_user)
    elif attachment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    return helpers.redirect_to(await attachment.file.url(), status_code=status.HTTP_302_FOUND)


@router.get("/workspaces/{workspace_id}/attachments/{attachment_id}/download")
async def attachment_download(
    attachment_id: UUID, workspace: Workspace = Depends(get_workspace), helpers: Helpers = Depends(get_helpers)
):
    attachment = await workspace.attachments.all().get(id=attachment_id).prefetch_related("file")
    return helpers.redirect_to(await attachment.file.url(), status_code=status.HTTP_302_FOUND)
