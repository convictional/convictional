import pytest
from fastapi import status

from config.enums import Integration
from tests.helpers.app import AppClient


@pytest.mark.asyncio
async def test_inbox_progress_show_returns_setup_state(client: AppClient):
    user = await client.get_default_user()
    await user.mark_onboarding_mailbox_sync_started()

    response = await client.get("/api/inbox_progress")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body["is_onboarding_mailbox_sync_complete"] is False
    assert body["onboarding_mailbox_sync_started_at"] is not None
    assert body["has_gmail_integration"] is False
    assert body["has_calendar_integration"] is False


@pytest.mark.asyncio
async def test_inbox_progress_show_reports_integrations(client: AppClient):
    user = await client.get_default_user()
    await user.add_integration(Integration.GMAIL)
    await user.add_integration(Integration.RECALL_AI_CALENDAR)
    await user.mark_onboarding_mailbox_sync_complete()

    response = await client.get("/api/inbox_progress")
    body = response.json()

    assert body["has_gmail_integration"] is True
    assert body["has_calendar_integration"] is True
    assert body["is_onboarding_mailbox_sync_complete"] is True
