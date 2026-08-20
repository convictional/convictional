import pytest
from fastapi import status

from app.models.collaboration.workspace import Visit
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_group, create_post, create_user


@pytest.mark.asyncio
async def test_views_returns_envelope_for_creator(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.get(f"/api/posts/{post.id}/views")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    expected_keys = {
        "seen_count",
        "total_audience",
        "first_seen_at",
        "last_seen_at",
        "group",
        "views",
    }
    assert expected_keys.issubset(body.keys())
    assert body["group"] is None  # ungrouped post
    assert isinstance(body["views"], list)
    assert all({"window_start", "count"} == set(entry.keys()) for entry in body["views"])


@pytest.mark.asyncio
async def test_views_counts_visits(client: AppClient):
    creator = await client.get_default_user()
    other = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await Visit.record(other.id, post.workspace_id)

    response = await client.get(f"/api/posts/{post.id}/views")
    body = response.json()
    assert body["seen_count"] == 1
    assert body["first_seen_at"] is not None
    assert body["last_seen_at"] is not None


@pytest.mark.asyncio
async def test_views_group_breakdown(client: AppClient):
    creator = await client.get_default_user()
    group = await create_group(name="Engineering", organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, group_id=group.id)

    response = await client.get(f"/api/posts/{post.id}/views")
    body = response.json()
    assert body["group"] is not None
    assert body["group"]["id"] == str(group.id)
    assert body["group"]["name"] == "Engineering"
    assert "seen_count" in body["group"]
    assert "total_audience" in body["group"]


@pytest.mark.asyncio
async def test_views_admin_access(client: AppClient):
    creator = await client.get_default_user()
    admin = await create_user(organization_id=creator.organization_id, is_admin=True)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    with client.current_user_as(admin):
        response = await client.get(f"/api/posts/{post.id}/views")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_views_forbidden_for_other_users(client: AppClient):
    creator = await client.get_default_user()
    viewer = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=creator.id, user_id=viewer.id)

    with client.current_user_as(viewer):
        response = await client.get(f"/api/posts/{post.id}/views")
        assert response.status_code == status.HTTP_403_FORBIDDEN
