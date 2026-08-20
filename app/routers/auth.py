from fastapi import APIRouter, Depends, Form, HTTPException, Request, status

from app.models.workspaces.meetings import Organization
from app.routers.dependencies import (
    Authentication,
    Helpers,
    delete_inbox_sort_preference_cookie,
    get_authentication,
    get_helpers,
    get_or_create_user,
)
from config import settings
from infra.oauth import Token

router = APIRouter()


@router.post("/logout")
async def logout(
    authentication: Authentication = Depends(get_authentication), helpers: Helpers = Depends(get_helpers)
):
    await authentication.logout()
    response = helpers.redirect_to(helpers.url_for("login"))
    delete_inbox_sort_preference_cookie(response)
    return response


@router.get("/signup")
@router.get("/login")
async def login(
    request: Request,
    authentication: Authentication = Depends(get_authentication),
    helpers: Helpers = Depends(get_helpers),
):
    if await authentication.has_valid_login():
        return helpers.redirect_to(helpers.url_for("mailbox_index"))

    intent = "login"
    if helpers.request.url.path.endswith("signup"):
        intent = "signup"

    response = helpers.render(
        "accounts/login.html.jinja",
        intent=intent,
        all_organizations=(
            await Organization.all().prefetch_related("users__avatar_file") if settings.enable_fake_auth else []
        ),
    )
    # Opt out of bfcache so the back button can't replay a stale form whose
    # CSRF token no longer matches the current session cookie.
    response.headers["Cache-Control"] = "no-store"
    return response


@router.get("/policies/terms_of_use")
async def terms_of_use(helpers: Helpers = Depends(get_helpers)):
    if not settings.terms_of_service_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return helpers.redirect_to(str(settings.terms_of_service_url))


@router.get("/policies/privacy_policy")
async def privacy_policy(helpers: Helpers = Depends(get_helpers)):
    if not settings.privacy_policy_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return helpers.redirect_to(str(settings.privacy_policy_url))


#
# Fake login
#
#

if settings.enable_fake_auth:

    @router.post("/login/fake")
    async def login_fake_post(
        authentication: Authentication = Depends(get_authentication),
        email: str = Form(...),
        helpers: Helpers = Depends(get_helpers),
    ):
        await get_or_create_user(authentication, Token.fake(email))
        return await helpers.redirect_back_or(helpers.url_for("mailbox_index"))
