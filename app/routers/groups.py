from fastapi import APIRouter, Depends

from app.routers.dependencies import Helpers, get_current_user, get_helpers

router = APIRouter()


@router.get("/groups", dependencies=[Depends(get_current_user)])
async def groups_index(helpers: Helpers = Depends(get_helpers)):
    # get_current_user is a route dependency (not a param) only to enforce auth:
    # an anonymous request must redirect to login, not 500 on `current_user.is_admin`
    # in the template. The value itself isn't needed here — the template reads
    # current_user from the rendering context.
    return helpers.render("groups/index.html.jinja")
