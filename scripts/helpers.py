from collections.abc import Awaitable

from app.main import app
from infra.db import close_db, init_db
from infra.messaging import start_subscription, stop_subscription

#
# Colorful console output
#
#

YELLOW = "\033[33m"
RED = "\033[31m"
GREEN = "\033[32m"
RESET = "\033[0m"


def green_text(text: str) -> str:
    return f"{GREEN}{text}{RESET}"


def yellow_text(text: str) -> str:
    return f"{YELLOW}{text}{RESET}"


def red_text(text: str) -> str:
    return f"{RED}{text}{RESET}"


#
# App lifecycle
#
#


async def in_app_lifespan(fn: Awaitable):
    async with app.router.lifespan_context(app):
        await fn


async def in_database_context(fn: Awaitable):
    await init_db()
    try:
        await fn
    finally:
        await close_db()


async def in_subscription_context(fn: Awaitable):
    await start_subscription()
    try:
        await fn
    finally:
        await stop_subscription()
