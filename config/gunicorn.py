import logging

from config.logging import stdout_json_handler
from config.settings import settings

bind = f"0.0.0.0:{str(settings.app_port)}"

# Preload the application code before the worker processes are forked
preload_app = True

# Worker processes
workers = settings.worker_count
worker_class = "uvicorn.workers.UvicornWorker"

# Timeout configuration
keepalive = 5  # Default 2, set higher because we are behind a LB
graceful_timeout = settings.shutdown_timeout

# Logging
loglevel = settings.log_level
errorlog = "-"
accesslog = "-"
access_log_format = '%h %l %u %t "%r" %s %b "%{Referer}i" "%{User-Agent}i" %D'

# Process naming
proc_name = "convictional"


def post_worker_init(worker):
    """Re-configure uvicorn loggers after UvicornWorker overwrites their handlers."""
    if not settings.is_running_on_gcp:
        return

    for logger_name in ["uvicorn", "uvicorn.error", "uvicorn.access"]:
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers = [stdout_json_handler]
        uvicorn_logger.propagate = False
