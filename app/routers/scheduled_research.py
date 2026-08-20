from fastapi import APIRouter, Depends

from app.routers.dependencies import Helpers, get_helpers

router = APIRouter()


@router.get("/scheduled_research", name="scheduled_research_index")
async def scheduled_research_index(helpers: Helpers = Depends(get_helpers)):
    return helpers.render("scheduled_research/index.html.jinja")
