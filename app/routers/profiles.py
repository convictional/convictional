from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse

from app.models.accounts import User
from app.routers.dependencies import Authentication, Helpers, get_authentication, get_current_user, get_helpers
from config import settings

router = APIRouter()


@router.get("/profile/edit")
async def profile_edit(helpers: Helpers = Depends(get_helpers), current_user: User = Depends(get_current_user)):
    # The React userSettings island fetches its own data (profile, timezone list,
    # and every integration's connection status), so the shell needs no context
    # beyond settings.has_google_oauth, which the template reads from globals.
    return helpers.render("profiles/edit.html.jinja")


@router.get("/profile/{user_id}/avatar")
async def user_avatar(
    user_id: UUID,
    authentication: Authentication = Depends(get_authentication),
    helpers: Helpers = Depends(get_helpers),
):
    # Stable URL for templates and JSON responses: GCS signed URLs require
    # async credential refresh, which can't run inside a sync Jinja render.
    #
    # The fake-login picker at /login renders avatars for every user without an
    # authenticated session, so when enable_fake_auth is on we allow the lookup
    # to proceed without an org-scoped current_user.
    if await authentication.has_valid_login():
        current_user = authentication.current_user
        assert current_user is not None
        user = await User.get(id=user_id, organization_id=current_user.organization_id)
    elif settings.enable_fake_auth:
        user = await User.get(id=user_id)
    else:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            detail="Redirecting to login",
            headers={"location": str(helpers.url_for("login"))},
        )
    if user.avatar_file_id is not None:
        await user.fetch_related("avatar_file")
        if user.avatar_file is not None:
            # Cap the redirect cache well below the 24h signed-URL expiry so a cached 302
            # can never point at an expired URL.
            return RedirectResponse(
                await user.avatar_file.url(),
                status_code=status.HTTP_302_FOUND,
                headers={"Cache-Control": "private, max-age=300"},
            )
    if user.oauth_picture:
        return helpers.redirect_to(user.oauth_picture, status_code=status.HTTP_302_FOUND)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
