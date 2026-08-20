import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_superuser


@pytest.mark.asyncio
async def test_api_docs_endpoints_require_superuser(client: AppClient):
    await client.get_default_user()

    for path in ("/api/openapi.json", "/api/docs", "/api/redoc"):
        response = await client.get(path)
        assert response.status_code == status.HTTP_403_FORBIDDEN, path


@pytest.mark.asyncio
async def test_api_docs_endpoints_served_to_superuser(client: AppClient):
    superuser = await create_superuser()

    with client.current_user_as(superuser):
        schema = await client.get("/api/openapi.json")
        swagger = await client.get("/api/docs")
        redoc = await client.get("/api/redoc")

    assert schema.status_code == status.HTTP_200_OK
    body = schema.json()
    assert body["openapi"].startswith("3.")
    assert body["info"]["title"] == "Convictional API"
    # Schema is scoped to JSON API routes only; HTML web routes are excluded.
    assert body["paths"], "openapi schema should expose at least one /api/ route"
    assert all(path.startswith("/api/") for path in body["paths"]), body["paths"].keys()

    assert swagger.status_code == status.HTTP_200_OK
    assert "text/html" in swagger.headers["content-type"]
    assert "/api/openapi.json" in swagger.text

    assert redoc.status_code == status.HTTP_200_OK
    assert "text/html" in redoc.headers["content-type"]
    assert "/api/openapi.json" in redoc.text


@pytest.mark.asyncio
async def test_builtin_docs_routes_are_disabled(client: AppClient):
    superuser = await create_superuser()

    with client.current_user_as(superuser):
        for path in ("/docs", "/redoc", "/openapi.json"):
            response = await client.get(path)
            assert response.status_code == status.HTTP_404_NOT_FOUND, path
