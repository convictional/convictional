import asyncio
from collections.abc import Awaitable, Callable

from app.models.collaboration.workspace import Event
from config.enums import EventAction


async def assert_event_action(action: EventAction):
    events = await Event.all()
    event_actions = [event.action for event in events]
    assert action in event_actions


async def assert_live_markdown_contains(
    fetch_markdown: Callable[[], Awaitable[str]], expected: str, timeout: float = 10.0
) -> None:
    """Poll the shared test DB until the Yjs provider has pushed `expected` to the server.

    Browser tests that read content back in a fresh context (no local Yjs state), or after a
    reload, need the server to hold it. `window.__yIndexeddbSynced` only covers the local
    IndexedDB write, and the WebSocket flush behind it is debounced, so wait on the persisted
    markdown rather than on a fixed interval. Pass the last thing typed: Yjs updates arrive in
    order, so its presence proves everything before it landed too."""
    deadline = asyncio.get_running_loop().time() + timeout
    markdown = ""
    while asyncio.get_running_loop().time() < deadline:
        markdown = await fetch_markdown()
        if expected in markdown:
            return
        await asyncio.sleep(0.25)
    raise AssertionError(f"Live document never persisted {expected!r} to the server (last: {markdown!r})")
