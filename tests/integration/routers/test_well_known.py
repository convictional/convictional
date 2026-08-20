import pytest
from fastapi import status
from fastapi.routing import APIRoute, iter_route_contexts

from app.main import app
from app.routers.well_known import APPLE_APP_SITE_ASSOCIATION_PATHS
from config import settings
from tests.helpers.app import AppClient


def _matches_some_route(aasa_path: str, route_paths: set[str]) -> bool:
    # AASA glob `/foo/*` matches when at least one registered route starts
    # with `/foo/`. AASA exact-match `/foo` requires `/foo` to be registered
    # as-is. Anything else is stale.
    if aasa_path.endswith("/*"):
        prefix = aasa_path[:-1]
        return any(rp.startswith(prefix) for rp in route_paths)
    return aasa_path in route_paths


@pytest.mark.asyncio
async def test_aasa_returns_404_when_team_id_unset(client: AppClient):
    # `apple_team_id` defaults to "" in `config/settings.py`. When unset, the
    # handler must return 404 so iOS swcd treats the domain as having no
    # association — anything else (e.g., serving an `appID` of
    # `.com.convictional.app`) would let iOS attempt to bind a malformed
    # association. Pin the default so a future `Field(default=...)` change
    # doesn't silently break this contract.
    with settings.override():
        settings.apple_team_id = ""
        response = await client.get("/.well-known/apple-app-site-association")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_aasa_returns_signed_payload_when_configured(client: AppClient):
    with settings.override():
        settings.apple_team_id = "ABCDE12345"
        settings.ios_bundle_id = "com.convictional.app"
        response = await client.get("/.well-known/apple-app-site-association")

    assert response.status_code == status.HTTP_200_OK
    assert response.headers["content-type"].startswith("application/json")
    body = response.json()
    details = body["applinks"]["details"]
    assert len(details) == 1
    assert details[0]["appID"] == "ABCDE12345.com.convictional.app"
    # The allowlist must cover the primary user-tappable resources and exclude
    # apex paths that intentionally fall through to Safari (`/`, `/login`,
    # `/policies/*`). If either invariant changes, the AASA list and these
    # assertions move together.
    paths = details[0]["paths"]
    assert "/email_threads/*" in paths
    assert "/posts/*" in paths
    assert "/goals/*" in paths
    assert "/gid/*" in paths
    assert "/" not in paths
    assert "/login" not in paths
    assert not any(p.startswith("/policies") for p in paths)


def test_aasa_paths_correspond_to_registered_routes():
    # Every AASA-allowlisted path must map to at least one registered FastAPI
    # GET route. Catches the rename-breaks-AASA case: if `/posts` is renamed
    # to `/articles`, this test flags that AASA still lists `/posts/*` while
    # production routing has moved on.
    #
    # Does NOT catch the inverse — a new route added without an AASA entry —
    # because not every new route should be a Universal Link (admin pages,
    # internal redirects, JSON-only endpoints). That direction is a judgment
    # call kept in the human review loop.
    # app.routes nests included routers as opaque wrappers; iter_route_contexts
    # descends them to the real, prefix-joined routes.
    get_route_paths = {
        ctx.path
        for ctx in iter_route_contexts(app.routes)
        if isinstance(ctx.original_route, APIRoute) and ctx.path and "GET" in (ctx.methods or set())
    }
    stale = [path for path in APPLE_APP_SITE_ASSOCIATION_PATHS if not _matches_some_route(path, get_route_paths)]
    assert not stale, (
        f"AASA paths with no matching GET route: {stale}. "
        "Either the route was renamed/removed (drop the AASA entry) or the "
        "entry was a typo (fix it)."
    )
