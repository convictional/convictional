import pytest

from config.enums import Integration
from infra.jobs import JobsOutbox
from integrations.google.gmail import MockGmailAPIState
from integrations.google.jobs.gmail import ReconnectGmailAccountJob
from integrations.google.models import GmailAccount
from tests.helpers.app import AppClient
from tests.integration.integrations.google.conftest import add_gmail_token_to_user


@pytest.mark.asyncio
async def test_reconnect_gmail_account_unchanged_email(client: AppClient, gmail_state: MockGmailAPIState):
    """Test Gmail account reconnection with unchanged email address"""
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_state.create_profile_by_email(user.email)

    gmail_account = await GmailAccount.create(
        user=user, email=user.email, history_id="123", last_sync_at=None, watch_expires_at=None
    )

    async with JobsOutbox():
        job = ReconnectGmailAccountJob(user_id=user.id)
        await job.perform()

    await gmail_account.refresh_from_db()
    assert gmail_account.email == user.email
    assert gmail_account.last_auth_errored_at is None


@pytest.mark.asyncio
async def test_reconnect_gmail_account_changed_email(client: AppClient, gmail_state: MockGmailAPIState):
    """Test Gmail account reconnection with changed email address"""
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    old_email = "old-email@example.com"
    new_email = "new-email@example.com"

    # Create profile with old email first so MockGoogleAPIClient can find it
    gmail_state.create_profile_by_email(old_email)

    gmail_account = await GmailAccount.create(
        user=user, email=old_email, history_id="123", last_sync_at=None, watch_expires_at=None
    )

    # Update user email to old email to simulate it being out of sync
    user.email = old_email
    await user.save(update_fields=["email"])

    # Update the profile to new email to simulate email address change
    gmail_state.profiles[old_email]["emailAddress"] = new_email

    async with JobsOutbox():
        job = ReconnectGmailAccountJob(user_id=user.id)
        await job.perform()

    await gmail_account.refresh_from_db()
    await user.refresh_from_db()
    assert gmail_account.email == new_email
    assert user.email == new_email


@pytest.mark.asyncio
async def test_reconnect_gmail_account_clears_auth_error(client: AppClient, gmail_state: MockGmailAPIState):
    """Test that reconnection clears previous auth errors"""
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_state.create_profile_by_email(user.email)

    gmail_account = await GmailAccount.create(
        user=user, email=user.email, history_id="123", last_sync_at=None, watch_expires_at=None
    )

    await gmail_account.mark_as_requires_reauth(Exception("Test error"))
    await gmail_account.save()
    assert gmail_account.last_auth_errored_at is not None

    async with JobsOutbox():
        job = ReconnectGmailAccountJob(user_id=user.id)
        await job.perform()

    await gmail_account.refresh_from_db()
    assert gmail_account.last_auth_errored_at is None
    assert gmail_account.last_auth_error is None
