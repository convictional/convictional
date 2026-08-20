import pytest

from tests.helpers.app import AppClient


@pytest.mark.asyncio
async def test_home_route(client: AppClient):
    user = await client.get_default_user()
    response = await client.get("/")
    assert user.display_name in response.text
