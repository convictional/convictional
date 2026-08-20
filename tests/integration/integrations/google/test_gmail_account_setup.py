import pytest

from config.enums import Integration
from infra.jobs import JobsOutbox
from integrations.google.gmail import MockGmailAPIState
from integrations.google.jobs.gmail import SetupGmailAccountJob
from integrations.google.models import GmailAccount
from tests.helpers.app import AppClient
from tests.integration.integrations.google.conftest import add_gmail_token_to_user


@pytest.mark.asyncio
async def test_gmail_account_setup(client: AppClient, gmail_state: MockGmailAPIState):
    """Test Gmail account setup job"""
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    gmail_state.create_profile_by_email(user.email)

    # Run Gmail account setup job to import all messages
    async with JobsOutbox():
        setup_job = SetupGmailAccountJob(user_id=user.id)
        await setup_job.perform()

    # Verify onboarding sync completed successfully
    gmail_account = await GmailAccount.get_or_none(user_id=user.id)
    assert gmail_account is not None
    assert gmail_account.onboarding_mailbox_sync_started_at is not None
    assert gmail_account.onboarding_mailbox_sync_completed_at is not None


@pytest.mark.asyncio
async def test_gmail_account_setup_when_gmail_unavailable(client: AppClient, gmail_state: MockGmailAPIState):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await add_gmail_token_to_user(user)

    async with JobsOutbox():
        await SetupGmailAccountJob(user_id=user.id).perform()

    await user.refresh_from_db()
    assert not user.is_integrated_with(Integration.GMAIL)
    assert user.is_onboarding_mailbox_sync_complete
    assert await GmailAccount.get_or_none(user_id=user.id) is None
