from uuid import UUID

from fastapi import APIRouter, Depends

from app.models.accounts import User
from app.models.workspaces.goals import Goal
from app.routers.dependencies import Helpers, get_current_user, get_helpers

router = APIRouter(tags=["goals"])


@router.get("/goal_alignments")
async def goal_alignments_index(helpers: Helpers = Depends(get_helpers)):
    return helpers.render("goal_alignments/index.html.jinja")


@router.get("/goals/{goal_id}/alignments")
async def goal_alignments_show(
    goal_id: UUID,
    helpers: Helpers = Depends(get_helpers),
    current_user: User = Depends(get_current_user),
):
    goal = await Goal.get_or_none(id=goal_id, organization_id=current_user.organization_id)
    if not goal:
        return helpers.redirect_to(helpers.url_for("goal_alignments_index"))

    return helpers.render("goal_alignments/show.html.jinja", goal=goal)
