import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_index_mounts_react_island(client: AppClient):
    # The /groups index is a React island shell. The only server-rendered bit is
    # the mount point plus the canManage bootstrap prop (admin status).
    admin = await client.get_default_user()
    await admin.make_admin()

    response = await client.get("/groups")
    assert response.status_code == status.HTTP_200_OK
    assert 'id="react-groups-index"' in response.text
    # data-props is HTML-escaped by tojson, so the quotes render as &#34;.
    assert "canManage&#34;: true" in response.text

    # Non-admins get canManage=false (the API re-gates authoritatively).
    non_admin = await create_user(organization_id=admin.organization_id)
    with client.current_user_as(non_admin):
        response = await client.get("/groups")
        assert response.status_code == status.HTTP_200_OK
        assert "canManage&#34;: false" in response.text

    # The shell requires auth: an anonymous request redirects to login rather
    # than 500ing on `current_user.is_admin` in the template.
    with client.logged_out():
        response = await client.get("/groups", follow_redirects=False)
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        assert response.headers["location"].endswith("/login")
