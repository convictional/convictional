"""
JSON API for the Slack connection, consumed by the React userSettings island. Status +
disconnect only — Connect redirects to Slack's OAuth, so it stays the redirect route
`integrations_slack_connect` in `router.py`. Mounted under `/api/...` from `app/main.py`.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.models.accounts import User
from app.routers.dependencies import get_current_user
from config.enums import Integration

router = APIRouter(tags=["slack integration"])

# Explicit, mutually-exclusive connection state rather than a bag of booleans.
# "unavailable" means the user can't self-serve a connect because no one in
# the org has installed the Slack app yet — the island shows the "ask your workspace
# admin to install" copy for that state.
SlackConnectionStatus = Literal["connected", "disconnected", "unavailable"]


class SlackConnectionResponse(BaseModel):
    status: SlackConnectionStatus


@router.get("/integrations/slack/connection", response_model=SlackConnectionResponse)
async def api_slack_connection_get(
    current_user: User = Depends(get_current_user),
) -> SlackConnectionResponse:
    if current_user.is_integrated_with(Integration.SLACK):
        connection_status: SlackConnectionStatus = "connected"
    elif await User.organization_has_integration(current_user.organization_id, Integration.SLACK):
        connection_status = "disconnected"
    else:
        connection_status = "unavailable"
    return SlackConnectionResponse(status=connection_status)


@router.delete("/integrations/slack/connection", status_code=status.HTTP_204_NO_CONTENT)
async def api_slack_connection_delete(
    current_user: User = Depends(get_current_user),
) -> Response:
    # remove_integration is idempotent (no-op when not integrated), so a DELETE when
    # nothing is connected still returns 204.
    await current_user.remove_integration(Integration.SLACK)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
