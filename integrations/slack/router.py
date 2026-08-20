from fastapi import APIRouter, Depends, Query

from app.models.accounts import OAuthToken
from app.routers.dependencies import (
    Authentication,
    Helpers,
    get_authentication,
    get_helpers,
)
from config import logger
from config.enums import FlashLevel, Integration
from infra.db import transaction
from infra.oauth import InvalidGrantError
from integrations.slack.oauth import SlackAuthenticator

router = APIRouter()


@router.get("/integrations/slack/connect")
async def integrations_slack_connect(
    authentication: Authentication = Depends(get_authentication),
    return_to: str | None = Query(None),
    helpers: Helpers = Depends(get_helpers),
):
    helpers.remember_location(return_to or str(helpers.url_for("profile_edit")))

    authenticator = SlackAuthenticator(str(helpers.url_for("auth_slack_callback")))
    url = authenticator.get_authorization_url()
    return helpers.redirect_to(url)


@router.get("/auth/slack/callback")
async def auth_slack_callback(
    authentication: Authentication = Depends(get_authentication),
    code: str | None = Query(None),
    error: str | None = Query(None),
    helpers: Helpers = Depends(get_helpers),
):
    if error:
        logger.warning(f"Slack OAuth error: {error}")
        helpers.flash("Failed to connect Slack. Please try again.", level=FlashLevel.ERROR)
        return helpers.redirect_to(helpers.url_for("profile_edit"))

    if not code:
        helpers.flash("No authorization code received from Slack.", level=FlashLevel.ERROR)
        return helpers.redirect_to(helpers.url_for("profile_edit"))

    try:
        authenticator = SlackAuthenticator(str(helpers.url_for("auth_slack_callback")))
        token = await authenticator.get_token(code)
    except InvalidGrantError:
        helpers.flash("Slack authorization code was invalid. Please try again.", level=FlashLevel.ERROR)
        return helpers.redirect_to(helpers.url_for("profile_edit"))
    except Exception:
        logger.exception("Error exchanging Slack code for token")
        helpers.flash("An error occurred while connecting to Slack.", level=FlashLevel.ERROR)
        return helpers.redirect_to(helpers.url_for("profile_edit"))

    current_user = authentication.current_user
    if not current_user:
        helpers.flash("You must be logged in to connect Slack.", level=FlashLevel.ERROR)
        return helpers.redirect_to(helpers.url_for("login"))

    async with transaction() as connection:
        await OAuthToken.create_or_update_by_token(current_user, token, using_db=connection)

        if not current_user.is_integrated_with(Integration.SLACK):
            await current_user.add_integration(Integration.SLACK, using_db=connection)

    helpers.flash("Slack has been connected successfully.")
    return await helpers.redirect_back_or(to=helpers.url_for("profile_edit"))
