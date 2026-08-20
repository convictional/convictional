from fastapi import APIRouter, Depends

from app.models.accounts import User
from app.routers.dependencies import Helpers, get_current_user, get_helpers

router = APIRouter()


@router.get("/integrations/notion/settings")
async def integrations_notion_settings(
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    return helpers.render("integrations/notion/settings.html.jinja")
