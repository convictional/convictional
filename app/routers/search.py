from fastapi import APIRouter, Depends, Query

from app.models.accounts import User
from app.routers.dependencies import Helpers, get_current_user, get_helpers

router = APIRouter()


@router.get("/search")
async def search_index(
    q: str = Query(""),
    helpers: Helpers = Depends(get_helpers),
    current_user: User = Depends(get_current_user),
):
    return helpers.render("search/index.html.jinja", query=q)
