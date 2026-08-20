import http
from collections.abc import Callable
from pprint import pformat
from re import Pattern

import sentry_sdk
from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from jinja2 import Template
from starlette.exceptions import HTTPException as StarletteHTTPException
from tortoise.exceptions import DoesNotExist

from app.middleware.security import apply_security_headers
from app.models.accounts import SignupBlockedError, SignupsDisabledError
from app.models.collaboration.workspace import WorkspaceMixin
from app.routers import API_PREFIX
from app.routers.dependencies import Authentication, Helpers, RequestAccessError, get_templates
from config import settings
from config.enums import FlashLevel
from config.logging import ExceptionDebugDetails
from infra.db import GlobalID, InvalidGlobalIDParamError
from infra.storage import FileValidationError

EXCEPTION_MAP: dict[type[Exception] | int, int] = {}

DEBUG_ERROR_TEMPLATE_PATH = settings.root / "app" / "templates" / "errors" / "5xx_debug.txt.jinja"

with DEBUG_ERROR_TEMPLATE_PATH.open("r") as template:
    DEBUG_ERROR_TEMPLATE_CONTENT = template.read()


def _register_handler(
    app: FastAPI, exception: int | type[Exception], handler: Callable, status_code: int | None = None
):
    app.add_exception_handler(exception, handler)
    if status_code:
        EXCEPTION_MAP[exception] = status_code


def register_error_handlers(app: FastAPI, ignore_paths: list[Pattern[str]] = []):
    app.state.ignore_error_handler_paths = ignore_paths

    _register_handler(app, Exception, error_handler)
    _register_handler(app, StarletteHTTPException, error_handler)
    _register_handler(app, DoesNotExist, error_handler, status.HTTP_404_NOT_FOUND)
    _register_handler(app, InvalidGlobalIDParamError, error_handler, status.HTTP_422_UNPROCESSABLE_CONTENT)
    _register_handler(app, FileValidationError, error_handler, status.HTTP_422_UNPROCESSABLE_CONTENT)
    _register_handler(app, RequestValidationError, error_handler, status.HTTP_422_UNPROCESSABLE_CONTENT)
    _register_handler(app, RequestAccessError, request_access_handler, status.HTTP_404_NOT_FOUND)
    _register_handler(app, SignupsDisabledError, refused_signup_handler, status.HTTP_503_SERVICE_UNAVAILABLE)
    _register_handler(app, SignupBlockedError, refused_signup_handler, status.HTTP_403_FORBIDDEN)


async def build_helpers(request: Request) -> Helpers:
    authentication = Authentication(request)
    await authentication.load()
    templates = get_templates()
    return Helpers(connection=request, templates=templates, authentication=authentication)


async def error_handler(request: Request, exception: Exception):
    for pattern in request.app.state.ignore_error_handler_paths:
        if pattern.match(request.url.path):
            raise exception

    status_code = getattr(exception, "status_code", None) or EXCEPTION_MAP.get(
        type(exception), status.HTTP_500_INTERNAL_SERVER_ERROR
    )

    if request.url.path.startswith(API_PREFIX):
        # All 3xx in /api/ come from auth redirects (get_current_user raises 307).
        # If a future API endpoint needs a real redirect, this will need updating.
        if status.HTTP_300_MULTIPLE_CHOICES <= status_code < status.HTTP_400_BAD_REQUEST:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
            )
        if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            sentry_sdk.capture_exception(exception)
            return JSONResponse(status_code=status_code, content={"detail": "An error occurred"})
        if isinstance(exception, RequestValidationError):
            # Preserve FastAPI's structured validation payload for JSON clients —
            # `detail` is a list of {loc, msg, type, ...} entries, not a string.
            return JSONResponse(status_code=status_code, content={"detail": jsonable_encoder(exception.errors())})
        if isinstance(exception, StarletteHTTPException):
            detail = exception.detail if isinstance(exception.detail, str) else str(exception.detail)
        else:
            try:
                detail = http.HTTPStatus(status_code).phrase
            except ValueError:
                detail = "An error occurred"
        return JSONResponse(status_code=status_code, content={"detail": detail})

    if status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
        return await handle_5xx_error(request, exception, status_code)

    # Error handlers do not have access to dependencies, so we have to do this
    # manually to render a template with a proper layout
    helpers = await build_helpers(request)

    is_3xx_exception = status_code < status.HTTP_400_BAD_REQUEST
    if isinstance(exception, StarletteHTTPException) and is_3xx_exception:
        return await handle_redirect_exception(exception, status_code, helpers)

    response = helpers.render("errors/4xx.html.jinja", status_code=status_code)
    response.status_code = status_code

    return response


async def handle_redirect_exception(exception: StarletteHTTPException, status_code: int, helpers: Helpers):
    headers = exception.headers or {}
    redirect_url = headers.get("location", helpers.url_for("login"))
    return RedirectResponse(url=redirect_url, status_code=status_code)


async def handle_5xx_error(request: Request, exception: Exception, status_code: int):
    sentry_event_id = sentry_sdk.capture_exception(exception)

    if settings.show_debug_exceptions:
        details = ExceptionDebugDetails(exception, request, status_code)
        content = Template(DEBUG_ERROR_TEMPLATE_CONTENT).render(details=details, pformat=pformat)
        return PlainTextResponse(content=content, status_code=status_code)

    # Skip build_helpers() (which awaits authentication.load() against the DB)
    # and render directly against the public layout. If the original 500 was a
    # DB outage, recreating that query — or walking application_layout's nav
    # chain — would cascade a second 500.
    templates = get_templates()
    # Starlette's ServerErrorMiddleware catches uncaught exceptions above the
    # user middleware stack, so this response never passes through
    # SecureHeadersMiddleware. We pull the nonce off request.state (set on the
    # way in) and stamp the security headers ourselves.
    nonce = getattr(request.state, "csp_nonce", "")
    context = {
        "request": request,
        "settings": settings,
        "sentry_event_id": sentry_event_id,
        "csrf_token": request.session.get("csrf_token", ""),
        "session_created_at": request.session.get("created_at", ""),
        "csp_nonce": nonce,
    }
    response = templates.TemplateResponse(request, "errors/5xx.html.jinja", context, status_code=status_code)
    apply_security_headers(response, nonce, request.url.path)
    return response


REFUSED_SIGNUP_MESSAGES: dict[type[Exception], str] = {
    SignupsDisabledError: (
        "New signups are paused right now. If you already have an account, log in with the address you used before."
    ),
    SignupBlockedError: "This account can't sign in to Convictional.",
}


async def refused_signup_handler(request: Request, exception: Exception):
    # Handled centrally rather than per-router because the refusals come from
    # User.get_or_create_by_oauth, which every OAuth entry point shares — a try/except in
    # each router could be missed by a future one.
    for pattern in request.app.state.ignore_error_handler_paths:
        if pattern.match(request.url.path):
            raise exception

    status_code = EXCEPTION_MAP.get(type(exception), status.HTTP_503_SERVICE_UNAVAILABLE)
    message = REFUSED_SIGNUP_MESSAGES.get(type(exception), "This account can't be created right now.")

    if request.url.path.startswith(API_PREFIX):
        return JSONResponse(status_code=status_code, content={"detail": message})

    # The session write survives because LazySessionMiddleware wraps the exception
    # middleware, so it still serializes the flash on the way out.
    helpers = await build_helpers(request)
    helpers.flash(message, level=FlashLevel.ERROR)
    return RedirectResponse(url=helpers.url_for("login"), status_code=status.HTTP_302_FOUND)


async def request_access_handler(request: Request, exception: RequestAccessError):
    for pattern in request.app.state.ignore_error_handler_paths:
        if pattern.match(request.url.path):
            raise exception

    status_code = EXCEPTION_MAP.get(type(exception), status.HTTP_500_INTERNAL_SERVER_ERROR)

    helpers = await build_helpers(request)
    try:
        global_id = GlobalID.parse(exception.global_id)
        model = await global_id.get_or_none()
    except (KeyError, ValueError, IndexError):
        # KeyError: unknown app/record type in Tortoise registry (stale or bad global ID).
        # ValueError: malformed UUID in the global ID path.
        # IndexError: gid path missing the record-id segment.
        model = None

    if not model:
        return await error_handler(request, StarletteHTTPException(status_code=status_code))

    if isinstance(model, WorkspaceMixin):
        request_access_url = helpers.url_for("workspace_collaborators_request_access", workspace_id=model.workspace_id)
        # JSON clients (React islands) can't follow an HTML redirect — fetch()
        # would swallow it and resolve a bodyless response. Hand them the
        # request-access URL as data (403, mirroring how error_handler special-
        # cases /api/) so they can surface a "request access" affordance instead
        # of a dead-end error. Server-rendered pages still get the 302.
        if request.url.path.startswith(API_PREFIX):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Access required", "request_access_url": str(request_access_url)},
            )
        return RedirectResponse(url=request_access_url, status_code=status.HTTP_302_FOUND)
    else:
        # Fall back to a 404 if we get an unexpected exception - should never happen
        return await error_handler(request, StarletteHTTPException(status_code=status_code))
