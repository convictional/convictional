from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.models.accounts import User
from app.routers.dependencies import Helpers, get_current_user, get_helpers

#
# Routes
#
#

router = APIRouter(tags=["meetings"])


@router.get("/meetings_collections")
async def meetings_collections_index(
    helpers: Helpers = Depends(get_helpers),
    current_user: User = Depends(get_current_user),
):
    return helpers.render("meetings_collections/index.html.jinja")


# The collection-show page folded into the meeting list page. Redirect
# permanently so existing bookmarks and already-sent email links land on the
# unified /meetings?collection_id={id} view. Validation (404 for missing or
# cross-org collections) happens at the target route.
@router.get("/meetings_collections/{collection_id}")
async def meetings_collections_show(
    collection_id: UUID,
    helpers: Helpers = Depends(get_helpers),
):
    return helpers.redirect_to(
        helpers.url_for("meetings_index").include_query_params(collection_id=str(collection_id)),
        status_code=status.HTTP_301_MOVED_PERMANENTLY,
    )
