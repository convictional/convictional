import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal


@pytest.mark.asyncio
async def test_show_renders_react_island(client: AppClient):
    """The standalone route renders the React island mount point. The section's
    UI (schedule, goal-update question, enabled badge) is now client-rendered;
    the island fetches its state from /api/organization/updates_configuration."""
    user = await client.get_default_user()
    await user.make_admin()
    await create_goal(organization_id=user.organization_id, creator_id=user.id)

    response = await client.get("/organization/updates_configuration")

    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-organization-updates-configuration"' in response.text
