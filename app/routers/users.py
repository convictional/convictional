from fastapi import APIRouter, Depends

from app.models.accounts import User
from app.routers.dependencies import Helpers, get_current_user, get_helpers

router = APIRouter()


@router.get("/organization/users")
async def organization_users_index(
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    # The React island fetches its own state from the /api/organization/users endpoints;
    # this handler only renders the shell it mounts into.
    return helpers.render("users/index.html.jinja")
