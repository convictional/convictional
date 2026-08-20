import pytest
from fastapi import status

from app.models.commands import QuickLink
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_api_quick_link_crud(client: AppClient):
    user = await client.get_default_user()

    create_response = await client.post(
        "/api/quick_links",
        json={"label": "My Link", "url": "https://example.com/foo", "open_in_new_tab": True},
    )
    assert create_response.status_code == status.HTTP_201_CREATED
    created = create_response.json()
    assert created["label"] == "My Link"
    assert created["url"] == "https://example.com/foo"
    assert created["open_in_new_tab"] is True
    quick_link_id = created["id"]

    quick_link = await QuickLink.get(id=quick_link_id)
    assert quick_link.owner_id == user.id

    show_response = await client.get(f"/api/quick_links/{quick_link_id}")
    assert show_response.status_code == status.HTTP_200_OK
    assert show_response.json() == created

    update_response = await client.patch(
        f"/api/quick_links/{quick_link_id}",
        json={"label": "Renamed", "url": "https://example.com/bar", "open_in_new_tab": False},
    )
    assert update_response.status_code == status.HTTP_200_OK
    updated = update_response.json()
    assert updated["label"] == "Renamed"
    assert updated["url"] == "https://example.com/bar"
    assert updated["open_in_new_tab"] is False

    delete_response = await client.delete(f"/api/quick_links/{quick_link_id}")
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT
    assert await QuickLink.get_or_none(id=quick_link_id) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    ["not-a-url", "javascript:alert(1)", "", "   ", "ftp://example.com"],
)
async def test_api_quick_link_rejects_invalid_url(client: AppClient, url: str):
    response = await client.post(
        "/api/quick_links",
        json={"label": "Bad", "url": url, "open_in_new_tab": False},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_api_quick_link_requires_owner(client: AppClient):
    owner = await client.get_default_user()
    other_user = await create_user(organization_id=owner.organization_id)

    quick_link = await QuickLink.create(
        label="Mine",
        url="https://example.com/mine",
        open_in_new_tab=False,
        owner_id=owner.id,
    )

    with client.current_user_as(other_user):
        show = await client.get(f"/api/quick_links/{quick_link.id}")
        assert show.status_code == status.HTTP_404_NOT_FOUND

        update = await client.patch(
            f"/api/quick_links/{quick_link.id}",
            json={"label": "Hijacked", "url": "https://example.com", "open_in_new_tab": False},
        )
        assert update.status_code == status.HTTP_404_NOT_FOUND

        delete = await client.delete(f"/api/quick_links/{quick_link.id}")
        assert delete.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_api_quick_link_requires_auth(client: AppClient):
    with client.logged_out():
        response = await client.post(
            "/api/quick_links",
            json={"label": "Anon", "url": "https://example.com", "open_in_new_tab": False},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
