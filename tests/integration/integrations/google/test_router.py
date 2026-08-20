import base64
import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import status

from app.models.accounts import User
from config import settings
from config.enums import AuthenticationProvider, Integration
from infra.oauth import Token
from tests.helpers.app import AppClient
from tests.helpers.factories import create_gmail_account


async def _microsoft_user() -> User:
    # Mint a user whose identity OAuthToken records the Microsoft provider so the
    # Google route gates can distinguish them from Google/testing logins.
    token = Token.fake("ms-gated@example.com")
    token.provider = AuthenticationProvider.MICROSOFT
    user, *_ = await User.get_or_create_by_oauth(token)
    await user.fetch_related("oauth_tokens", "organization")
    return user


@pytest.mark.asyncio
async def test_auth_google_redirects_through_oauth_proxy_when_configured(client: AppClient):
    proxy_base = "https://convictional-oauth-proxy-885382291938.us-central1.run.app"
    with settings.override():
        settings.oauth_proxy_url = proxy_base
        settings.google_oauth_client_id = "test-client-id"
        settings.enable_fake_auth = False

        with client.logged_out():
            response = await client.get("/auth/google", follow_redirects=False)

    location = response.headers["location"]
    params = parse_qs(urlparse(location).query)

    assert params["redirect_uri"] == [f"{proxy_base}/auth/google"]
    state = json.loads(base64.urlsafe_b64decode(params["state"][0]))
    assert state["origin"] == str(settings.base_url)


@pytest.mark.asyncio
async def test_google_integration_routes_gated_for_microsoft_users(client: AppClient):
    microsoft_user = await _microsoft_user()
    google_user = await client.get_default_user()

    # scenario: a Microsoft-login user cannot start the Gmail or Calendar OAuth
    # flows — both flash and redirect away without attaching an integration.
    with client.current_user_as(microsoft_user):
        gmail_response = await client.get("/integrations/gmail/auth", follow_redirects=False)
        assert gmail_response.status_code == status.HTTP_303_SEE_OTHER
        assert "login.microsoftonline.com" not in gmail_response.headers["location"]
        assert "accounts.google.com" not in gmail_response.headers["location"]

        calendar_response = await client.get("/integrations/google_calendar/login", follow_redirects=False)
        assert calendar_response.status_code == status.HTTP_303_SEE_OTHER
        assert "accounts.google.com" not in calendar_response.headers["location"]

    await microsoft_user.refresh_from_db()
    assert not microsoft_user.is_integrated_with(Integration.GMAIL)
    assert not microsoft_user.is_integrated_with(Integration.RECALL_AI_CALENDAR)

    # scenario: a Google (default) user still reaches Google's OAuth consent screen.
    with client.current_user_as(google_user):
        gmail_response = await client.get("/integrations/gmail/auth", follow_redirects=False)
        assert gmail_response.status_code == status.HTTP_303_SEE_OTHER
        assert "accounts.google.com" in gmail_response.headers["location"]


@pytest.mark.asyncio
async def test_gmail_webhook_records_push_received(client: AppClient):
    """The webhook stamps last_push_received_at on the first real-time notification — the liveness
    signal the health check uses to tell a working watch from a silently-dead one — but throttles
    the write so a burst of pushes doesn't issue a gmailaccount UPDATE each time."""
    user = await client.get_default_user()
    gmail_account = await create_gmail_account(history_id="100", user_id=user.id, email=user.email)
    assert gmail_account.last_push_received_at is None

    async def post_webhook(history_id: int):
        data = base64.b64encode(json.dumps({"emailAddress": user.email, "historyId": history_id}).encode()).decode()
        with settings.override():
            settings.enable_fake_auth = True
            response = await client.post("/integrations/gmail/webhook", json={"message": {"data": data}})
        assert response.status_code == status.HTTP_200_OK

    await post_webhook(200)
    await gmail_account.refresh_from_db()
    first_push_at = gmail_account.last_push_received_at
    assert first_push_at is not None

    # A second push moments later is throttled: the timestamp is recent enough that we skip the write.
    await post_webhook(300)
    await gmail_account.refresh_from_db()
    assert gmail_account.last_push_received_at == first_push_at
