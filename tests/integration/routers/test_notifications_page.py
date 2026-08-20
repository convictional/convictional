import re

import pytest
from bs4 import BeautifulSoup
from fastapi import status

from tests.helpers.app import AppClient


def _module_script_srcs(html: str) -> list[str]:
    # Matches both the raw entry path (no manifest) and the hashed build path
    # (manifest present), so assertions don't depend on whether `make assets` ran.
    soup = BeautifulSoup(html, "html.parser")
    return [src for tag in soup.find_all("script", type="module") if (src := tag.get("src"))]


@pytest.mark.asyncio
async def test_notifications_path_serves_spa_shell(client: AppClient):
    """`/notifications` is a client-routed SPA path (app/routers/spa.py): the server
    serves the SPA entry, not the Jinja notifications page. test_spa.py covers the
    shell's generic contents; this asserts only what's specific to this path."""
    await client.get_default_user()

    response = await client.get("/notifications")

    assert response.status_code == status.HTTP_200_OK
    body = response.text
    # Booted by the spa entry, not the legacy main bundle. Match the entry token
    # in the script srcs rather than anywhere in the body (which "spa" can hit by
    # accident), mirroring test_spa.py.
    srcs = _module_script_srcs(body)
    assert any("spa" in src for src in srcs), srcs
    assert not any(re.search(r"/main[.\-]", src) for src in srcs), srcs
    # The page is client-routed, so the Jinja island mount point is absent.
    assert '<div id="react-notifications"></div>' not in body


@pytest.mark.asyncio
async def test_notifications_shell_served_to_unauthenticated_users(client: AppClient):
    """The shell carries no get_current_user dependency, so the server returns the
    shell (200) for unauthenticated requests instead of redirecting — the client
    beforeLoad guard is the sole auth gate. The mobile WebView's /login session-clear
    watcher is unaffected: redirectToLogin still does a full-document load to /login,
    so the WebView's top-level URL still lands there exactly as the old server 307 did."""
    with client.logged_out():
        response = await client.get("/notifications")

    assert response.status_code == status.HTTP_200_OK
    assert '<div id="root">' in response.text
