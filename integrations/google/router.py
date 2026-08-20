import asyncio
import base64
import json
from typing import Any
from urllib.parse import urlencode, urljoin

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from google.oauth2.credentials import Credentials

from app.helpers.url import absolute_url
from app.models.accounts import User
from app.routers.dependencies import (
    Authentication,
    Helpers,
    get_authentication,
    get_current_user,
    get_helpers,
    get_or_create_user,
)
from config import logger, settings
from config.enums import AuthenticationProvider, FlashLevel, Integration
from infra.jobs import enqueue_job
from infra.oauth import InvalidGrantError, Token, login_redirect_uri
from integrations.google.gmail import build_people_client
from integrations.google.jobs.gmail import ProcessGmailHistoryJob, ReconnectGmailAccountJob, SetupGmailAccountJob
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_DEFAULT_SCOPES, GOOGLE_GMAIL_SCOPES, GoogleAuthenticator
from integrations.recall_ai.client import RecallAIClient
from integrations.recall_ai.models import RecallAICalendarPreferences

#
# Helpers
#
#


async def sync_google_email_aliases(token: Token, user: User):
    credentials = Credentials(
        token=token.access_token,
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
    )
    service = await asyncio.to_thread(build_people_client, credentials)
    request = service.people().get(
        resourceName="people/me",
        personFields="emailAddresses",
        # Filter out contact emails, we only want aliases from the profile
        sources=["READ_SOURCE_TYPE_PROFILE"],
    )
    results = await asyncio.to_thread(request.execute)
    email_addresses: list[str] = []
    for email_entry in results.get("emailAddresses", []):
        is_verified_address = email_entry.get("metadata", {}).get("verified", False)
        address = email_entry.get("value")
        if is_verified_address and address:
            email_addresses.append(address)

    await user.sync_email_aliases(email_addresses)


def google_calendar_auth_url(
    redirect_url: str,
    recall_calendar_auth_token: str,
    success_url: str | None = None,
    recall_calendar_preference: RecallAICalendarPreferences = RecallAICalendarPreferences.NONE,
):
    state_obj = {
        "recall_calendar_auth_token": recall_calendar_auth_token,
        "google_oauth_redirect_url": redirect_url,
        "recall_calendar_preference": recall_calendar_preference,
    }
    if success_url:
        state_obj["success_url"] = success_url

    query_params = {
        "response_type": "code",
        "client_id": settings.google_oauth_client_id,
        "redirect_uri": redirect_url,
        "scope": "https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/userinfo.email",
        "access_type": "offline",
        "prompt": "consent",
        "state": json.dumps(state_obj),
    }

    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(query_params)


async def validate_pubsub_token(request: Request) -> bool:
    if settings.enable_fake_auth:
        return True

    authorization_header = request.headers.get("Authorization")
    if not authorization_header or not authorization_header.startswith("Bearer "):
        logger.warning(f"Gmail webhook: Invalid authorization header format: {authorization_header}")
        return False

    token = authorization_header.split(" ", 1)[1]
    expected_audience = urljoin(str(settings.internal_base_url), "/")

    try:
        await asyncio.to_thread(
            id_token.verify_oauth2_token, token, google_requests.Request(), audience=expected_audience
        )
        return True
    except ValueError as e:
        logger.warning(f"Gmail webhook: Token validation failed - {e}")
        return False


#
# Router
#
#


router = APIRouter(tags=["skip_onboarding"])

#
# Authentication
#
#


@router.get("/auth/google")
async def auth_google(
    authentication: Authentication = Depends(get_authentication),
    helpers: Helpers = Depends(get_helpers),
    code: str | None = Query(None),
):
    redirect_uri = login_redirect_uri("google", str(helpers.url_for("auth_google")))
    authenticator = GoogleAuthenticator(redirect_uri)

    if not code:
        include_granted_scopes = "true" if settings.oauth_include_granted_scopes_on_login else "false"
        kwargs: dict[str, str] = {"include_granted_scopes": include_granted_scopes}
        if settings.oauth_proxy_url:
            kwargs["state"] = base64.urlsafe_b64encode(
                json.dumps({"origin": str(settings.base_url)}).encode()
            ).decode()
        return helpers.redirect_to(authenticator.get_authorization_url(scopes=None, **kwargs))
    try:
        token = await authenticator.get_token(code)
    except InvalidGrantError:
        helpers.flash("Google authorization code was invalid. Please try again.", level=FlashLevel.ERROR)
        return helpers.redirect_to(helpers.url_for("login"))

    if not token.id_token:
        # We should always receive an ID token from Google
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID token not found in response.")

    user = await get_or_create_user(authentication, token)

    await sync_google_email_aliases(token, user)

    # Requires a refresh token, not just the Gmail scopes: include_granted_scopes can hand the
    # scopes back on a plain login (no offline access) after a prior grant, and provisioning a
    # Gmail account off that would create a connection that can never refresh.
    google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    if (
        not user.authentication.is_microsoft
        and google_token
        and google_token.has_scopes(GOOGLE_GMAIL_SCOPES)
        and google_token.refresh_token
    ):
        if user.is_integrated_with(Integration.GMAIL):
            # Reconnecting an existing Gmail account
            gmail_account = await GmailAccount.get_or_none(user_id=user.id)
            await enqueue_job(ReconnectGmailAccountJob(user_id=user.id))
            if gmail_account and gmail_account.has_auth_error:
                helpers.flash("Your Gmail account has been reconnected.")
        else:
            # Setup a new Gmail account
            await enqueue_job(SetupGmailAccountJob(user_id=user.id))
            await user.add_integration(Integration.GMAIL)
            helpers.flash(
                "Loading your email history. This usually takes about 1 hour. We'll send an email once we're done."
            )

    return await helpers.redirect_back_or(to=helpers.url_for("mailbox_index"))


#
# Gmail
#
#


@router.get("/integrations/gmail/auth")
async def integrations_gmail_auth(
    current_user: User = Depends(get_current_user),
    return_to: str | None = Query(None),
    helpers: Helpers = Depends(get_helpers),
):
    if current_user.authentication.is_microsoft:
        helpers.flash("Connecting Gmail is not supported for your sign-in method.", level=FlashLevel.ERROR)
        return helpers.redirect_to(return_to or str(helpers.url_for("profile_edit")))

    helpers.remember_location(return_to or str(helpers.url_for("profile_edit")))

    redirect_uri = login_redirect_uri("google", str(helpers.url_for("auth_google")))
    authenticator = GoogleAuthenticator(redirect_uri)
    extra_params: dict[str, str] = {}
    if settings.oauth_proxy_url:
        state = base64.urlsafe_b64encode(json.dumps({"origin": str(settings.base_url)}).encode()).decode()
        extra_params["state"] = state
    url = authenticator.get_authorization_url(
        scopes=GOOGLE_DEFAULT_SCOPES + GOOGLE_GMAIL_SCOPES,
        # Incremental authorization: merge these Gmail scopes with the user's
        # already-granted login scopes rather than replacing them. Google-specific.
        include_granted_scopes="true",
        access_type="offline",
        prompt="consent",
        **extra_params,
    )
    return helpers.redirect_to(url)


@router.post("/integrations/gmail/webhook")
async def integrations_gmail_webhook(request: Request, body: dict = Body(...)):
    if not await validate_pubsub_token(request):
        logger.warning("Gmail webhook: received invalid or missing OIDC token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid authentication token")

    message: dict[str, Any] = body.get("message", {})
    if not message:
        logger.warning("Gmail webhook: received webhook without message payload")
        return {"status": "ok"}

    data = message.get("data", "")
    if not data:
        logger.warning("Gmail webhook: webhook received empty message data")
        return {"status": "ok"}

    decoded_data = base64.b64decode(data).decode("utf-8")
    notification_data: dict[str, Any] = json.loads(decoded_data)

    email_address: str | None = notification_data.get("emailAddress")
    if not email_address:
        logger.warning("Gmail notification missing email address")
        return {"status": "ok"}

    history_id: int | None = notification_data.get("historyId")
    if not history_id:
        logger.warning("Gmail notification missing history ID")
        return {"status": "ok"}

    user = await User.filter(User.filters.by_any_email([email_address])).prefetch_related("email_aliases").first()
    if not user:
        logger.warning(f"Received Gmail notification for unknown user with email: {email_address}")
        return {"status": "ok"}
    gmail_account = await GmailAccount.get_or_none(user_id=user.id)
    if not gmail_account:
        logger.warning(f"Received Gmail notification for unknown email: {email_address}")
        return {"status": "ok"}

    logger.info(f"Received Gmail notification for {email_address}, history_id: {history_id}")
    await gmail_account.mark_push_received()
    await enqueue_job(
        ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=str(history_id), unique=True)
    )
    return {"status": "ok"}


#
# Google Calendar
#
#


@router.get("/integrations/google_calendar/login")
async def integrations_google_calendar_login(
    helpers: Helpers = Depends(get_helpers),
    current_user: User = Depends(get_current_user),
    recall_calendar_preference: RecallAICalendarPreferences = Query(RecallAICalendarPreferences.NONE),
):
    if current_user.authentication.is_microsoft:
        helpers.flash("Connecting a calendar is not supported for your sign-in method.", level=FlashLevel.ERROR)
        return await helpers.redirect_back_or(to=str(helpers.url_for("profile_edit")))

    redirect_url = str(helpers.url_for("integrations_recall_ai_google_calendar_auth"))
    recall_calendar_auth_token = await RecallAIClient()._calendar_auth(user_id=current_user.id)

    return_to = await helpers.redirect_from_request("return_to")
    return_to_url = absolute_url(return_to) if return_to else str(settings.base_url)

    url = google_calendar_auth_url(
        redirect_url=redirect_url,
        recall_calendar_auth_token=recall_calendar_auth_token["token"],
        success_url=return_to_url,
        recall_calendar_preference=recall_calendar_preference,
    )
    return helpers.redirect_to(url)
