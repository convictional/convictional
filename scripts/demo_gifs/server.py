import asyncio
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import httpx

HOST = "127.0.0.1"
STARTUP_TIMEOUT = 40  # seconds — includes app boot; assets are prebuilt by the make target
READINESS_HTTP_TIMEOUT = 5


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((HOST, port)) == 0


async def _wait_until_ready(client: httpx.AsyncClient, port: int, log: Path) -> None:
    deadline = time.time() + STARTUP_TIMEOUT
    last_exc: Exception | None = None
    while time.time() < deadline:
        # TCP pre-check avoids a burst of connection-refused errors while uvicorn binds.
        if _port_open(port):
            try:
                resp = await client.get("/", timeout=READINESS_HTTP_TIMEOUT)
                if resp.status_code < 500:
                    return
            except Exception as e:  # noqa: BLE001 — surfaced only if we time out
                last_exc = e
        await asyncio.sleep(0.1)
    tail = log.read_text(errors="replace")[-2000:]
    raise RuntimeError(f"Server failed to start within {STARTUP_TIMEOUT}s: {last_exc}\n--- uvicorn log ---\n{tail}")


@asynccontextmanager
async def dev_server() -> AsyncIterator[str]:
    """Boot a static (no-Vite) dev server against the development DB on a free port.

    Assets must already be built for /static/build (the make target does this).
    Fake auth is enabled by .env.development, which is how we log in as a seed user.
    """
    port = _free_port()
    base_url = f"http://{HOST}:{port}"

    env = os.environ.copy()
    env.update(
        {
            "ENV": "development",
            "ASSET_BUILDING_ENABLED": "False",
            "BASE_URL": base_url,
            "PYTHONUNBUFFERED": "1",
        }
    )
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        HOST,
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    log_file = tempfile.NamedTemporaryFile(prefix="demo_gifs_uvicorn_", suffix=".log", mode="w", delete=False)
    log_path = Path(log_file.name)
    proc = subprocess.Popen(command, env=env, stdout=log_file, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        async with httpx.AsyncClient(base_url=base_url, follow_redirects=True) as client:
            await _wait_until_ready(client, port, log_path)
        yield base_url
    finally:
        with suppress(Exception):
            os.killpg(proc.pid, signal.SIGTERM)
        with suppress(Exception):
            proc.wait(timeout=5)
        with suppress(Exception):
            os.killpg(proc.pid, signal.SIGKILL)
        log_file.close()
        log_path.unlink(missing_ok=True)
