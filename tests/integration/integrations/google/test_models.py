import pytest

from app.models.accounts import OAuthToken
from config.enums import AuthenticationProvider
from integrations.google.models import GmailAccount
from tests.helpers.factories import create_gmail_account


@pytest.mark.asyncio
async def test_get_authed_requires_refresh_token():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")
    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None

    # A scoped token with a refresh token is a usable connection.
    assert await GmailAccount.get_authed_for_user(user.id) is not None
    assert await GmailAccount.get_authed_by_id(gmail_account.id) is not None

    # Without a refresh token the connection can never be refreshed, so both accessors treat
    # it as unauthed — keeping such accounts out of the sync jobs instead of failing on refresh.
    await OAuthToken.filter(id=token.id).update(refresh_token=None)

    assert await GmailAccount.get_authed_for_user(user.id) is None
    assert await GmailAccount.get_authed_by_id(gmail_account.id) is None


@pytest.mark.asyncio
async def test_has_valid_gmail_oauth_filter_requires_refresh_token():
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")
    google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert google_token is not None

    # With a refresh token, the account passes the filter the sync jobs select on.
    selected = await GmailAccount.filter(GmailAccount.filters.has_valid_gmail_oauth()).values_list("id", flat=True)
    assert gmail_account.id in selected

    # Strip the refresh token from the Google token. The user still has another token (the
    # TESTING login token) that carries a refresh token, so this also guards that the filter's
    # refresh-token clause is scoped to the same Gmail-scoped token, not any token on the user.
    await OAuthToken.filter(id=google_token.id).update(refresh_token=None)

    selected = await GmailAccount.filter(GmailAccount.filters.has_valid_gmail_oauth()).values_list("id", flat=True)
    assert gmail_account.id not in selected
