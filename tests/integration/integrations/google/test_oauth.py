import contextlib
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from google.auth.exceptions import RefreshError

from app.models.accounts import OAuthToken
from config.enums import AuthenticationProvider
from integrations.google.helpers import gmail_oauth_error_handling
from integrations.google.oauth import (
    GOOGLE_GMAIL_SCOPES,
    GoogleOAuthReauthorizationRequiredError,
    get_gmail_credentials,
    revoke_google_oauth_token,
)
from tests.helpers.factories import create_gmail_account


@pytest.mark.vcr(record_mode="none")
@pytest.mark.asyncio
async def test_revoke_google_oauth_token_revokes_at_google():
    # No mock: VCR replays the recorded POST to Google's /revoke from the cassette, so this
    # exercises the real request and confirms a 200 passes raise_for_status without erroring.
    await revoke_google_oauth_token("tok-123")


@pytest.mark.asyncio
async def test_gmail_oauth_error_handling_marks_account_as_errored():
    """Test that the gmail_oauth_error_handling context manager properly handles reauth errors."""
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")

    # Verify initial state
    assert gmail_account.last_auth_errored_at is None
    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    assert GOOGLE_GMAIL_SCOPES[0] in token.scopes

    # Use the context manager and raise an error
    async with gmail_oauth_error_handling(user):
        raise GoogleOAuthReauthorizationRequiredError(user.id, RefreshError("invalid_scope: Bad Request"))

    # Refresh the models to see changes
    await gmail_account.refresh_from_db()
    await user.refresh_from_db()
    await user.fetch_related("oauth_tokens")

    # Verify the Gmail account was marked as requiring reauth
    assert gmail_account.last_auth_errored_at is not None
    assert gmail_account.last_auth_error is not None
    assert "invalid_scope" in gmail_account.last_auth_error

    # Verify Gmail scopes were removed from the OAuth token
    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    for scope in GOOGLE_GMAIL_SCOPES:
        assert scope not in token.scopes


@pytest.mark.asyncio
async def test_get_refreshed_google_credentials_skips_refresh_when_token_valid():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")

    current_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert current_token is not None
    original_access_token = current_token.access_token

    with patch("google.oauth2.credentials.Credentials.refresh") as refresh_mock:
        credentials = await get_gmail_credentials(user)

    refresh_mock.assert_not_called()
    assert credentials.token == original_access_token

    await current_token.refresh_from_db()
    assert current_token.access_token == original_access_token


@pytest.mark.asyncio
async def test_get_refreshed_google_credentials_missing_refresh_token_requires_reauth():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")

    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    await OAuthToken.filter(id=token.id).update(refresh_token=None, expires_at=datetime.now(UTC) - timedelta(hours=1))
    await token.refresh_from_db()

    # An expired token with no refresh token raises the typed reauth error rather than a
    # bare RefreshError the sync jobs' handler wouldn't recognize.
    with pytest.raises(GoogleOAuthReauthorizationRequiredError):
        await get_gmail_credentials(user)

    # Wrapped as the sync jobs invoke it, that error is swallowed (so the job completes
    # instead of failing and retrying) and the Gmail scopes are cleared so the account
    # drops out and the reconnect flow surfaces.
    async with gmail_oauth_error_handling(user):
        await get_gmail_credentials(user)

    await gmail_account.refresh_from_db()
    await user.refresh_from_db()
    await user.fetch_related("oauth_tokens")
    assert gmail_account.last_auth_errored_at is not None
    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    for scope in GOOGLE_GMAIL_SCOPES:
        assert scope not in token.scopes


@pytest.mark.asyncio
async def test_get_refreshed_google_credentials_refreshes_when_token_expired():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")

    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    token.expires_at = datetime.now(UTC) - timedelta(hours=1)
    await token.save(update_fields=["expires_at"])

    # The bare refresh Mock leaves the Credentials unpopulated, so the post-refresh
    # validation may raise; only the refresh call count is under test here.
    with patch("google.oauth2.credentials.Credentials.refresh") as refresh_mock:
        with contextlib.suppress(ValueError):
            await get_gmail_credentials(user)

    refresh_mock.assert_called_once()


@pytest.mark.asyncio
async def test_get_refreshed_google_credentials_refreshes_when_expiry_unknown():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")

    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    await OAuthToken.filter(id=token.id).update(expires_at=None)
    await token.refresh_from_db()

    # The bare refresh Mock leaves the Credentials unpopulated, so the post-refresh
    # validation may raise; only the refresh call count is under test here.
    with patch("google.oauth2.credentials.Credentials.refresh") as refresh_mock:
        with contextlib.suppress(ValueError):
            await get_gmail_credentials(user)

    refresh_mock.assert_called_once()
