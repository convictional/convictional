import pytest
from fastapi import status

from tests.helpers.app import AppClient


@pytest.mark.asyncio
async def test_settings_renders_island_shell(client: AppClient):
    await client.get_default_user()
    response = await client.get("/integrations/notion/settings")

    assert response.status_code == status.HTTP_200_OK
    # The HTML route now only renders the React island mount point; all mutation
    # and listing logic lives in integrations/notion/api.py.
    assert 'id="react-notion-settings"' in response.text


@pytest.mark.asyncio
async def test_settings_requires_auth(client: AppClient):
    with client.logged_out():
        response = await client.get("/integrations/notion/settings", follow_redirects=False)

    assert response.status_code in (
        status.HTTP_302_FOUND,
        status.HTTP_303_SEE_OTHER,
        status.HTTP_307_TEMPORARY_REDIRECT,
    )
