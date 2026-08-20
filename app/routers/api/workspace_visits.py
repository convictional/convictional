from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.models.accounts import User
from app.models.collaboration.workspace import Event, Visit, Workspace
from app.routers.dependencies import get_current_user, get_workspace
from infra.messaging import Topic

router = APIRouter(tags=["workspace visits"])


class RecordVisitRequest(BaseModel):
    last_event_id: UUID | None = None


@router.post("/workspaces/{workspace_id}/visits", status_code=status.HTTP_204_NO_CONTENT)
async def api_workspaces_record_visit(
    body: RecordVisitRequest = RecordVisitRequest(),
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    # The cursor is a client-supplied event id; reject one that isn't an event in this workspace so a
    # crafted id can't poison view state (last_viewed_event_at drives chat unread and "Seen by").
    if body.last_event_id and not await Event.filter(id=body.last_event_id, workspace_id=workspace.id).exists():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="last_event_id is not an event in this workspace",
        )
    await Visit.record(current_user.id, workspace.id, body.last_event_id)
    # A recorded visit changes this collaborator's view state. Broadcast on the shared
    # workspace_collaborators stream so any viewer's cached collaborators (with view_state)
    # refreshes live — the goal "Seen by" avatars and the collaborators panel both read it.
    # visit_user_id lets the handler skip the actor, whose own tab already knows.
    await Topic("workspace_collaborators", workspace_id=workspace.id).broadcast(visit_user_id=str(current_user.id))
