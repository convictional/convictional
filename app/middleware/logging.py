from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from config.logging import LoggingContext


class LoggingContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        log_fields = {}
        session = scope.get("session", {})
        if user_id := session.get("user_id"):
            log_fields["user_id"] = user_id

        with LoggingContext(request=connection, **log_fields):
            await self.app(scope, receive, send)
