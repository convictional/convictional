import json
import logging
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from logging.handlers import RotatingFileHandler
from platform import platform
from traceback import TracebackException
from typing import Any, Protocol, runtime_checkable

from fastapi.requests import HTTPConnection
from uvicorn.logging import DefaultFormatter

from .settings import settings

FMT = "%(levelprefix)s [%(asctime)s] -- %(name)s: %(message)s"
MAX_SIZE = 10485760  # 10MB
LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


@runtime_checkable
class Loggable(Protocol):
    def log_context(self) -> dict[str, Any]: ...


request_context: ContextVar[HTTPConnection | None] = ContextVar("request_context", default=None)
logging_context: ContextVar[dict | None] = ContextVar("logging_context", default=None)


class LoggingContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Handle logging context
        log_context = logging_context.get()
        if log_context:
            # Merge context with any existing json_fields from the original log call
            existing_fields = getattr(record, "json_fields", {})
            record.json_fields = {**log_context, **existing_fields}

        # Handle request context
        request = LoggingContext.get_request()
        if request is not None:
            record.http_request = LoggingContext.http_request(request)

        return True

    @staticmethod
    def get_context():
        return logging_context.get()


class LoggingContext:
    def __init__(self, request: HTTPConnection | None = None, *args: Loggable | dict[str, Any], **kwargs):
        # Convert loggable args
        context_dicts = [arg.log_context() if isinstance(arg, Loggable) else arg for arg in args]
        merged_context = {}
        for context in context_dicts:
            merged_context.update(context)
        merged_context.update(kwargs)

        self.new_context = self._convert_to_string_values(kwargs)
        self.request: HTTPConnection | None = request
        self.previous_context: dict | None = None
        self.previous_request: HTTPConnection | None = None

    @staticmethod
    def _convert_to_string_values(data: dict) -> dict:
        return {key: str(value) for key, value in data.items()}

    def __enter__(self):
        # Store previous context and request for restoration
        self.previous_context = logging_context.get()
        self.previous_request = request_context.get()

        # Set the request context if provided
        if self.request is not None:
            request_context.set(self.request)

        # Merge with existing context if it exists
        if self.previous_context:
            merged_context = {**self.previous_context, **self.new_context}
        else:
            merged_context = self.new_context.copy()

        # Set the merged context for this scope
        logging_context.set(merged_context)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore previous context and request (may be None)
        logging_context.set(self.previous_context)
        request_context.set(self.previous_request)

    @staticmethod
    def set_request(request: HTTPConnection | None):
        request_context.set(request)

    @staticmethod
    def get_request() -> HTTPConnection | None:
        return request_context.get()

    @staticmethod
    def http_request(request: HTTPConnection) -> dict:
        url = request.url
        request_dict = {
            "requestMethod": request.method if hasattr(request, "method") else None,
            # Include query string to match Cloud Run's built-in httpRequest.requestUrl
            "requestUrl": f"{url.scheme}://{url.netloc}{url.path}{'?' + url.query if url.query else ''}",
            "userAgent": request.headers.get("user-agent"),
        }

        if request.client:
            request_dict["remoteIp"] = request.client.host

        return request_dict


class CloudRunJsonFormatter(logging.Formatter):
    """Formats log records as single-line JSON for Cloud Run stdout.

    Cloud Logging parses JSON from stdout and maps special fields to the LogEntry:
    - "severity" → LogEntry.severity
    - "message" → display text in the logs explorer
    - "httpRequest" → top-level LogEntry.httpRequest (filterable in sinks)

    Custom fields from LoggingContext (e.g. user_id) are merged into the payload
    and appear under jsonPayload in Cloud Logging.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "severity": record.levelname,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            payload["exception"] = self.formatException(record.exc_info)
        if json_fields := getattr(record, "json_fields", None):
            payload.update(json_fields)
        # Cloud Logging extracts httpRequest from JSON stdout and promotes it to a
        # top-level LogEntry field, enabling filtering on httpRequest.requestUrl in sinks.
        if http_request := getattr(record, "http_request", None):
            payload["httpRequest"] = http_request
        return json.dumps(payload, default=str)


log_level = LEVELS.get(settings.log_level.lower(), logging.INFO)

# Get the root logger and configure it
logger = logging.getLogger()
logger.setLevel(log_level)

# Silence noisy third-party loggers
logging.getLogger("jax").setLevel(logging.WARNING)
logging.getLogger("docket").setLevel(logging.WARNING)
logging.getLogger("fakeredis").setLevel(logging.WARNING)
# watchfiles (uvicorn --reload) logs every detected change at DEBUG. Our file handler
# writes those lines into log/<env>.log, which watchfiles then sees as a change — a
# self-sustaining loop that floods the dev console.
logging.getLogger("watchfiles").setLevel(logging.WARNING)


# Create console handler for stdout
if settings.is_debug and settings.is_env("development"):
    from pygments import highlight
    from pygments.formatters.terminal import TerminalFormatter
    from pygments.lexers.sql import PostgresLexer
    from uvicorn.logging import ColourizedFormatter

    postgres = PostgresLexer()
    terminal_formatter = TerminalFormatter()

    class DevelopmentFormatter(ColourizedFormatter):
        def formatMessage(self, record: logging.LogRecord):  # noqa: N802
            original_message = record.getMessage()

            if record.name == "tortoise.db_client":
                if (
                    record.levelname == "DEBUG"
                    and not original_message.startswith("Created connection pool")
                    and not original_message.startswith("Closed connection pool")
                ):
                    record.args = ()
                    record.__dict__["color_message"] = highlight(
                        original_message, postgres, terminal_formatter
                    ).rstrip()
                    return super().formatMessage(record)

            # Format the base message
            formatted_message = super().formatMessage(record)

            # Add json_fields if present
            if hasattr(record, "json_fields") and record.json_fields:
                try:
                    json_str = json.dumps(record.json_fields, separators=(",", ":"))
                    formatted_message += f" log_context={json_str}"
                except Exception as e:
                    formatted_message += f" log_context=<log_context_serialization_error: {e}>"

            return formatted_message

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(log_level)
    stdout_handler.setFormatter(DevelopmentFormatter(fmt=FMT, use_colors=True))
    stdout_handler.addFilter(LoggingContextFilter())
    logger.addHandler(stdout_handler)

# If running on GCP, integrate with Cloud Logging
if settings.is_running_on_gcp:
    from google.cloud import logging as cloud_logging

    # Primary handler for all application-level logs on GCP
    client = cloud_logging.Client()
    gcp_handler = client.get_default_handler()
    gcp_handler.setLevel(log_level)
    gcp_handler.addFilter(LoggingContextFilter())
    logger.addHandler(gcp_handler)

    # Used by post_worker_init in gunicorn.py to reconfigure uvicorn loggers
    # after UvicornWorker overwrites their handlers.
    stdout_json_handler = logging.StreamHandler(sys.stdout)
    stdout_json_handler.setLevel(log_level)
    stdout_json_handler.setFormatter(CloudRunJsonFormatter())
    stdout_json_handler.addFilter(LoggingContextFilter())
else:
    # Create file handler for logging to a file
    log_file_path = settings.root / "log" / f"{settings.env}.log"
    file_handler = RotatingFileHandler(log_file_path, maxBytes=MAX_SIZE)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(DefaultFormatter(fmt=FMT, use_colors=False))
    file_handler.addFilter(LoggingContextFilter())
    logger.addHandler(file_handler)


@dataclass
class ExceptionDebugDetails:
    exception: Exception
    request: HTTPConnection
    status_code: int

    @property
    def now(self):
        return datetime.now().isoformat()

    @property
    def platform(self):
        return platform()

    @property
    def python(self):
        return sys.version

    @property
    def path_params(self):
        return self.request.path_params

    @property
    def query_params(self):
        return dict(self.request.query_params)

    @property
    def headers(self):
        return dict(self.request.headers)

    @property
    def cookies(self):
        return self.request.cookies

    @property
    def session(self):
        if hasattr(self.request, "session"):
            return self.request.session

    @property
    def formatted_exception(self):
        def format_tb(tb_exc: TracebackException, indent=0):
            lines = []
            pad = " " * indent
            if tb_exc.exc_type:
                lines.append(f"{pad}Exception Type   : {tb_exc.exc_type.__name__}")
            lines.append(f"{pad}Exception Message: {tb_exc.__str__()}")

            app_stack_trace_lines = []
            for frame in tb_exc.stack:
                if any(pattern in frame.filename for pattern in settings.debug_exceptions_filters):
                    continue
                frame_info = f"{pad}   {frame.filename}:{frame.lineno} in `{frame.name}`"
                if frame.line:
                    frame_info += f"\n{pad}        {frame.line.strip()}"
                app_stack_trace_lines.append(frame_info)
            if tb_exc.__cause__:
                app_stack_trace_lines.append(f"{pad}-- Caused By --")
                app_stack_trace_lines.extend(format_tb(tb_exc.__cause__, indent + 1))
            elif tb_exc.__context__ and not tb_exc.__suppress_context__:
                app_stack_trace_lines.append(f"{pad}-- Context --")
                app_stack_trace_lines.extend(format_tb(tb_exc.__context__, indent + 1))

            if app_stack_trace_lines:
                lines.append(f"{pad}App Stack Trace:")
                lines.extend(app_stack_trace_lines)

            return lines

        tb_exception = TracebackException.from_exception(self.exception, capture_locals=True)
        return "\n".join(format_tb(tb_exception))
