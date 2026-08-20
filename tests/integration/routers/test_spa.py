import re
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from fastapi import status

from app.routers.dependencies import INBOX_SORT_PREFERENCE_COOKIE
from app.routers.spa import SPA_ROUTES
from tests.helpers.app import AppClient


def _module_script_srcs(html: str) -> list[str]:
    # Matches both the raw entry path (no manifest) and the hashed build path
    # (manifest present), so assertions don't depend on whether `make assets` ran.
    soup = BeautifulSoup(html, "html.parser")
    return [src for tag in soup.find_all("script", type="module") if (src := tag.get("src"))]


@pytest.mark.asyncio
async def test_registered_path_serves_spa_shell(client: AppClient):
    """A path in the SPA registry returns the near-empty shell: a #root mount,
    the CSRF meta, the spa.tsx entry (never main.ts), and none of the legacy
    nav/htmx layout chrome."""
    await client.get_default_user()

    response = await client.get("/_spa")

    assert response.status_code == status.HTTP_200_OK
    body = response.text
    assert '<div id="root">' in body
    assert 'name="csrf-token"' in body
    assert 'name="page-title-prefix"' in body
    # Source of truth for useAssetVersionReloader, which compares it against the
    # version the `version_refresh` channel reports and hard-reloads on mismatch.
    assert 'name="asset-version"' in body
    # Source of truth for the React useIsMobile() hook (read off <html>); without
    # it every SPA route would treat the device as desktop.
    assert "data-is-mobile=" in body
    # Read by React to style rendered email HTML (EmailMessageBody/QuotedHtmlNodeView).
    assert "window.EMAIL_CSS_URL" in body
    # nonce attribute is stamped on the bundle scripts (empty in tests, which
    # bypass SecureHeadersMiddleware — the attribute is what matters here).
    assert "nonce=" in body
    # The shell boots the SPA entry, not the legacy main bundle. Match on the
    # entry token rather than the literal source path, which the Vite manifest
    # rewrites to build/spa-<hash>.js once assets are built.
    srcs = _module_script_srcs(body)
    assert any("spa" in src for src in srcs), srcs
    assert not any(re.search(r"/main[.\-]", src) for src in srcs), srcs
    # No nav/htmx chrome leaks in.
    assert "data-nav-sticky-wrapper" not in body
    assert "hx-boost" not in body
    assert 'name="htmx-config"' not in body


@pytest.mark.asyncio
async def test_documents_paths_serve_the_spa_shell(client: AppClient):
    """The documents index, show, and edit paths are registered as SPA routes:
    all return the shell, and the parameterized paths register fine because the
    shell handler ignores path params. The names stay resolvable for url_for
    (back_navigation, gid redirects, the comment/mention mailers) even though the
    Jinja handlers are gone."""
    await client.get_default_user()

    index = await client.get("/documents")
    assert index.status_code == status.HTTP_200_OK
    assert '<div id="root">' in index.text

    document_id = uuid4()
    show = await client.get(f"/documents/{document_id}")
    assert show.status_code == status.HTTP_200_OK
    assert '<div id="root">' in show.text

    # The editor serves the shell unconditionally — even a non-collaborator (here,
    # a nonexistent doc). The collaborator gate lives at GET /api/documents/{id};
    # the client route redirects non-collaborators to the read-only show page.
    edit = await client.get(f"/documents/{document_id}/edit")
    assert edit.status_code == status.HTTP_200_OK
    assert '<div id="root">' in edit.text


@pytest.mark.asyncio
async def test_posts_paths_serve_the_spa_shell(client: AppClient):
    """The posts index, show, and edit paths are registered as SPA routes: all
    return the shell, and the parameterized paths register fine because the shell
    handler ignores path params (here, a nonexistent post). The names stay
    resolvable for url_for (nav link, back_navigation, gid redirects, the
    post_created/commented/decided/pinned/announced mailers, and the
    posts_edit-targeted cross-status redirects) even though the Jinja handlers are
    gone. The draft↔show cross-status redirects live client-side, keyed on the
    complementary GET /api/posts/{id} and GET /api/posts/{id}/draft 404s."""
    await client.get_default_user()

    index = await client.get("/posts")
    assert index.status_code == status.HTTP_200_OK
    assert '<div id="root">' in index.text

    post_id = uuid4()
    show = await client.get(f"/posts/{post_id}")
    assert show.status_code == status.HTTP_200_OK
    assert '<div id="root">' in show.text

    # The editor serves the shell unconditionally — even a nonexistent post. The
    # draft gate lives at GET /api/posts/{id}/draft; the client route redirects a
    # published post to the read-only show page (and lands a genuine 404 on its
    # own error state, so the show⇄edit redirect pair can't loop).
    edit = await client.get(f"/posts/{post_id}/edit")
    assert edit.status_code == status.HTTP_200_OK
    assert '<div id="root">' in edit.text


@pytest.mark.asyncio
async def test_goals_paths_serve_the_spa_shell(client: AppClient):
    """The goals index and show paths are registered as SPA routes: both return the
    shell, and the parameterized path registers fine because the shell handler
    ignores path params (here, a nonexistent goal). The goals_index/goals_show names
    stay resolvable for url_for (the Goal and GoalComment gid redirects,
    back_navigation's BACK_LABELS, the mailbox entry href) even though the Jinja
    handlers are gone. Access gating lives at GET /api/goals/{id}, which 404s a goal
    outside the requester's organization (see
    tests/integration/routers/api/test_goals_show.py)."""
    await client.get_default_user()

    index = await client.get("/goals")
    assert index.status_code == status.HTTP_200_OK
    assert '<div id="root">' in index.text

    show = await client.get(f"/goals/{uuid4()}")
    assert show.status_code == status.HTTP_200_OK
    assert '<div id="root">' in show.text


# Route name -> path, matching SPA_ROUTES. Every name is a back-navigation fallback
# (app/helpers/url.py) and six are aliased onto canonical view names by
# api/mailbox_entries.py, so a dropped name silently degrades a back-button label
# rather than raising — _back_label_for_path swallows NoMatchFound.
MAILBOX_ROUTE_NAMES = {
    "mailbox_index": "/",
    "mailbox_unread": "/unread",
    "mailbox_archived": "/archived",
    "mailbox_sent": "/sent",
    "mailbox_drafts": "/drafts",
    "mailbox_assigned_to_me": "/assigned_to_me",
    "mailbox_snoozed": "/snoozed",
}


@pytest.mark.asyncio
async def test_mailbox_paths_serve_the_spa_shell(client: AppClient):
    """All seven inbox paths are registered as SPA routes and serve the shell, and all
    seven legacy route names stay resolvable through url_for even though the Jinja
    handlers are gone. The focus-preference redirect that GET / used to perform now
    lives client-side (routes/mailboxIndex.tsx beforeLoad, reading
    GET /api/users/me/mailbox_focus), so the shell is returned unconditionally."""
    await client.get_default_user()

    for name, path in MAILBOX_ROUTE_NAMES.items():
        response = await client.get(path)
        assert response.status_code == status.HTTP_200_OK, path
        assert '<div id="root">' in response.text, path
        assert (path, name) in SPA_ROUTES


@pytest.mark.asyncio
async def test_bare_inbox_no_longer_redirects_for_a_stored_focus(client: AppClient):
    """The stored focus preference no longer moves the user server-side: a soft
    navigation to "/" never reaches the server, so the redirect had to become a client
    guard. The cookie is still the store — it is read and written through
    /api/users/me/mailbox_focus."""
    await client.get_default_user()

    response = await client.get("/", cookies={INBOX_SORT_PREFERENCE_COOKIE: "sort=oldest"}, follow_redirects=False)

    assert response.status_code == status.HTTP_200_OK
    assert '<div id="root">' in response.text


@pytest.mark.asyncio
async def test_chats_paths_serve_the_spa_shell(client: AppClient):
    """The chats index and show paths are registered as SPA routes: both return
    the shell, and the parameterized path registers fine because the shell handler
    ignores path params. The chats_index/chats_show names stay resolvable for
    url_for (back_navigation, the Chat gid redirect, the mailbox entry href) even
    though the Jinja handlers are gone. The show shell is served unconditionally —
    even for a nonexistent chat; access gating lives at GET /api/chats/{id}, which
    404s a non-member (see tests/integration/routers/api/test_chats.py)."""
    await client.get_default_user()

    index = await client.get("/chats")
    assert index.status_code == status.HTTP_200_OK
    assert '<div id="root">' in index.text

    show = await client.get(f"/chats/{uuid4()}")
    assert show.status_code == status.HTTP_200_OK
    assert '<div id="root">' in show.text


@pytest.mark.asyncio
async def test_email_threads_paths_serve_the_spa_shell(client: AppClient):
    """The email-thread show and original-message paths are registered as SPA
    routes: both return the shell, and the parameterized paths register fine
    because the shell handler ignores path params. The email_threads_show /
    email_threads_show_original names stay resolvable for url_for (the gid
    redirect, the mailbox entry href, view_original_url) even
    though the Jinja handlers are gone. The show shell is served unconditionally —
    even for a nonexistent thread; access gating lives at GET /api/email_threads/{id},
    which 403s a same-org non-collaborator and 404s cross-org (see
    tests/integration/routers/api/test_email_threads_show.py)."""
    await client.get_default_user()

    thread_id = uuid4()
    show = await client.get(f"/email_threads/{thread_id}")
    assert show.status_code == status.HTTP_200_OK
    assert '<div id="root">' in show.text

    original = await client.get(f"/email_threads/{thread_id}/email_messages/{uuid4()}")
    assert original.status_code == status.HTTP_200_OK
    assert '<div id="root">' in original.text


@pytest.mark.asyncio
async def test_organization_edit_serves_spa_shell(client: AppClient):
    """The migrated organization settings page is a registered SPA path: it serves
    the shell (not the old Jinja island) and embeds no /api/organization* URL —
    the React route fetches its own data. Admin-gating moved to the route's
    beforeLoad, so the shell itself is served without a server admin check — note
    this passes for a non-admin user, proving the gate is no longer server-side."""
    await client.get_default_user()

    response = await client.get("/organization/edit")

    assert response.status_code == status.HTTP_200_OK
    body = response.text
    assert '<div id="root">' in body
    assert 'id="react-organization-settings"' not in body
    assert "/api/organization" not in body


@pytest.mark.asyncio
async def test_non_spa_path_renders_normal_layout(client: AppClient):
    """Paths outside the registry are untouched: a still-classic page renders the
    full server-side application layout, not the SPA shell."""
    await client.get_default_user()

    response = await client.get("/meetings")

    assert response.status_code == status.HTTP_200_OK
    assert 'hx-boost="true"' in response.text
    assert '<div id="root">' not in response.text


@pytest.mark.asyncio
async def test_unregistered_path_is_not_swallowed_by_shell(client: AppClient):
    """A path that resembles but isn't in the registry 404s — the shell handler
    only serves the explicit registry paths."""
    await client.get_default_user()

    response = await client.get("/_spa/not-registered")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_shell_is_served_to_unauthenticated_users(client: AppClient):
    """The shell is served regardless of auth — it carries no get_current_user
    dependency, so the server never redirects. This is the contract that makes
    client-side beforeLoad guards (routerGuards.ts) the sole auth gate for client
    routes; a server-side redirect here would make them dead code."""
    with client.logged_out():
        response = await client.get("/_spa")

    assert response.status_code == status.HTTP_200_OK
    assert '<div id="root">' in response.text
    assert 'data-authenticated="false"' in response.text


@pytest.mark.asyncio
async def test_shell_leaves_a_pending_flash_for_the_client_to_drain(client: AppClient):
    """The shell renders no flashes, so it must not consume them either: React drains
    them from /api/users/me at boot. Consuming them here destroys the flash set by
    whatever redirected in — a sent draft, a Gmail connect — since
    the shell render is the only thing between the redirect and the bootstrap fetch."""
    await client.get_default_user()
    client.seed_session(flashes=[{"content": "Message sent", "level": "success"}])

    shell = await client.get("/_spa")

    assert shell.status_code == status.HTTP_200_OK
    assert "Message sent" not in shell.text

    bootstrap = (await client.get("/api/users/me")).json()
    assert bootstrap["flashes"] == [{"content": "Message sent", "level": "success"}]


@pytest.mark.asyncio
async def test_htmx_request_is_bounced_to_a_full_navigation(client: AppClient):
    """hx-boost is global on the legacy layout, so a link from a legacy page to a
    SPA route reaches this handler as an htmx fragment fetch. Serving the shell
    body there lets htmx-ext-head-support merge its inline bootstrap scripts into
    the legacy document and crash (Sentry DECIDE-9WK/9WQ/9SG). Instead we answer
    with HX-Redirect so htmx does a real browser navigation; the query string is
    preserved so the follow-up top-level GET lands on the same URL."""
    await client.get_default_user()

    response = await client.get(
        "/documents?foo=bar",
        headers={"HX-Request": "true", "HX-Boosted": "true"},
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.headers["HX-Redirect"] == "/documents?foo=bar"
    assert '<div id="root">' not in response.text
