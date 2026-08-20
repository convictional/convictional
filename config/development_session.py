"""Write a small JSON file at app/.development_session.json on server boot.

The sibling mobile app reads this file from its metro.config.js so a developer
who runs `make server` and then `make start_ios` in app/mobile/
gets their API base URL configured automatically; no per-machine .env editing.

Only active when ENV=development. Other environments no-op.
"""

import json
import logging
import time
from pathlib import Path

from config import settings

logger = logging.getLogger(__name__)

# Lives in the app/ dir that ties web and mobile together, alongside their subprojects.
SESSION_FILE = Path(__file__).resolve().parents[2] / ".development_session.json"


def write_development_session() -> None:
    if settings.env != "development":
        return

    try:
        SESSION_FILE.write_text(
            json.dumps(
                {
                    "web_port": settings.app_port,
                    "started_at": time.time(),
                },
                indent=2,
            )
        )
    except OSError:
        # Development-only convenience; never block app boot on this.
        logger.exception("Failed to write %s", SESSION_FILE)


def clear_development_session() -> None:
    if settings.env != "development":
        return

    SESSION_FILE.unlink(missing_ok=True)
