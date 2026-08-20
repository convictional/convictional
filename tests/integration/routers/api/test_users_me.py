import pytest
from fastapi import status

from config.settings import settings
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_users_me_returns_identity_and_bootstrap(client: AppClient):
    user = await client.get_default_user()
    await user.fetch_related("organization")
    settings.klipy_api_key = "test-key"

    response = await client.get("/api/users/me")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body["id"] == str(user.id)
    assert body["display_name"] == user.display_name
    assert body["is_admin"] == user.is_admin
    assert "picture" in body
    assert body["client_config"] == {"klipy_api_key": "test-key"}

    # Bootstrap fields consumed by the React AppShell.
    assert body["is_admin"] == user.is_admin
    assert body["organization_id"] == str(user.organization_id)
    assert body["organization_name"] == user.organization.name
    assert body["time_zone"] == user.time_zone
    assert body["feedback_upload_url"].endswith("/api/workspaces/attachments")
    # No server flashes pending on a plain GET; the field is always present.
    assert body["flashes"] == []


@pytest.mark.asyncio
async def test_users_me_returns_null_klipy_when_unset(client: AppClient):
    settings.klipy_api_key = ""

    response = await client.get("/api/users/me")
    assert response.json()["client_config"]["klipy_api_key"] is None


@pytest.mark.asyncio
async def test_users_me_reflects_admin_state(client: AppClient):
    admin = await create_user(is_admin=True)
    with client.current_user_as(admin):
        body = (await client.get("/api/users/me")).json()
        assert body["is_admin"] is True

    member = await create_user(is_admin=False)
    with client.current_user_as(member):
        body = (await client.get("/api/users/me")).json()
        assert body["is_admin"] is False


@pytest.mark.asyncio
async def test_users_me_drains_and_clears_pending_session_flashes(client: AppClient):
    client.seed_session(flashes=[{"content": "Saved your changes", "level": "success"}])

    first = (await client.get("/api/users/me")).json()
    assert first["flashes"] == [{"content": "Saved your changes", "level": "success"}]

    # Draining clears the session, so a second fetch sees nothing — flashes show
    # exactly once.
    second = (await client.get("/api/users/me")).json()
    assert second["flashes"] == []


@pytest.mark.asyncio
async def test_users_me_unauthenticated_returns_401(client: AppClient):
    with client.logged_out():
        response = await client.get("/api/users/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
