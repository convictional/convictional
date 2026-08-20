from fastapi import Request
from starlette.background import BackgroundTasks
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from infra.jobs import JobsOutbox


class JobsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        await JobsOutbox.reset()

        response = await call_next(request)

        if not isinstance(response.background, BackgroundTasks):
            response.background = BackgroundTasks()
        response.background.add_task(JobsOutbox.enqueue_pending)
        return response
