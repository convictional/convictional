import base64
import json
from time import time
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from fastapi import status

from app.models.accounts import OAuthToken, User
from config import settings
from config.enums import AuthenticationProvider
from infra.oauth import FAKE_TOKEN_TTL, InvalidGrantError, Token
from tests.helpers.app import AppClient


def _microsoft_token(email: str) -> Token:
    # Token.fake() stamps provider=TESTING; IDToken.from_jwt doesn't verify the
    # signature and OAuthToken persists token.provider verbatim, so we override
    # the provider explicitly to mint a genuine Microsoft-provider token.
    token = Token.fake(email)
    token.provider = AuthenticationProvider.MICROSOFT
    return token


def _microsoft_token_without_email_claim(preferred_username: str) -> Token:
    # Microsoft Entra (work/school) accounts frequently omit the `email` claim
    # entirely and carry the address in `preferred_username` (the UPN). Token.fake
    # always sets `email`, so build the ID token by hand to reproduce that shape.
    now = int(time())
    id_token = jwt.encode(
        {
            "aud": "fake-client-id",
            "iat": now,
            "exp": now + FAKE_TOKEN_TTL,
            "iss": "https://login.microsoftonline.com/common/v2.0",
            "sub": "ms-entra-sub-no-email",
            "name": "Entra User",
            "preferred_username": preferred_username,
            "tid": "fake-tenant-id",
        },
        "fake-secret-key-for-testing-only!",
        algorithm="HS256",
    )
    return Token(
        provider=AuthenticationProvider.MICROSOFT,
        access_token="fake-access",
        token_type="Bearer",
        expires_in=3600,
        scope="openid email profile",
        id_token=id_token,
    )


async def _microsoft_user(email: str = "ms-user@example.com") -> User:
    user, *_ = await User.get_or_create_by_oauth(_microsoft_token(email))
    await user.fetch_related("oauth_tokens", "organization")
    return user


@pytest.mark.asyncio
async def test_auth_microsoft_login(client: AppClient):
    token = _microsoft_token("ms-login@example.com")

    with patch(
        "integrations.microsoft.oauth.MicrosoftAuthenticator.get_token",
        new=AsyncMock(return_value=token),
    ):
        with client.logged_out():
            response = await client.get("/auth/microsoft?code=test_code", follow_redirects=False)

    # scenario: a brand-new Microsoft user is created and lands in the mailbox
    assert response.status_code == status.HTTP_303_SEE_OTHER
    location = response.headers["location"]
    assert urlparse(location).path == "/"

    user = await User.get_or_none(email="ms-login@example.com").prefetch_related("oauth_tokens")
    assert user is not None

    # scenario: the persisted identity token records the Microsoft provider
    ms_token = user.oauth_token_for_provider(AuthenticationProvider.MICROSOFT)
    assert ms_token is not None
    assert ms_token.provider == AuthenticationProvider.MICROSOFT
    assert await OAuthToken.filter(user_id=user.id, provider=AuthenticationProvider.MICROSOFT).exists()


@pytest.mark.asyncio
async def test_auth_microsoft_login_falls_back_to_preferred_username_for_email(client: AppClient):
    # An Entra account whose ID token omits `email` and only carries the UPN in
    # `preferred_username` — the common work/school case that 400'd before the
    # IDToken fallback.
    token = _microsoft_token_without_email_claim("entra-upn@example.com")

    with patch(
        "integrations.microsoft.oauth.MicrosoftAuthenticator.get_token",
        new=AsyncMock(return_value=token),
    ):
        with client.logged_out():
            response = await client.get("/auth/microsoft?code=test_code", follow_redirects=False)

    # scenario: login succeeds (no "Email not found" 400) and the user is created
    # with the UPN as their email.
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert urlparse(response.headers["location"]).path == "/"

    user = await User.get_or_none(email="entra-upn@example.com")
    assert user is not None


@pytest.mark.asyncio
async def test_auth_microsoft_no_code_redirects_to_authorize_url(client: AppClient):
    with settings.override():
        settings.microsoft_oauth_client_id = "test-ms-client-id"
        settings.enable_fake_auth = False

        with client.logged_out():
            response = await client.get("/auth/microsoft", follow_redirects=False)

    # scenario: without a code we bounce the user to Microsoft's authorize endpoint
    assert response.status_code == status.HTTP_303_SEE_OTHER
    location = response.headers["location"]
    parsed = urlparse(location)
    assert parsed.netloc == "login.microsoftonline.com"

    params = parse_qs(parsed.query)
    assert params["client_id"] == ["test-ms-client-id"]
    assert "openid email profile" in params["scope"][0]
    assert params["redirect_uri"][0].endswith("/auth/microsoft")


@pytest.mark.asyncio
async def test_auth_microsoft_invalid_grant_flashes_and_redirects_to_login(client: AppClient):
    with patch(
        "integrations.microsoft.oauth.MicrosoftAuthenticator.get_token",
        new=AsyncMock(side_effect=InvalidGrantError("bad code")),
    ):
        with client.logged_out():
            response = await client.get("/auth/microsoft?code=bad_code", follow_redirects=False)

    # scenario: an invalid authorization code flashes an error and returns to login
    assert response.status_code == status.HTTP_303_SEE_OTHER
    assert "/login" in response.headers["location"]


@pytest.mark.asyncio
async def test_auth_microsoft_redirects_through_oauth_proxy_when_configured(client: AppClient):
    # oauth_proxy_url is the proxy base; each provider appends its own /auth/{provider}.
    proxy_base = "https://convictional-oauth-proxy-885382291938.us-central1.run.app"
    with settings.override():
        settings.oauth_proxy_url = proxy_base
        settings.microsoft_oauth_client_id = "test-ms-client-id"
        settings.enable_fake_auth = False

        with client.logged_out():
            response = await client.get("/auth/microsoft", follow_redirects=False)

    # scenario: with a proxy configured, the authorize URL targets the proxy's
    # Microsoft path and carries a base64 state encoding our true origin
    location = response.headers["location"]
    params = parse_qs(urlparse(location).query)

    assert params["redirect_uri"] == [f"{proxy_base}/auth/microsoft"]
    state = json.loads(base64.urlsafe_b64decode(params["state"][0]))
    assert state["origin"] == str(settings.base_url)
