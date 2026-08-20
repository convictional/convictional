import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal


@pytest.mark.asyncio
async def test_subscription_get_and_toggle(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test goal")

    # GET returns effective state. No explicit row yet — is_explicit is False.
    response = await client.get(f"/api/workspaces/{goal.workspace_id}/subscription")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_explicit"] is False

    # PATCH to subscribe → explicit row.
    response = await client.patch(
        f"/api/workspaces/{goal.workspace_id}/subscription",
        json={"level": "all"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"wants_all": True, "is_explicit": True}

    # PATCH to unsubscribe.
    response = await client.patch(
        f"/api/workspaces/{goal.workspace_id}/subscription",
        json={"level": "relevant_only"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"wants_all": False, "is_explicit": True}


@pytest.mark.asyncio
async def test_subscription_delete_returns_to_fallback(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test goal")

    # Create an explicit row.
    await client.patch(
        f"/api/workspaces/{goal.workspace_id}/subscription",
        json={"level": "relevant_only"},
    )

    # DELETE removes the row, returning 204 No Content.
    response = await client.delete(f"/api/workspaces/{goal.workspace_id}/subscription")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    # A follow-up GET reads the resolved fallback state.
    response = await client.get(f"/api/workspaces/{goal.workspace_id}/subscription")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_explicit"] is False


@pytest.mark.asyncio
async def test_goal_response_includes_workspace_id(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test goal")

    response = await client.get("/api/goals")
    assert response.status_code == status.HTTP_200_OK
    goal_data = response.json()["goals"][0]
    assert "workspace_id" in goal_data
    assert goal_data["workspace_id"] == str(goal.workspace_id)
