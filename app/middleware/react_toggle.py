from urllib.parse import urlencode

from pydantic import HttpUrl
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from config import settings

REACT_MODE_COOKIE = "react_mode"
REACT_MODE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year
TOGGLE_PARAM = "react"


class ReactToggleMiddleware:
    """
    Persists a user's choice to view in-progress React migrations across
    requests via a `react_mode` cookie.

    Do not remove until the React migration is fully complete. This is the
    A/B-testing harness for in-progress React refactors: it lets a tester pin a
    `?react=on`/`?react=off` branch so the migrated React island and the legacy
    HTMX/Alpine page can be compared side by side. It may temporarily have no
    consumer between migrations — that is expected, not dead code.

    A GET request from a logged-in browser carrying `?react=on` or `?react=off`
    gets a 302 to the same URL minus the param, with `Set-Cookie: react_mode=on`
    or a deletion cookie. Templates read the cookie via `react_mode_enabled`
    instead of inspecting query params — so HTMX swaps, redirects, and hotkey
    navigation all keep the tester on the same branch.

    Must be registered inside `LazySessionMiddleware` (i.e. added earlier in
    `app/main.py`) so `scope["session"]` is populated when the auth check runs.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        # Re-coerce via HttpUrl: settings.base_url is typed HttpUrl but some test
        # envs hand it back as a string, so `.scheme` / `.host` fail. Matches the
        # workaround in app/middleware/security.py.
        base_url = HttpUrl(settings.base_url)
        self._cookie_secure = base_url.scheme == "https"
        self._cookie_domain = f".{base_url.host}" if settings.is_env("staging", "production") else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return

        # /api/* returns JSON; redirecting it would break fetch() callers.
        if scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        value = request.query_params.get(TOGGLE_PARAM)
        if value not in ("on", "off"):
            await self.app(scope, receive, send)
            return

        # HTMX requests need HX-Redirect to follow a navigation; testers paste
        # `?react=on` in the address bar, so a normal 302 is enough.
        if request.headers.get("HX-Request") == "true":
            await self.app(scope, receive, send)
            return

        response = RedirectResponse(_stripped_url(request), status_code=302)

        if scope.get("session", {}).get("user_id"):
            if value == "on":
                response.set_cookie(
                    REACT_MODE_COOKIE,
                    "on",
                    max_age=REACT_MODE_COOKIE_MAX_AGE,
                    path="/",
                    domain=self._cookie_domain,
                    secure=self._cookie_secure,
                    httponly=False,
                    samesite="lax",
                )
            else:
                response.delete_cookie(
                    REACT_MODE_COOKIE,
                    path="/",
                    domain=self._cookie_domain,
                )

        await response(scope, receive, send)


def _stripped_url(request: Request) -> str:
    kept = [(k, v) for k, v in request.query_params.multi_items() if k != TOGGLE_PARAM]
    return str(request.url.replace(query=urlencode(kept)))
