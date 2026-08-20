from fastapi import APIRouter, Depends

from app.routers.dependencies import Helpers, get_helpers

router = APIRouter()


@router.get("/")
async def background_jobs_new(
    helpers: Helpers = Depends(get_helpers),
):
    return helpers.render("background_jobs/new.html.jinja")
