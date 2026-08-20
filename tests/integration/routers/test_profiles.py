import pytest
from fastapi import status

from config import settings
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_user_avatar_route_reachable_by_non_admins(client: AppClient):
    # Regression: the avatar route previously lived on users.router, which is
    # gated by get_admin_user — non-admins viewing a teammate's avatar got 403.
    viewer = await client.get_default_user()
    assert not viewer.is_admin

    teammate = await create_user(organization_id=viewer.organization_id)
    teammate.oauth_picture = "https://oauth.example/teammate.jpg"
    await teammate.save()

    client.follow_redirects = False
    response = await client.get(f"/profile/{teammate.id}/avatar")
    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "https://oauth.example/teammate.jpg"


@pytest.mark.asyncio
async def test_user_avatar_unauthenticated_with_fake_auth_enabled(client: AppClient):
    # The /login fake-login picker renders avatars for users in every org while
    # the visitor is logged out; the avatar endpoint has to serve those requests.
    target = await create_user()
    target.oauth_picture = "https://oauth.example/fake-login-target.jpg"
    await target.save()

    client.follow_redirects = False
    with settings.override():
        settings.enable_fake_auth = True
        with client.logged_out():
            response = await client.get(f"/profile/{target.id}/avatar")

    assert response.status_code == status.HTTP_302_FOUND
    assert response.headers["location"] == "https://oauth.example/fake-login-target.jpg"


@pytest.mark.asyncio
async def test_user_avatar_unauthenticated_without_fake_auth_redirects_to_login(client: AppClient):
    target = await create_user()

    client.follow_redirects = False
    with settings.override():
        settings.enable_fake_auth = False
        with client.logged_out():
            response = await client.get(f"/profile/{target.id}/avatar")

    assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
    assert response.headers["location"].endswith("/login")


@pytest.mark.asyncio
async def test_user_avatar_cross_org_returns_404(client: AppClient):
    # Authenticated callers must still be confined to their own organization.
    await client.get_default_user()
    outsider = await create_user()
    outsider.oauth_picture = "https://oauth.example/outsider.jpg"
    await outsider.save()

    response = await client.get(f"/profile/{outsider.id}/avatar")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# /profile/edit renders only the React island, so the timezone dropdown (and its
# browser-tz/uncurated-zone preselect) is exercised in the React TimezoneSection
# tests — tests/javascript/react/features/userSettings/UserSettings.test.tsx —
# not here.
