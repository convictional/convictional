from urllib.parse import urlencode, urljoin
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.accounts import User
from app.models.workspaces.email.thread import EmailAttachment, EmailThread
from app.routers.dependencies import Helpers, get_current_user, get_helpers
from app.routers.email_threads import get_email_thread
from config import settings
from infra.email import sign_attachment_download_token, verify_attachment_download_token

#
# Dependencies
#
#


async def get_email_attachment(
    attachment_id: UUID,
    thread: EmailThread = Depends(get_email_thread),
) -> EmailAttachment:
    attachment = await EmailAttachment.get_or_none(id=attachment_id, thread_id=thread.id).prefetch_related("file")
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


#
# Router
#
#


router = APIRouter(tags=["inbox"])


@router.get("/email_threads/{email_thread_id}/attachments/{attachment_id}/download")
async def email_attachments_download(
    attachment: EmailAttachment = Depends(get_email_attachment),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    return helpers.redirect_to(await attachment.file.url(), status_code=status.HTTP_302_FOUND)


@router.get("/email_attachments/download")
async def email_attachments_download_public(
    token: str,
    helpers: Helpers = Depends(get_helpers),
):
    """Serve an oversized email attachment to an external recipient via a signed link.

    The signed token is the capability — external recipients have no Convictional session and
    aren't thread collaborators, so this route is intentionally public. The token never
    expires; the attachment stays downloadable however long after sending the recipient
    opens the email. GCS does the actual serving: we redirect to a fresh, short-lived
    signed URL minted per click. A bad token 404s rather than raising RequestAccessError,
    which must never leak thread existence here.
    """
    attachment_id = verify_attachment_download_token(token)
    if not attachment_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    attachment = await EmailAttachment.get_or_none(id=attachment_id).prefetch_related("file")
    if not attachment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")

    return helpers.redirect_to(await attachment.file.url(), status_code=status.HTTP_302_FOUND)


def signed_attachment_download_url(attachment_id: UUID) -> str:
    """Absolute public download link embedded in outbound email for oversized attachments.

    Reverses the route by name so the path stays in lockstep with the decorator above; the
    signed token is the capability carried in the query string.
    """
    token = sign_attachment_download_token(attachment_id)
    path = router.url_path_for("email_attachments_download_public")
    return urljoin(str(settings.base_url), f"{path}?{urlencode({'token': token})}")
