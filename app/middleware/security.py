import base64
import hashlib
import secrets

from bs4 import BeautifulSoup
from fastapi import Request
from pydantic import HttpUrl
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from config import settings
from config.sentry import sentry_security_report_url


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce security headers"""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Per-request nonce for inline <script> blocks. Stashed on request.state
        # so the dependency layer can surface it to Jinja as `csp_nonce`, and
        # so `apply_security_headers` can reuse it when the 5xx handler runs
        # outside the middleware stack (see `app/routers/errors.py`).
        nonce = secrets.token_urlsafe(16)
        request.state.csp_nonce = nonce

        response = await call_next(request)
        apply_security_headers(response, nonce, request.url.path)
        return response


def apply_security_headers(response: Response, nonce: str, path: str) -> None:
    """Stamp the standard set of security headers onto `response`.

    Normally handled by SecureHeadersMiddleware on the way out. The 5xx
    exception handler bypasses every user-installed middleware (Starlette's
    ServerErrorMiddleware sits above them and short-circuits the response),
    so that path calls this directly to keep the headers consistent.
    """
    # Prevents clickjacking
    response.headers["X-Frame-Options"] = "DENY"

    # The CSP mode follows whether a violation collector is configured, never
    # the environment directly. Report-Only is a *monitoring* mode — its only
    # job is to ship violations to `report-uri`; a report-only policy with no
    # collector reports nowhere (browsers flag it as having no effect). So:
    #   - collector present (prod): Report-Only — tune the rules in Sentry
    #     without breaking the page. Flip to enforcing once the stream is quiet.
    #   - no collector (local dev): enforce — the policy actually protects, and
    #     any gap surfaces immediately to the developer instead of into a void.
    csp = _build_csp(nonce, path)
    report_url = sentry_security_report_url()
    if report_url:
        response.headers["Content-Security-Policy-Report-Only"] = f"{csp}; report-uri {report_url}"
    else:
        response.headers["Content-Security-Policy"] = csp

    # Prevent MIME type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"

    # Limit referrer leakage on cross-origin navigations
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

    # Enforces HTTPS
    if HttpUrl(settings.base_url).scheme == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000 ; includeSubDomains"


_OFFLINE_HTML_PATH = settings.root / "static" / "offline.html"


def _compute_offline_inline_script_sha256_sources() -> list[str]:
    # The offline page is served from the service worker cache, so we can't
    # inject a per-request CSP nonce. A sha256 hash source in script-src is
    # the only way `'strict-dynamic'` (which ignores `'self'`) will trust
    # an inline <script>. Hashes are computed once at import from the file
    # that ships with the repo — every inline script in `offline.html` gets
    # its own source, so adding or editing scripts on that page just works.
    # The stdlib `html.parser` backend keeps <script> content in CDATA mode,
    # so the body bytes match what the browser hashes at runtime.
    soup = BeautifulSoup(_OFFLINE_HTML_PATH.read_text(), "html.parser")
    bodies = [tag.decode_contents() for tag in soup.find_all("script") if not tag.get("src")]
    assert bodies, f"no inline <script> in {_OFFLINE_HTML_PATH}"
    return [f"'sha256-{base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()}'" for body in bodies]


_OFFLINE_INLINE_SCRIPT_SOURCES = " ".join(_compute_offline_inline_script_sha256_sources())

# FastMCP's OAuth proxy mounts `/authorize` and `/consent` under our `/mcp`
# prefix (see app/mcp/base.py → mount_mcp). Both render HTML forms that
# POST and then 302 to the requesting client's registered `redirect_uri` —
# a per-client host we can't enumerate — so `form-action 'self' …` would
# block them. Keep the exemption scoped to these two paths; everything
# else under `/mcp/` is JSON and stays restricted.
_MCP_OAUTH_FORM_ACTION_EXEMPT_PREFIXES = ("/mcp/authorize", "/mcp/consent")


def _connect_src() -> str:
    sources = "connect-src 'self' https://*.sentry.io https://*.ingest.sentry.io https://api.klipy.com"
    # The Vite HMR client opens a WebSocket back to the dev server. Its HTTP
    # origin is added by with_assets() (Vite is the dev asset origin); only the
    # ws:// origin has to be listed explicitly here.
    if settings.asset_building_enabled:
        sources += f" {str(settings.vite_url).rstrip('/').replace('http', 'ws', 1)}"
    return sources


def _build_csp(nonce: str, path: str) -> str:
    # `'strict-dynamic'` lets a nonce-trusted script transitively trust the
    # modules it imports, so we don't have to enumerate every script host. It's
    # required because our bundled entry (main.ts / spa.tsx) is a nonce'd module
    # that dynamically imports the rest of the app (including @sentry/browser).
    #
    # `'unsafe-eval'` is required by Alpine.js, which compiles every inline
    # directive (`x-data`, `x-show`, `@click`, …) via `new AsyncFunction()`.
    # Removing it is gated on finishing the HTMX/Alpine→React migration; the
    # Alpine CSP build is not a drop-in (it requires every component to be
    # pre-registered as a named global), so a wholesale rewrite is the only
    # path off it.

    # Bundled JS/CSS, fonts, and workers are served from a separate origin: in
    # production `settings.asset_host` (e.g. https://cdn.{domain}); in dev the
    # Vite dev server. Inject whichever applies into every fetch directive a
    # browser consults for those resources. Missing the dev origin here is not
    # hypothetical — email bodies render in srcdoc iframes that load
    # styles/email.css from Vite, and enforcing CSP blocks it otherwise.
    asset_host = str(settings.asset_host).rstrip("/") if settings.asset_host else None
    vite_origin = str(settings.vite_url).rstrip("/") if settings.asset_building_enabled else None
    asset_origins = " ".join(origin for origin in (asset_host, vite_origin) if origin)

    def with_assets(directive: str) -> str:
        return f"{directive} {asset_origins}" if asset_origins else directive

    directives = [
        "default-src 'self'",
        with_assets(
            f"script-src 'self' 'nonce-{nonce}' 'strict-dynamic' 'unsafe-eval' {_OFFLINE_INLINE_SCRIPT_SOURCES}"
        ),
        # Alpine x-cloak, the inline <style> in _head.html.jinja, and inline
        # style="" attrs scattered through templates all need unsafe-inline.
        # p.typekit.net is where use.typekit.net's loader CSS @imports from;
        # fonts.googleapis.com serves Material Symbols icon CSS.
        with_assets(
            "style-src 'self' 'unsafe-inline'"
            " https://use.typekit.net https://p.typekit.net"
            " https://fonts.googleapis.com"
        ),
        with_assets("font-src 'self' https://use.typekit.net https://fonts.gstatic.com data:"),
        # `https:` is intentionally broad: link previews (lib/unfurl.py) load
        # images from arbitrary user-pasted URLs, so we can't enumerate hosts
        # without putting an image proxy in front of unfurl. Tightening this
        # is blocked on that proxy.
        "img-src 'self' data: blob: https:",
        # Meeting recordings and uploaded media are served as signed URLs
        # from the GCS bucket (see infra/storage.py:GCSStorage.url).
        "media-src 'self' https://storage.googleapis.com",
        with_assets(_connect_src()),
        with_assets("worker-src 'self' blob:"),
        "manifest-src 'self'",
        (
            "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com"
            " https://player.vimeo.com https://www.loom.com https://www.google.com"
        ),
        "object-src 'none'",
        "base-uri 'self'",
    ]

    # `form-action` constrains both the form's `action` URL and every URL the
    # submission redirects through. We omit it on the FastMCP OAuth routes
    # (see `_MCP_OAUTH_FORM_ACTION_EXEMPT_PREFIXES` above); form-action has
    # no default-src fallback, so omitting it leaves it unrestricted, which
    # is the intent there. `accounts.google.com` and `login.microsoftonline.com`
    # are the redirect targets of the `/auth/google` and `/auth/microsoft`
    # sign-in forms on `/login` and `/signup`. When an oauth-proxy is configured
    # (staging/demo/prod), the IdP redirects the callback back through it before
    # it lands on our origin — so the proxy is itself an in-chain hop and must be
    # allow-listed, or an already-authenticated IdP session (which 302s straight
    # through with no interactive stop) trips form-action.
    if not path.startswith(_MCP_OAUTH_FORM_ACTION_EXEMPT_PREFIXES):
        form_action = "form-action 'self' https://accounts.google.com https://login.microsoftonline.com"
        if settings.oauth_proxy_url:
            form_action += f" {settings.oauth_proxy_url.rstrip('/')}"
        directives.append(form_action)

    return "; ".join(directives)
