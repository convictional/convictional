import pytest
from fastapi import status

from app.models.accounts import OAuthToken, User
from config.enums import AuthenticationProvider, Integration
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from tests.helpers.app import AppClient
from tests.helpers.factories import create_gmail_account


async def _add_google_token(user: User, *, with_gmail_scopes: bool) -> OAuthToken:
    return await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.GOOGLE,
        client_id=f"google-client-{user.id}",
        access_token="fake-google-access-token",
        scope=" ".join(GOOGLE_GMAIL_SCOPES) if with_gmail_scopes else "",
    )


@pytest.mark.asyncio
async def test_gmail_connection_get(client: AppClient):
    user = await client.get_default_user()

    # A non-Google (testing) user can't connect Gmail at all. requires_reauth stays
    # False throughout: this user never had the GMAIL integration, so missing scopes
    # just means never-connected, never a reconnect.
    response = await client.get("/api/integrations/gmail/connection")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "unavailable", "requires_reauth": False}

    # Google-authed but no Gmail scopes yet → connectable, not connected.
    token = await _add_google_token(user, with_gmail_scopes=False)
    body = (await client.get("/api/integrations/gmail/connection")).json()
    assert body == {"status": "disconnected", "requires_reauth": False}

    # Once the Gmail scopes are present, it reads as connected.
    token.scope = " ".join(GOOGLE_GMAIL_SCOPES)
    await token.save()
    body = (await client.get("/api/integrations/gmail/connection")).json()
    assert body == {"status": "connected", "requires_reauth": False}


@pytest.mark.asyncio
async def test_gmail_connection_requires_reauth(client: AppClient):
    # requires_reauth is what the mailbox reauth badge keys off: the GMAIL integration
    # is set (so the user *was* connected) but the Google token has lost the Gmail
    # scopes. Distinct from a never-connected user, who also reads as "disconnected"
    # but must get no reconnect nag.
    user = await client.get_default_user()
    token = await _add_google_token(user, with_gmail_scopes=True)
    await user.add_integration(Integration.GMAIL)

    body = (await client.get("/api/integrations/gmail/connection")).json()
    assert body == {"status": "connected", "requires_reauth": False}

    # An auth error strips the Gmail scopes but keeps the integration — the genuine
    # reconnect case.
    token.scope = ""
    await token.save()
    body = (await client.get("/api/integrations/gmail/connection")).json()
    assert body == {"status": "disconnected", "requires_reauth": True}


@pytest.mark.asyncio
async def test_gmail_connection_delete(client: AppClient):
    user = await client.get_default_user()
    await _add_google_token(user, with_gmail_scopes=True)
    await create_gmail_account(user_id=user.id, email=user.email)
    await user.add_integration(Integration.GMAIL)
    assert await GmailAccount.filter(user_id=user.id).exists()

    response = await client.delete("/api/integrations/gmail/connection")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    user = await User.get(id=user.id).prefetch_related("oauth_tokens")
    assert not user.is_integrated_with(Integration.GMAIL)
    assert not await GmailAccount.filter(user_id=user.id).exists()
    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None and not token.has_scopes(GOOGLE_GMAIL_SCOPES)

    # Idempotent: disconnecting again is still a 204.
    assert (await client.delete("/api/integrations/gmail/connection")).status_code == status.HTTP_204_NO_CONTENT
