import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_group,
    create_group_member,
    create_user,
)


@pytest.mark.asyncio
async def test_api_people_show_returns_user_and_groups(client: AppClient):
    me = await create_user(email="viewer@convictional.com")
    other = await create_user(
        name="Other Person",
        email="other@convictional.com",
        organization_id=me.organization_id,
        bio="hello world",
        is_admin=True,
    )
    group = await create_group(name="Engineering", organization_id=me.organization_id)
    await create_group_member(group_id=group.id, user_id=other.id)

    with client.current_user_as(me):
        response = await client.get(f"/api/people/{other.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user"]["id"] == str(other.id)
    assert data["user"]["display_name"] == "Other Person"
    assert data["user"]["email"] == "other@convictional.com"
    assert data["user"]["bio"] == "hello world"
    assert data["user"]["is_admin"] is True
    assert [g["name"] for g in data["groups"]] == ["Engineering"]
    # Card-only fields are gone; clients compute is_current_user themselves
    # and fetch the top goal separately via /api/users/{id}/top_goal.
    assert "is_current_user" not in data
    assert "goal" not in data
    assert "extra_goal_count" not in data


@pytest.mark.asyncio
async def test_api_people_show_for_self(client: AppClient):
    me = await create_user(email="self-show@convictional.com", bio="me")

    with client.current_user_as(me):
        response = await client.get(f"/api/people/{me.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user"]["id"] == str(me.id)
    assert data["user"]["bio"] == "me"


@pytest.mark.asyncio
async def test_api_people_show_other_organization_is_not_found(client: AppClient):
    me = await create_user(email="org-a@convictional.com")
    outsider = await create_user(email="org-b@convictional.com")

    with client.current_user_as(me):
        response = await client.get(f"/api/people/{outsider.id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
