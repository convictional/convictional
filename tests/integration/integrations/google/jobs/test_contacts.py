import logging
from datetime import UTC, datetime, timedelta

import pytest

from app.models.accounts import OAuthToken
from config.enums import AuthenticationProvider, ContactsSyncStatus
from integrations.google.jobs.contacts import SyncGmailContactsJob
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from tests.helpers.factories import create_gmail_account


@pytest.mark.asyncio
async def test_sync_reports_revoked_grant_as_warning_not_exception(caplog):
    """A revoked/expired Google grant is an expected reauth condition, so the sync job logs a
    warning rather than logger.exception — the latter would report expected noise to Sentry."""
    gmail_account = await create_gmail_account()
    await gmail_account.fetch_related("user")
    user = gmail_account.user
    await user.fetch_related("oauth_tokens")

    # Expired token with no refresh token routes straight to reauth without any network call.
    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    await OAuthToken.filter(id=token.id).update(refresh_token=None, expires_at=datetime.now(UTC) - timedelta(hours=1))

    with caplog.at_level(logging.WARNING):
        await SyncGmailContactsJob(user_id=user.id).perform()

    # The expected condition must not surface as an error-level log (which Sentry reports).
    assert "Failed to sync Gmail contacts for user" not in caplog.text
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)
    assert "Gmail contacts sync needs reauth" in caplog.text

    # The account is still marked errored and gmail_oauth_error_handling drove the reauth bookkeeping.
    await gmail_account.refresh_from_db()
    await user.refresh_from_db()
    await user.fetch_related("oauth_tokens")
    assert gmail_account.contacts_sync_status == ContactsSyncStatus.ERROR
    assert gmail_account.last_auth_errored_at is not None
    token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
    assert token is not None
    for scope in GOOGLE_GMAIL_SCOPES:
        assert scope not in token.scopes
