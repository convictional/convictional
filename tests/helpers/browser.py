import asyncio
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pytest_asyncio
from fastapi import status
from PIL import Image
from playwright.async_api import Browser, Locator, Page, expect

from config import settings

BROWSER_TEST_HOST = "127.0.0.1"
BROWSER_TEST_STARTUP_TIMEOUT = 25  # seconds
BROWSER_READINESS_PATH = "/"
BROWSER_TEST_READINESS_TIMEOUT = 5  # seconds
BROWSER_TEST_SHUTDOWN_TIMEOUT = 5  # seconds

expect.set_options(timeout=settings.browser_test_default_timeout)


def _free_port() -> int:
    server_socket = socket.socket()
    server_socket.bind(("", 0))
    port = server_socket.getsockname()[1]
    server_socket.close()
    return port


async def _wait_until_ready(
    client: httpx.AsyncClient, host: str, port: int, startup_timeout: float, http_timeout: float, readiness_path: str
) -> None:
    deadline = time.time() + startup_timeout
    last_exc: Exception | None = None

    while time.time() < deadline:
        # TCP bind check (fast/cheap)
        try:
            _, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
        except Exception as e:
            last_exc = e
            await asyncio.sleep(0.05)
            continue

        # HTTP readiness
        try:
            resp = await client.get(readiness_path, timeout=http_timeout)
            if resp.status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
                return
        except Exception as e:
            last_exc = e

        await asyncio.sleep(0.1)

    raise RuntimeError(f"Server failed to start within {startup_timeout}s: {last_exc}")


@pytest_asyncio.fixture
async def browser_test_url() -> AsyncIterator[str]:
    port = _free_port()
    base_url = f"http://{BROWSER_TEST_HOST}:{port}"

    env = os.environ.copy()
    env.update({"ENV": "test", "BASE_URL": base_url, "PYTHONUNBUFFERED": "1"})

    uvicorn_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        BROWSER_TEST_HOST,
        "--port",
        str(port),
        "--log-level",
        "warning",
        "--lifespan",
        "on",
    ]

    # Capture combined stdout/stderr to a temp file for debugging later
    log_file = tempfile.NamedTemporaryFile("wb+", delete=False)
    log_path = Path(log_file.name)

    proc = subprocess.Popen(
        uvicorn_command, stdout=log_file, stderr=subprocess.STDOUT, env=env, start_new_session=True
    )

    try:
        async with httpx.AsyncClient(base_url=base_url, follow_redirects=True) as client:
            await _wait_until_ready(
                client=client,
                host=BROWSER_TEST_HOST,
                port=port,
                startup_timeout=BROWSER_TEST_STARTUP_TIMEOUT,
                http_timeout=BROWSER_TEST_READINESS_TIMEOUT,
                readiness_path=BROWSER_READINESS_PATH,
            )

        yield base_url

    finally:
        # Try graceful group shutdown, then escalate.
        with suppress(Exception):
            os.killpg(proc.pid, signal.SIGTERM)
        with suppress(Exception):
            proc.terminate()

        # Wait for process to exit, then escalate.
        try:
            proc.wait(timeout=BROWSER_TEST_SHUTDOWN_TIMEOUT)
        except Exception:
            with suppress(Exception):
                os.killpg(proc.pid, signal.SIGKILL)
            with suppress(Exception):
                proc.kill()

        # Print useful tail if errors or startup issues happened
        try:
            log_file.seek(0)
            contents = log_file.read().decode("utf-8", "replace")
            if "ERROR" in contents or "Traceback" in contents or settings.is_debug:
                tail = contents[-4000:]
                print("\n--- uvicorn stderr/stdout (tail) ---\n" + tail)
        finally:
            log_file.close()
            with suppress(Exception):
                log_path.unlink(missing_ok=True)


@dataclass
class BrowserClient:
    base_url: str
    browser: Browser
    page: Page
    _page_errors: list[str]
    _console_messages: list[str]

    def expect(self, actual: Locator, message: str | None = None):
        return expect(actual, message)

    def test_id_locator(self, test_id: str) -> Locator:
        # Two conventions coexist: HTMX/Alpine templates use `data-test-id` (kebab);
        # React components use `data-testid` (the @testing-library convention shared
        # with JS unit tests). Match either so a single test can talk to both.
        return self.page.locator(f'[data-test-id="{test_id}"], [data-testid="{test_id}"]')

    async def new_context(self):
        context = await self.browser.new_context()

        page = await context.new_page()
        page.set_default_navigation_timeout(settings.browser_test_default_timeout)
        page.set_default_timeout(settings.browser_test_default_timeout)
        page.on("pageerror", self._handle_page_error)
        page.on("console", self._handle_console_message)

        return BrowserClient(
            base_url=self.base_url,
            browser=self.browser,
            page=page,
            _page_errors=self._page_errors,
            _console_messages=self._console_messages,
        )

    async def save_screenshot(self, filename: str | None = None):
        screenshots_dir = settings.root / "tmp" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{timestamp}.png"

        if not filename.endswith(".png"):
            filename += ".png"

        screenshot_path = screenshots_dir / filename
        await self.page.screenshot(path=str(screenshot_path))
        return screenshot_path

    async def save_and_open_screenshot(self):
        screenshot_path = await self.save_screenshot()
        Image.open(screenshot_path).show()

    async def login(self, email: str):
        # Navigate to fake login page
        await self.page.goto(self.base_url)

        # Fill in fake login form
        email_input = self.test_id_locator("fake-login-form").locator("input[name='email']")
        await self.expect(email_input).to_be_visible()
        await email_input.fill(email)
        login_submit = self.test_id_locator("fake-login-form").locator("button[type='submit']")
        await login_submit.click()

        # Wait until we've left the login page. A new/incomplete user is redirected from
        # the inbox root to the getting-started focus (/?mailbox_view_template=...), so an
        # exact-root match would miss the landing; "no longer on /login" covers both.
        await self.page.wait_for_url(lambda url: "/login" not in url, wait_until="domcontentloaded")

    def _handle_page_error(self, error: Any):
        self._page_errors.append(str(error))

    def _handle_console_message(self, msg: Any):
        self._console_messages.append(f"[{msg.type}] {msg.text}")


@pytest_asyncio.fixture
async def browser_client(browser: Browser, page: Page, browser_test_url: str):
    page_errors: list[str] = []
    console_messages: list[str] = []

    def handle_page_error(error):
        page_errors.append(str(error))

    def handle_console_message(msg):
        console_messages.append(f"[{msg.type}] {msg.text}")

    page.on("pageerror", handle_page_error)
    page.on("console", handle_console_message)
    page.set_default_navigation_timeout(settings.browser_test_default_timeout)
    page.set_default_timeout(settings.browser_test_default_timeout)

    client = BrowserClient(
        base_url=browser_test_url,
        browser=browser,
        page=page,
        _page_errors=page_errors,
        _console_messages=console_messages,
    )
    yield client

    if page_errors:
        if console_messages:
            console_output = "\n  ".join(console_messages)
            print(f"\n--- Browser console output ---\n  {console_output}")

        error_list = "\n  ".join(page_errors)
        raise AssertionError(f"\n--- Page JavaScript errors ---\n  {error_list}\n")
