import re
from contextlib import contextmanager
from uuid import UUID, uuid4

import pytest
import sentry_sdk
from fastapi import status
from httpx import ASGITransport, AsyncClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from tortoise.exceptions import DoesNotExist

from app.main import app
from app.routers.api import API_PREFIX
from app.routers.dependencies import RequestAccessError
from config import settings
from tests.helpers.app import BASE_URL, AppClient
from tests.helpers.factories import create_meeting, create_user


@contextmanager
def temp_routes():
    # Snapshot route count so registered test routes can be popped back to the
    # original length regardless of how many @app.get decorators ran.
    initial = len(app.routes)
    try:
        yield
    finally:
        while len(app.routes) > initial:
            app.routes.pop()


@pytest.mark.asyncio
async def test_api_error_returns_json(client: AppClient):
    with temp_routes():

        @app.get(f"{API_PREFIX}/test_not_found")
        async def test_not_found():
            raise DoesNotExist("Test not found")

        @app.get(f"{API_PREFIX}/test_server_error")
        async def test_server_error():
            raise Exception("Something broke")

        @app.get(f"{API_PREFIX}/test_validation/{{record_id}}")
        async def test_validation(record_id: UUID):
            return {"id": str(record_id)}

        response = await client.get(f"{API_PREFIX}/test_not_found")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json() == {"detail": "Not Found"}

        # ServerErrorMiddleware always re-raises after sending the response,
        # so we need a client that won't propagate the exception.
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url=BASE_URL,
        ) as no_raise_client:
            response = await no_raise_client.get(f"{API_PREFIX}/test_server_error")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "An error occurred"}

        # FastAPI path-validator failures on /api/* preserve FastAPI's
        # structured validation payload so JSON clients can introspect the
        # offending field. (HTML requests get the polished 4xx page instead.)
        response = await client.get(f"{API_PREFIX}/test_validation/not-a-uuid")
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert isinstance(data["detail"], list)
        assert data["detail"][0]["type"] == "uuid_parsing"


@pytest.mark.asyncio
async def test_generic_exception(client: AppClient):
    with temp_routes():

        @app.get("/test_exception")
        async def test_exception():
            raise Exception("Test exception")

        with pytest.raises(Exception):
            response = await client.get("/test_exception")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Test exception" in response.text


@pytest.mark.asyncio
async def test_ignoring_paths(client: AppClient):
    current_ignore_error_handler_paths = app.state.ignore_error_handler_paths
    try:
        with temp_routes():
            app.state.ignore_error_handler_paths = [re.compile("/test_exception")]

            @app.get("/test_exception")
            async def test_exception():
                raise DoesNotExist("Test exception")

            with pytest.raises(DoesNotExist):
                response = await client.get("/test_exception")
                # With graceful exception handling, the status code would be 404
                assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    finally:
        app.state.ignore_error_handler_paths = current_ignore_error_handler_paths


@pytest.mark.asyncio
async def test_error_pages_render_polished_html(client: AppClient, monkeypatch):
    """Happy path: authenticated 4xx and 5xx render the branded page with
    status-specific copy and the pinned visual contract."""
    with temp_routes():

        @app.get("/test_403")
        async def test_403():
            raise StarletteHTTPException(status_code=403)

        @app.get("/test_422")
        async def test_422():
            raise StarletteHTTPException(status_code=422)

        @app.get("/test_validation/{record_id}")
        async def test_validation(record_id: UUID):
            return {"id": str(record_id)}

        @app.get("/test_410")
        async def test_410():
            raise StarletteHTTPException(status_code=410)

        @app.get("/test_5xx")
        async def test_5xx():
            raise Exception("Intentional 5xx")

        creator = await client.get_default_user()
        other_user = await create_user()
        # A still-server-rendered resource is required here: the error pages are Jinja,
        # so the vehicle must be a path with an HTML handler. SPA-shell paths (goals,
        # posts, documents, chats) answer 200 with the shell for any id and gate access
        # client-side, so they can't exercise a server 404 at all.
        meeting = await create_meeting(creator_id=creator.id, organization_id=creator.organization_id)
        assert creator.organization_id != other_user.organization_id

        with client.current_user_as(creator):
            # 404 with the full visual contract pinned (font-accent heading,
            # no alert-error block, one btn-primary CTA, no error glyph).
            response = await client.get(f"/meetings/{uuid4()}")
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "Page not found" in response.text
            assert "font-accent" in response.text
            assert "alert alert-error" not in response.text
            assert "btn btn-primary" in response.text
            assert '<span class="material-symbols-outlined">error</span>' not in response.text

            # With a Sentry DSN configured and an authenticated user, the
            # SENTRY_USER script is rendered — the fix guards on current_user,
            # it does not remove the block globally. Pinned against a normal
            # authenticated 200 page (the error-handler render path builds its
            # own Authentication and never carries a current_user in tests).
            # Also pins that the true-branch serializes the real identity through
            # tojson | safe, not just the literal SENTRY_USER string.
            monkeypatch.setattr(settings, "sentry_dsn", "https://public@o0.ingest.sentry.io/0")
            response = await client.get(f"/meetings/{meeting.id}")
            assert response.status_code == status.HTTP_200_OK
            assert "SENTRY_USER" in response.text
            assert creator.email in response.text

            response = await client.get("/test_403")
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "don't have access" in response.text.lower()
            assert "font-accent" in response.text

            response = await client.get("/test_422")
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
            assert "Invalid request" in response.text
            assert "font-accent" in response.text

            # FastAPI path-validator failures (RequestValidationError) also
            # route through the polished 422 page — not raw JSON.
            response = await client.get("/test_validation/not-a-uuid")
            assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
            assert "Invalid request" in response.text
            assert "font-accent" in response.text
            assert "alert alert-error" not in response.text

            # Generic 4xx fallback still shows the numeric code for support triage.
            response = await client.get("/test_410")
            assert response.status_code == 410
            assert "410" in response.text
            assert "font-accent" in response.text

            # HX-Request returns the partial layout (no full <html> shell).
            response = await client.get(f"/meetings/{uuid4()}", headers={"HX-Request": "true"})
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "<html" not in response.text
            assert "font-accent" in response.text

        # Cross-org access on a real record still 404s through the same template.
        with client.current_user_as(other_user):
            response = await client.get(f"/meetings/{meeting.id}")
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "Page not found" in response.text

        # 5xx now renders polished HTML (was PlainTextResponse).
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url=BASE_URL,
        ) as no_raise_client:
            response = await no_raise_client.get("/test_5xx")
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert "text/html" in response.headers.get("content-type", "")
        assert "Something went wrong" in response.text
        assert "font-accent" in response.text
        assert "alert alert-error" not in response.text

        # The 5xx handler builds its template context by hand (it skips the
        # dependency layer to avoid touching the DB on a failure path). The
        # head's inline <script>s would render as `nonce=""` and be blocked
        # by strict-dynamic CSP if csp_nonce weren't threaded through. The CSP
        # rides whichever header the mode picked (enforcing without a Sentry
        # collector, e.g. in tests; report-only with one).
        csp_header = (
            response.headers.get("Content-Security-Policy-Report-Only") or response.headers["Content-Security-Policy"]
        )
        csp_nonce_match = re.search(r"'nonce-([^']+)'", csp_header)
        assert csp_nonce_match, "no script-src nonce in CSP header"
        assert f'nonce="{csp_nonce_match.group(1)}"' in response.text


@pytest.mark.asyncio
async def test_error_pages_for_unauthenticated_users(monkeypatch):
    """Secure path: anonymous users get a valid HTML page, the CTA points to
    /login (not mailbox_index), and 403 copy drops 'signed in' framing.
    With a Sentry DSN configured (as in production) the SENTRY_USER script must
    be omitted for anonymous requests rather than crashing on a None user."""
    with temp_routes():

        @app.get("/test_unauth_404")
        async def test_unauth_404():
            raise StarletteHTTPException(status_code=404)

        @app.get("/test_unauth_403")
        async def test_unauth_403():
            raise StarletteHTTPException(status_code=403)

        @app.get("/test_unauth_405")
        async def test_unauth_405():
            raise StarletteHTTPException(status_code=405)

        monkeypatch.setattr(settings, "sentry_dsn", "https://public@o0.ingest.sentry.io/0")

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url=BASE_URL,
        ) as anon_client:
            response = await anon_client.get("/test_unauth_404")
            assert response.status_code == status.HTTP_404_NOT_FOUND
            assert "<html" in response.text
            assert "font-accent" in response.text
            assert "/login" in response.text
            assert "SENTRY_USER" not in response.text

            response = await anon_client.get("/test_unauth_405")
            assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
            assert "<html" in response.text

            response = await anon_client.get("/test_unauth_403")
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert "signed in" not in response.text.lower()
            assert "don't have access" in response.text.lower()


@pytest.mark.asyncio
async def test_error_handler_regressions(client: AppClient, monkeypatch):
    """Regression path. Three previously broken behaviors pinned together:
    (1) the inverted capture_exception guard that silently dropped every 5xx
    Sentry event; (2) RequestAccessError 500-ing on KeyError from GlobalID for
    unregistered model types instead of falling through to 404; (3) debug-mode
    plain-text traceback survives the move to an HTML 5xx page."""
    with temp_routes():

        @app.get("/test_sentry")
        async def test_sentry():
            raise Exception("Sentry test")

        @app.get("/test_request_access_fallback")
        async def test_request_access_fallback():
            raise RequestAccessError(global_id=f"GoalType:{uuid4()}")

        @app.get("/test_debug_5xx")
        async def test_debug_5xx():
            raise Exception("Debug test exception")

        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url=BASE_URL,
        ) as no_raise_client:
            monkeypatch.setattr(sentry_sdk, "capture_exception", lambda *a, **k: "abc123event")
            response = await no_raise_client.get("/test_sentry")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "abc123event" in response.text
            assert "Error ID" in response.text

            monkeypatch.setattr(sentry_sdk, "capture_exception", lambda *a, **k: None)
            response = await no_raise_client.get("/test_sentry")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "Error ID" not in response.text

            monkeypatch.setattr(settings, "show_debug_exceptions", True)
            response = await no_raise_client.get("/test_debug_5xx")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "text/plain" in response.headers.get("content-type", "")
            assert "Debug test exception" in response.text
            assert "<html" not in response.text

        monkeypatch.undo()

        user = await client.get_default_user()
        with client.current_user_as(user):
            response = await client.get("/test_request_access_fallback")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "font-accent" in response.text
