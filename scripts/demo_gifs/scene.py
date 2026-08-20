import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from playwright.async_api import Page

# Capture dimensions. Playwright's CDP screencast records at the CSS viewport resolution
# and fits it into record_video_size (padding, not supersampling), so we capture 1:1.
WIDTH = 780
HEIGHT = 507

# Neutral resting spot where the synthetic cursor first appears once a demo begins.
START_X = WIDTH * 0.5
START_Y = HEIGHT * 0.45


@dataclass
class Scene:
    """The flow-facing view of a recording in progress.

    Wraps the Playwright page and base URL and exposes the demo choreography as methods,
    so a flow reads as a script of deliberate actions rather than raw Playwright calls.
    """

    page: Page
    base_url: str
    show_cursor: bool
    _started: float = field(default_factory=time.monotonic)
    lead_in: float = 0.0

    async def begin(self) -> None:
        # Reveal the cursor at a neutral resting spot (instant move, no glide from the
        # corner) and mark where the demo starts so the load/settle lead-in is trimmed.
        if self.show_cursor:
            await self.move_cursor(START_X, START_Y)
        self.lead_in = time.monotonic() - self._started

    async def goto(self, path: str = "") -> None:
        await self.page.goto(f"{self.base_url}{path}")

    async def wait(self, selector: str) -> None:
        await self.page.locator(selector).first.wait_for(state="visible")

    async def wait_url(self, pattern: str) -> None:
        await self.page.wait_for_url(pattern, wait_until="domcontentloaded")

    async def settle(self, ms: int = 900) -> None:
        await self.page.wait_for_timeout(ms)

    async def move_cursor(self, x: float, y: float) -> None:
        # Instant placement (steps=1), used to reveal the cursor without a glide — e.g.
        # after a navigation re-runs the cursor init script on a fresh document.
        await self.page.mouse.move(x, y, steps=1)

    async def glide_to(self, x: float, y: float) -> None:
        # Stepped move so the synthetic cursor travels smoothly; locator.click()
        # otherwise teleports the pointer.
        await self.page.mouse.move(x, y, steps=25)

    async def click(self, selector: str, *, pause: int = 250) -> None:
        """Glide the cursor to an element's center, pause, then click — so the recording
        shows a deliberate pointer movement rather than an instant jump."""
        locator = self.page.locator(selector).first
        await locator.wait_for(state="visible")
        box = await locator.bounding_box()
        if box:
            await self.glide_to(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            await self.settle(pause)
        await locator.click()

    async def press(self, keys: str) -> None:
        await self.page.keyboard.press(keys)

    async def type(self, selector: str, text: str, *, delay: int) -> None:
        await self.page.locator(selector).first.press_sequentially(text, delay=delay)

    async def freeze_clock(self, when: datetime) -> None:
        await self.page.clock.set_fixed_time(when)

    async def get_json(self, path: str) -> dict[str, Any]:
        response = await self.page.request.get(f"{self.base_url}{path}")
        return await response.json()
