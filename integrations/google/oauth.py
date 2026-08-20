import asyncio
from uuid import UUID

import httpx
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.models.accounts import User
from config import logger, settings
from config.enums import AuthenticationProvider
from infra.oauth import OAuthAuthenticator

GOOGLE_DEFAULT_SCOPES = ["openid", "email", "profile", "https://www.googleapis.com/auth/user.emails.read"]
GOOGLE_GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/contacts.readonly",
    "https://www.googleapis.com/auth/contacts.other.readonly",
]
GOOGLE_OAUTH_TOKEN_URI = "https://oauth2.googleapis.com/token"
GOOGLE_OAUTH_REVOKE_URI = "https://oauth2.googleapis.com/revoke"
# `unauthorized_client` is returned when a refresh token cannot be exchanged by
# the client presenting it (e.g. a token minted for a different OAuth client) —
# it is unusable and only re-authorization can recover it.
REAUTH_REQUIRED_ERRORS = {"invalid_grant", "invalid_scope", "unauthorized_client"}


def is_reauth_required_error(error: RefreshError) -> bool:
    """Check if a RefreshError requires user re-authorization."""
    return any(err in str(error) for err in REAUTH_REQUIRED_ERRORS)


class GoogleAuthenticator(OAuthAuthenticator):
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    default_scopes = GOOGLE_DEFAULT_SCOPES

    def __init__(self, redirect_uri: str):
        self.provider = AuthenticationProvider.GOOGLE
        self.client_id = settings.google_oauth_client_id
        self.client_secret = settings.google_oauth_client_secret.get_secret_value()
        self.redirect_uri = redirect_uri


class GoogleOAuthReauthorizationRequiredError(Exception):
    """Raised when Google OAuth credentials require user re-authorization."""

    def __init__(self, user_id: UUID, original_error: Exception):
        self.user_id = user_id
        self.original_error = original_error
        super().__init__(f"OAuth credentials require user re-authorization, user_id={user_id}, error={original_error}")


async def get_refreshed_google_credentials(user: User, token_uri: str):
    current_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    if not current_token:
        raise ValueError("User does not have a Google OAuth token")

    credentials = Credentials(
        token=current_token.access_token,
        refresh_token=current_token.refresh_token,
        token_uri=token_uri,
        client_id=settings.google_oauth_client_id,
        client_secret=settings.google_oauth_client_secret.get_secret_value(),
        scopes=current_token.scopes,
        expiry=current_token.credentials_expiry,
    )

    if not current_token.is_expired:
        return credentials

    # google-auth raises a bare RefreshError for a missing refresh token that is_reauth_required_error
    # won't recognize, causing indefinite job retries; route to reauth to force a true Gmail reconnection.
    if not current_token.refresh_token:
        raise GoogleOAuthReauthorizationRequiredError(user.id, RefreshError("missing refresh token"))

    try:
        await asyncio.to_thread(credentials.refresh, Request())
    except RefreshError as e:
        if not is_reauth_required_error(e):
            raise

        await user.refresh_from_db()
        await user.fetch_related("oauth_tokens")
        refreshed_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
        if refreshed_token and refreshed_token.refresh_token != current_token.refresh_token:
            credentials = Credentials(
                token=refreshed_token.access_token,
                refresh_token=refreshed_token.refresh_token,
                token_uri=token_uri,
                client_id=settings.google_oauth_client_id,
                client_secret=settings.google_oauth_client_secret.get_secret_value(),
                scopes=current_token.scopes,
            )
            try:
                await asyncio.to_thread(credentials.refresh, Request())
            except RefreshError as retry_error:
                if is_reauth_required_error(retry_error):
                    logger.warning("OAuth credentials invalid after retry, requires re-authorization")
                    raise GoogleOAuthReauthorizationRequiredError(user.id, retry_error) from retry_error
                raise
        else:
            # No new refresh token available, credentials are truly invalid
            logger.warning("No valid refresh token available for user, requires re-authorization")
            raise GoogleOAuthReauthorizationRequiredError(user.id, e) from e

    if not credentials.token or not credentials.expiry:
        raise ValueError("Credentials missing token or expiry after refresh")

    refresh_token_to_use = credentials.refresh_token if credentials.refresh_token else current_token.refresh_token
    if not refresh_token_to_use:
        raise ValueError("No refresh token available")

    await current_token.refresh(credentials.token, refresh_token_to_use, credentials.expiry)

    return credentials


async def get_gmail_credentials(user: User):
    return await get_refreshed_google_credentials(user, GOOGLE_OAUTH_TOKEN_URI)


async def revoke_google_oauth_token(token: str) -> None:
    """Revoke a Google OAuth grant at Google. The token may be a refresh or access token;
    revoking either invalidates the whole grant, so a later login can't silently resurrect
    the connection via include_granted_scopes (deleting our rows alone leaves the grant
    alive). Raises on transport/HTTP errors — callers should log and swallow, since a failed
    revoke must not block user deletion."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(GOOGLE_OAUTH_REVOKE_URI, data={"token": token})
        response.raise_for_status()
