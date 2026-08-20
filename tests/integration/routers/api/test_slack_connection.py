import pytest
from fastapi import status

from app.models.accounts import User
from config.enums import Integration
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_slack_connection_get(client: AppClient):
    user = await client.get_default_user()

    response = await client.get("/api/integrations/slack/connection")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "unavailable"}

    # Once anyone in the org has Slack, the app is installed → this user can connect.
    other = await create_user(organization_id=user.organization_id, integrations=[Integration.SLACK])
    body = (await client.get("/api/integrations/slack/connection")).json()
    assert body == {"status": "disconnected"}

    # A soft-deleted member's install does not count.
    await other.soft_delete()
    body = (await client.get("/api/integrations/slack/connection")).json()
    assert body == {"status": "unavailable"}

    # Connecting this user reports connected.
    await user.add_integration(Integration.SLACK)
    body = (await client.get("/api/integrations/slack/connection")).json()
    assert body == {"status": "connected"}


@pytest.mark.asyncio
async def test_slack_connection_delete(client: AppClient):
    user = await client.get_default_user()
    await user.add_integration(Integration.SLACK)
    assert user.is_integrated_with(Integration.SLACK)

    response = await client.delete("/api/integrations/slack/connection")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    user = await User.get(id=user.id)
    assert not user.is_integrated_with(Integration.SLACK)

    # Idempotent: disconnecting again is still a 204.
    assert (await client.delete("/api/integrations/slack/connection")).status_code == status.HTTP_204_NO_CONTENT
