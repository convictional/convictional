from uuid import UUID

from fastapi import APIRouter, Depends

from app.models.accounts import User
from app.models.collaboration.workspace import Workspace
from app.routers.dependencies import (
    Helpers,
    get_current_user,
    get_helpers,
    index_workspace_resource,
)

router = APIRouter(dependencies=[Depends(index_workspace_resource, scope="function")])


# The access-request page is the only HTML surface left for workspace collaborators —
# it hosts a React island that talks to the API for state and submission.
@router.get("/workspaces/{workspace_id}/collaborators/access")
async def workspace_collaborators_request_access(
    workspace_id: UUID,
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    # Verify the workspace exists in the current user's organization. The island fetches
    # its own state from the API; 404s here keep the page from rendering for outsiders.
    workspace = await Workspace.get(id=workspace_id, organization_id=current_user.organization_id)
    return helpers.render("workspace_collaborators/access.html.jinja", workspace=workspace)
