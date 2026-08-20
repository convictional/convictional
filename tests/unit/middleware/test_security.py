import re

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.testclient import TestClient
from pydantic import HttpUrl

from app.middleware.security import SecureHeadersMiddleware
from config import settings

app = FastAPI()
app.add_middleware(SecureHeadersMiddleware)


@app.get("/page")
async def page_route():
    return HTMLResponse("<html><body>Page</body></html>")


@app.get("/echo-nonce")
async def echo_nonce(request: Request):
    return HTMLResponse(request.state.csp_nonce)


@app.get("/mcp/authorize")
async def mcp_authorize():
    return HTMLResponse("<html><body>authorize</body></html>")


@app.get("/mcp/consent")
async def mcp_consent():
    return HTMLResponse("<html><body>consent</body></html>")


@app.get("/mcp/anything-else")
async def mcp_anything_else():
    return HTMLResponse("<html><body>tool</body></html>")


client = TestClient(app)

_NONCE_RE = re.compile(r"script-src [^;]*?'nonce-([^']+)'")
_OFFLINE_HASH_RE = re.compile(r"script-src [^;]*?'sha256-[A-Za-z0-9+/=]+='")


def _csp(response) -> str:
    # The same directive string is emitted under whichever header the configured
    # mode picked (report-only with a collector, enforcing without one), so tests
    # that only care about the directives read whichever header is present.
    return response.headers.get("Content-Security-Policy-Report-Only") or response.headers["Content-Security-Policy"]


def test_sets_baseline_security_headers_on_every_response():
    response = client.get("/page")

    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_csp_mode_follows_whether_a_violation_collector_is_configured():
    # With a collector, stay in Report-Only so violations are monitored without
    # breaking the page. Without one (e.g. local dev), enforce — a report-only
    # policy reporting nowhere is the one useless state.
    with settings.override():
        settings.sentry_dsn = HttpUrl("https://abc123@o0.ingest.sentry.io/42")
        headers = client.get("/page").headers
    assert "Content-Security-Policy-Report-Only" in headers
    assert "Content-Security-Policy" not in headers

    with settings.override():
        settings.sentry_dsn = None
        headers = client.get("/page").headers
    assert "Content-Security-Policy" in headers
    assert "Content-Security-Policy-Report-Only" not in headers


def test_content_security_policy_has_all_required_directives():
    csp = _csp(client.get("/page"))

    assert "default-src 'self'" in csp
    assert "script-src 'self' 'nonce-" in csp
    assert "'strict-dynamic'" in csp
    assert "'unsafe-eval'" in csp  # required by Alpine.js inline directives
    # Sentry is bundled (@sentry/browser), no longer loaded from a CDN, so its
    # script host must not be allow-listed. Events still POST to the ingest hosts
    # allow-listed in connect-src below.
    assert "sentry-cdn" not in csp
    assert "style-src 'self' 'unsafe-inline'" in csp
    assert "https://use.typekit.net" in csp
    assert "https://p.typekit.net" in csp
    assert "https://fonts.googleapis.com" in csp
    assert "img-src 'self' data: blob: https:" in csp
    assert "media-src 'self' https://storage.googleapis.com" in csp
    assert "font-src 'self' https://use.typekit.net https://fonts.gstatic.com data:" in csp
    assert "connect-src 'self' https://*.sentry.io https://*.ingest.sentry.io https://api.klipy.com" in csp
    assert "worker-src 'self' blob:" in csp
    assert "manifest-src 'self'" in csp
    assert "frame-src 'self' https://www.youtube.com" in csp
    assert "https://player.vimeo.com" in csp
    assert "https://www.loom.com" in csp
    assert "object-src 'none'" in csp
    assert "base-uri 'self'" in csp
    # Both SSO sign-in forms (`/auth/google`, `/auth/microsoft`) submit and
    # then redirect to their provider, so both provider hosts must be allowed
    # by form-action or the browser blocks the redirect.
    assert "form-action 'self' https://accounts.google.com https://login.microsoftonline.com" in csp
    # Hash for the inline retry script in `static/offline.html`. The exact
    # digest is computed at import in security.py from the actual file body
    # (assertions there guard structural assumptions); the unit test only
    # validates that *some* sha256 source made it into script-src.
    assert _OFFLINE_HASH_RE.search(csp)


def test_form_action_omitted_only_on_mcp_oauth_form_routes():
    # `/mcp/authorize` and `/mcp/consent` render HTML forms that 302 to
    # client-registered `redirect_uri`s we can't enumerate — form-action
    # would block them. Any other `/mcp/*` route is JSON and must stay
    # restricted by `form-action 'self' …`.
    for exempt_path in ("/mcp/authorize", "/mcp/consent"):
        csp = _csp(client.get(exempt_path))
        assert "form-action" not in csp, f"{exempt_path} should be exempt from form-action"

    csp = _csp(client.get("/mcp/anything-else"))
    assert "form-action 'self' https://accounts.google.com" in csp


def test_form_action_includes_oauth_proxy_when_configured():
    # Staging/demo/prod route the SSO callback back through the oauth-proxy
    # before it lands on our origin, so the proxy is an in-chain redirect hop
    # of the sign-in form submission. If it isn't allow-listed, an already
    # authenticated IdP session 302s straight through it and the browser trips
    # form-action. Unset (local dev hits the IdP redirect_uri directly), it
    # must not appear.
    with settings.override():
        settings.oauth_proxy_url = ""
        csp = _csp(client.get("/page"))
        form_action = next(d for d in csp.split("; ") if d.startswith("form-action"))
        assert "run.app" not in form_action

        settings.oauth_proxy_url = "https://convictional-oauth-proxy.example.run.app/"
        csp = _csp(client.get("/page"))
        form_action = next(d for d in csp.split("; ") if d.startswith("form-action"))
        # rstrip the trailing slash — a CSP host-source must not carry a path.
        assert "https://convictional-oauth-proxy.example.run.app" in form_action
        assert "run.app/" not in form_action


def _csp_nonce(csp: str) -> str:
    match = _NONCE_RE.search(csp)
    assert match, f"no script-src nonce in CSP: {csp!r}"
    return match.group(1)


def test_csp_nonce_is_fresh_per_request_and_matches_request_state():
    response_a = client.get("/echo-nonce")
    response_b = client.get("/echo-nonce")

    handler_nonce_a = response_a.text
    handler_nonce_b = response_b.text
    header_nonce_a = _csp_nonce(_csp(response_a))
    header_nonce_b = _csp_nonce(_csp(response_b))

    assert handler_nonce_a and handler_nonce_b
    assert handler_nonce_a == header_nonce_a
    assert handler_nonce_b == header_nonce_b
    assert handler_nonce_a != handler_nonce_b


def test_csp_reports_violations_to_sentry_when_dsn_configured():
    with settings.override():
        settings.sentry_dsn = HttpUrl("https://abc123@o0.ingest.sentry.io/42")
        csp = _csp(client.get("/page"))

    assert "report-uri https://o0.ingest.sentry.io/api/42/security/?" in csp
    assert "sentry_key=abc123" in csp


def test_csp_omits_report_uri_when_sentry_disabled():
    with settings.override():
        settings.sentry_dsn = None
        csp = _csp(client.get("/page"))

    assert "report-uri" not in csp


def test_csp_allows_vite_dev_server_when_building_assets():
    # In dev the Vite dev server is the asset origin (the CDN's stand-in), so it
    # must appear in every fetch directive that loads bundled assets — e.g. email
    # bodies render in srcdoc iframes that load styles/email.css from it, which
    # enforcing CSP would otherwise block. The HMR client additionally needs its
    # ws:// origin in connect-src. Production (assets prebuilt) must not advertise
    # the localhost dev origin.
    with settings.override():
        settings.vite_url = HttpUrl("http://localhost:5190")

        settings.asset_building_enabled = False
        assert "localhost:5190" not in _csp(client.get("/page"))

        settings.asset_building_enabled = True
        csp = _csp(client.get("/page"))

    for directive in ("script-src", "style-src", "font-src", "worker-src", "connect-src"):
        directive_value = next(d for d in csp.split("; ") if d.startswith(directive))
        assert "http://localhost:5190" in directive_value, f"{directive!r} missing Vite origin: {directive_value!r}"
    connect_src = next(d for d in csp.split("; ") if d.startswith("connect-src"))
    assert "ws://localhost:5190" in connect_src


def test_csp_allows_asset_host_for_cdn_served_bundles():
    with settings.override():
        settings.asset_host = HttpUrl("https://cdn.example.com")
        csp = _csp(client.get("/page"))

    # Bundled scripts, stylesheets, fonts, workers, and any fetch() against
    # the CDN must be allowed by every directive a browser consults for them.
    for directive in ("script-src", "style-src", "font-src", "worker-src", "connect-src"):
        directive_value = next(d for d in csp.split("; ") if d.startswith(directive))
        assert "https://cdn.example.com" in directive_value, f"{directive!r} missing CDN host: {directive_value!r}"
