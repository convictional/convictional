import pytest_asyncio

from app.models.accounts import OAuthToken, User
from config import settings
from config.enums import AuthenticationProvider
from config.settings import EmailClient, GmailAPIClient
from integrations.google.gmail import MockGmailAPIStateRegistry
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES


@pytest_asyncio.fixture
async def use_gmail_client():
    with settings.override():
        # Use Gmail email client (so SendEmailThroughGmailJob gets enqueued via router)
        # But use mock Gmail API client within that job
        settings.email_client = EmailClient.GMAIL
        settings.gmail_api_client = GmailAPIClient.MOCK
        yield


@pytest_asyncio.fixture
async def gmail_state(use_gmail_client):
    """Provides access to the mock Gmail API state for test setup"""
    MockGmailAPIStateRegistry.clear_state()
    return MockGmailAPIStateRegistry.get_state()


async def add_gmail_token_to_user(user: User) -> OAuthToken:
    """Helper to add a Google OAuth token with Gmail scopes to a user."""
    await user.fetch_related("oauth_tokens")

    # Check if user already has a Google token
    google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)

    if google_token:
        # Update existing Google token with Gmail scopes (and a refresh token, which a real
        # Gmail connection always has and get_authed_* now requires).
        existing_scopes = set(google_token.scope.split(" "))
        new_scopes = existing_scopes.union(GOOGLE_GMAIL_SCOPES)
        google_token.scope = " ".join(new_scopes)
        if not google_token.refresh_token:
            google_token.refresh_token = "fake-google-refresh-token"
        await google_token.save()
        return google_token

    # Create a new Google token with Gmail scopes. A real Gmail connection always has a refresh
    # token (the connect flow requests offline access), and get_authed_* requires one.
    google_token = await OAuthToken.create(
        user_id=user.id,
        provider=AuthenticationProvider.GOOGLE,
        client_id=f"google-client-{user.id}",
        access_token="fake-google-access-token",
        refresh_token="fake-google-refresh-token",
        scope=" ".join(GOOGLE_GMAIL_SCOPES),
    )
    await user.fetch_related("oauth_tokens")
    return google_token
