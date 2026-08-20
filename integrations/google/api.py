"""
JSON API for the Gmail integration connection, consumed by the React userSettings island.

Lives in `integrations/google/` because the handlers reach `has_gmail_scope` and
`GmailAccount`, and the .importlinter contract forbids `app -> integrations`. Mounted
under `/api/...` from `app/main.py` (mirroring `integrations/notion/api.py`).

This is the status + disconnect contract only. Connect is a browser navigation to a
third party, so it stays the redirect route `integrations_gmail_auth` in `router.py`
(separate from the mobile/native flow in `api_router.py`).
"""

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.models.accounts import User
from app.routers.dependencies import get_current_user
from config.enums import Integration, IntegrationConnectionStatus
from integrations.google.helpers import has_gmail_scope
from integrations.google.models import GmailAccount

router = APIRouter(tags=["gmail integration"])

# Explicit, mutually-exclusive connection state rather than a bag of booleans,
# shared via config.enums. "unavailable" means the user can't self-serve a
# connect because Gmail requires a Google login — the island shows that state's message.


class GmailConnectionResponse(BaseModel):
    status: IntegrationConnectionStatus
    # The GMAIL integration is set but the Google token no longer carries the Gmail
    # scopes — an auth error stripped them (gmail_oauth_error_handling) while keeping
    # the integration, so the connection needs re-authorizing. A refinement of, not a
    # replacement for, `status`: a never-connected user also reads as `disconnected`,
    # so `status` alone can't tell the two apart. The settings island keys off `status`
    # (reconnect and connect are the same OAuth flow there); the mailbox reauth badge
    # keys off this bit, which is the only place that distinction matters.
    requires_reauth: bool


@router.get("/integrations/gmail/connection", response_model=GmailConnectionResponse)
async def api_gmail_connection_get(
    current_user: User = Depends(get_current_user),
) -> GmailConnectionResponse:
    has_scope = has_gmail_scope(current_user)
    if has_scope:
        connection_status = IntegrationConnectionStatus.CONNECTED
    elif current_user.authentication.is_google:
        connection_status = IntegrationConnectionStatus.DISCONNECTED
    else:
        connection_status = IntegrationConnectionStatus.UNAVAILABLE
    return GmailConnectionResponse(
        status=connection_status,
        requires_reauth=current_user.is_integrated_with(Integration.GMAIL) and not has_scope,
    )


@router.delete("/integrations/gmail/connection", status_code=status.HTTP_204_NO_CONTENT)
async def api_gmail_connection_delete(
    current_user: User = Depends(get_current_user),
) -> Response:
    await GmailAccount.disconnect(current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
