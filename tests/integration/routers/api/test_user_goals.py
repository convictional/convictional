import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_user


@pytest.mark.asyncio
async def test_top_goal_returns_null_when_user_has_no_goals(client: AppClient):
    user = await client.get_default_user()
    response = await client.get(f"/api/users/{user.id}/top_goal")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"top_goal": None}


@pytest.mark.asyncio
async def test_top_goal_returns_highest_priority_owned_goal(client: AppClient):
    user = await client.get_default_user()
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="First goal",
        owner_id=user.id,
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Second goal",
        owner_id=user.id,
    )

    response = await client.get(f"/api/users/{user.id}/top_goal")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["top_goal"] is not None
    assert body["top_goal"]["description"] in {"First goal", "Second goal"}


@pytest.mark.asyncio
async def test_top_goal_targets_named_user(client: AppClient):
    me = await client.get_default_user()
    other = await create_user(organization_id=me.organization_id)
    await create_goal(
        organization_id=me.organization_id,
        creator_id=me.id,
        description="My goal",
        owner_id=me.id,
    )
    other_goal = await create_goal(
        organization_id=me.organization_id,
        creator_id=me.id,
        description="Other's goal",
        owner_id=other.id,
    )

    response = await client.get(f"/api/users/{other.id}/top_goal")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["top_goal"]["id"] == str(other_goal.id)


@pytest.mark.asyncio
async def test_top_goal_supports_parent_expand(client: AppClient):
    user = await client.get_default_user()
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent")
    child = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Child",
        owner_id=user.id,
        parent_id=parent.id,
    )

    # Without ?expand=parent, parent is null even though parent_id is set
    response = await client.get(f"/api/users/{user.id}/top_goal")
    body = response.json()
    assert body["top_goal"]["id"] == str(child.id)
    assert body["top_goal"]["parent_id"] == str(parent.id)
    assert body["top_goal"]["parent"] is None

    # With ?expand=parent, the parent summary is hydrated
    response = await client.get(f"/api/users/{user.id}/top_goal?expand=parent")
    body = response.json()
    assert body["top_goal"]["parent"]["id"] == str(parent.id)
