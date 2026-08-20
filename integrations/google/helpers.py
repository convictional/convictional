from contextlib import asynccontextmanager

from fastapi import status
from googleapiclient.errors import HttpError

from app.models.accounts import User
from config.enums import AuthenticationProvider
from config.logging import logger
from infra.db import transaction
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES, GoogleOAuthReauthorizationRequiredError


def has_gmail_scope(user: User) -> bool:
    # Keyed on the Google token's scopes, not the sign-in provider: a Gmail connection can ride a
    # non-Google login (e.g. a dev/testing sign-in), and a non-Google user simply has no such token.
    google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    return bool(google_token and google_token.has_scopes(GOOGLE_GMAIL_SCOPES))


@asynccontextmanager
async def gmail_oauth_error_handling(user: User):
    """
    Context manager to handle Gmail OAuth authentication errors.

    Automatically marks Gmail account as errored and removes OAuth scopes
    when OAuth authentication fails, requiring user re-authorization.

    Args:
        user: The user performing Gmail operations

    Usage:
        gmail = get_gmail_api_client(user, gmail_account)
        async with gmail_oauth_error_handling(user):
            # Gmail API operations that may fail due to OAuth issues
            gmail.get_profile()
    """
    try:
        yield
    except (GoogleOAuthReauthorizationRequiredError, HttpError) as error:
        # Only handle OAuth-related errors (401 Unauthorized)
        if isinstance(error, HttpError) and error.status_code != status.HTTP_401_UNAUTHORIZED:
            raise

        async with transaction() as connection:
            # Mark Gmail account as errored if it exists
            gmail_account = await GmailAccount.get_or_none(user=user, using_db=connection)
            if gmail_account:
                await gmail_account.mark_as_requires_reauth(error, using_db=connection)

            # Remove OAuth scopes to trigger re-auth
            google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
            if google_token:
                await google_token.remove_scopes(GOOGLE_GMAIL_SCOPES, connection)

        # Log OAuth failure
        logger.warning("Gmail OAuth authentication failed, user needs to re-authorization")
