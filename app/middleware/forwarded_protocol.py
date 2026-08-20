from starlette.types import ASGIApp, Receive, Scope, Send


class ForwardedProtocolMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            headers = dict(scope.get("headers", []))
            x_forwarded_proto = headers.get(b"x-forwarded-proto")
            if x_forwarded_proto:
                scope["scheme"] = x_forwarded_proto.decode("latin-1")

        await self.app(scope, receive, send)
