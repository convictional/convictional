import secrets
from re import Pattern

import sentry_sdk
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Match
from starlette.types import ASGIApp, Receive, Scope, Send

from config import settings


def rotate_csrf_token(session: dict, state) -> str:
    token = secrets.token_urlsafe(32)
    session["csrf_token"] = token
    state.csrf_token = token
    return token


class CSRFMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        exempt_urls: list[Pattern] | None = None,
        safe_methods: set[str] = {"GET", "HEAD", "OPTIONS", "TRACE"},
        header_name: str = "x-csrftoken",
        form_field_name: str = "csrf_token",
        routes: list[BaseRoute] | None = None,
    ) -> None:
        self.app = app
        self.exempt_urls = exempt_urls or []
        self.safe_methods = safe_methods
        self.header_name = header_name
        self.form_field_name = form_field_name
        self.routes = routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        session = scope.get("session", {})

        token = session.get("csrf_token")
        if not token:
            token = rotate_csrf_token(session, request.state)
        else:
            request.state.csrf_token = token

        if request.method not in self.safe_methods and not self._is_exempt(request):
            # If the route doesn't exist, pass the request up the chain to return a 404
            if self.routes is not None and not self._has_matching_route(scope):
                await self.app(scope, receive, send)
                return

            if settings.sentry_dsn:
                sentry_sdk.set_context(
                    "CSRF",
                    {
                        "path": request.url.path,
                        "method": request.method,
                        "userId": session.get("user_id", ""),
                    },
                )

            # Valid routes need to verify the token
            submitted = await self._get_submitted_csrf_token(request)
            if not submitted:
                if settings.sentry_dsn:
                    sentry_sdk.capture_message("CSRF token missing from request", level="warning")
                response = Response("CSRF token is required", status_code=403)
                response.headers["X-CSRF-Failure"] = "true"
                await response(scope, receive, send)
                return
            if not secrets.compare_digest(submitted, token):
                if settings.sentry_dsn:
                    sentry_sdk.capture_message("CSRF token verification failed", level="warning")
                response = Response("CSRF token verification failed", status_code=403)
                response.headers["X-CSRF-Failure"] = "true"
                await response(scope, receive, send)
                return

            # Replace receive so downstream handlers can re-read the body
            # Only needed when we consumed the stream to parse form data
            if hasattr(request, "_body"):
                receive = self._cached_receive(request._body)

        await self.app(scope, receive, send)

    def _is_exempt(self, request: Request) -> bool:
        return any(pattern.fullmatch(request.url.path) for pattern in self.exempt_urls)

    def _has_matching_route(self, scope: Scope) -> bool:
        if not self.routes:
            return True
        return any(route.matches(scope)[0] != Match.NONE for route in self.routes)

    async def _get_submitted_csrf_token(self, request: Request) -> str | None:
        token = request.headers.get(self.header_name)
        if token:
            return token

        # Cache the raw body before parsing form so it can be replayed
        request._body = await request.body()
        form = await request.form()
        await form.close()
        value = form.get(self.form_field_name)
        return value if isinstance(value, str) else None

    @staticmethod
    def _cached_receive(body: bytes) -> Receive:
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        return receive
