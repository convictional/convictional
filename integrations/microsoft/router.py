import base64
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.routers.dependencies import (
    Authentication,
    Helpers,
    get_authentication,
    get_helpers,
    get_or_create_user,
)
from config import settings
from config.enums import FlashLevel
from infra.oauth import InvalidGrantError, login_redirect_uri
from integrations.microsoft.oauth import MicrosoftAuthenticator

router = APIRouter(tags=["skip_onboarding"])


@router.get("/auth/microsoft")
async def auth_microsoft(
    authentication: Authentication = Depends(get_authentication),
    helpers: Helpers = Depends(get_helpers),
    code: str | None = Query(None),
):
    redirect_uri = login_redirect_uri("microsoft", str(helpers.url_for("auth_microsoft")))
    authenticator = MicrosoftAuthenticator(redirect_uri)

    if not code:
        kwargs: dict[str, str] = {}
        if settings.oauth_proxy_url:
            kwargs["state"] = base64.urlsafe_b64encode(
                json.dumps({"origin": str(settings.base_url)}).encode()
            ).decode()
        return helpers.redirect_to(authenticator.get_authorization_url(scopes=None, **kwargs))

    try:
        token = await authenticator.get_token(code)
    except InvalidGrantError:
        helpers.flash("Microsoft authorization code was invalid. Please try again.", level=FlashLevel.ERROR)
        return helpers.redirect_to(helpers.url_for("login"))

    if not token.id_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID token not found in response.")

    await get_or_create_user(authentication, token)

    return await helpers.redirect_back_or(to=helpers.url_for("mailbox_index"))
