from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

STATIC_PREFIX = "/static/"


class CacheControlMiddleware(BaseHTTPMiddleware):
    """
    Decide caching policy for every response.

    Default: dynamic (non-/static) responses get `private, no-cache` so
    authenticated content is never stored by shared caches and the browser
    must revalidate before reusing it. We deliberately avoid `no-store` to
    keep the bfcache path alive for back/forward navigation. HTMX preload
    requests with stable responses get a brief private cache instead, so
    preloading actually saves a round trip.

    Handler intent wins: a route that already set Cache-Control is left alone.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)

        if request.url.path.startswith(STATIC_PREFIX):
            return response

        if "cache-control" in response.headers:
            return response

        if request.headers.get("hx-preloaded") == "true":
            # We can't sniff Set-Cookie here: LazySessionMiddleware sits outside
            # this middleware and appends Set-Cookie in its own ASGI send_wrapper
            # *after* dispatch() returns. Ask the session directly instead.
            session = request.scope.get("session")
            session_was_written = session is not None and session.modified
            is_success = status.HTTP_200_OK <= response.status_code < status.HTTP_300_MULTIPLE_CHOICES
            is_preloadable = is_success and not session_was_written
            if is_preloadable:
                response.headers["Cache-Control"] = "private, max-age=1"
                return response

        response.headers["Cache-Control"] = "private, no-cache"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response
