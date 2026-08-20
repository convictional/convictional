from fastapi import APIRouter, Depends

from app.models.accounts import User
from app.routers.dependencies import Helpers, get_current_user, get_helpers

router = APIRouter()


@router.get("/organization/updates_configuration")
async def organization_updates_configuration_show(
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    # The React island fetches its own state from /api/organization/updates_configuration;
    # this handler only renders the shell it mounts into.
    return helpers.render("organization_updates_configuration/show.html.jinja")
