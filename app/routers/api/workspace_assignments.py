from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from app.jobs.content import ContentIndexingJob
from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.workspace import Workspace
from app.routers.api.schemas import WorkspaceAssignmentResponse, WorkspaceAssignmentUpdateRequest
from app.routers.api.serializers import user_response
from app.routers.dependencies import get_current_user, get_workspace, index_workspace_resource
from config.enums import EventAction
from infra.db import transaction
from infra.jobs import enqueue_job

router = APIRouter(dependencies=[Depends(index_workspace_resource, scope="function")], tags=["workspace assignments"])


@router.get("/workspaces/{workspace_id}/assignment", response_model=WorkspaceAssignmentResponse)
async def api_workspace_assignment_show(workspace: Workspace = Depends(get_workspace)):
    assignee = await workspace.resource.collaboration.get_assignee()
    return WorkspaceAssignmentResponse(assignee=user_response(assignee))


@router.patch("/workspaces/{workspace_id}/assignment", response_model=WorkspaceAssignmentResponse)
async def api_workspace_assignment_update(
    body: WorkspaceAssignmentUpdateRequest,
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    async with transaction() as connection:
        user = await User.get(id=body.user_id, organization_id=current_user.organization_id, using_db=connection)
        notifier = Notifier(workspace.resource, current_user)
        async with notifier.record_and_notify(
            action=EventAction.ASSIGNED, creator_id=current_user.id, using_db=connection
        ) as recording:
            await workspace.resource.collaboration.assign_to(user, current_user, using_db=connection)
            recording.event.details = {"assignee": user.field_values}

        await enqueue_job(
            ContentIndexingJob.from_model(workspace.organization_id, workspace.resource), using_db=connection
        )

    return WorkspaceAssignmentResponse(assignee=user_response(user))


@router.delete("/workspaces/{workspace_id}/assignment", status_code=status.HTTP_204_NO_CONTENT)
async def api_workspace_assignment_delete(
    workspace: Workspace = Depends(get_workspace),
    current_user: User = Depends(get_current_user),
):
    assignee = await workspace.resource.collaboration.get_assignee()
    if assignee is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    async with transaction() as connection:
        notifier = Notifier(workspace.resource, current_user)
        async with notifier.record_and_notify(
            action=EventAction.UNASSIGNED, creator_id=current_user.id, using_db=connection
        ) as recording:
            await workspace.resource.collaboration.unassign(assignee, using_db=connection)
            recording.event.details = {"assignee": assignee.field_values}

        await enqueue_job(
            ContentIndexingJob.from_model(workspace.organization_id, workspace.resource), using_db=connection
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
