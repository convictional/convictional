import asyncio
import signal
from collections.abc import Callable, Coroutine
from types import FrameType
from typing import Any

from sse_starlette.sse import AppStatus

from config import logger

GRACEFUL_SHUTDOWN_SIGNALS = [
    signal.SIGINT,  # Interrupt from keyboard (Ctrl+C)
    signal.SIGTERM,  # Termination signal
]

stop_event = asyncio.Event()
worker_task: asyncio.Task | None = None


def install_signal_handler(signal_num: int):
    existing_handler = signal.getsignal(signal_num)

    def handler(signum: int, frame: FrameType | None):
        logger.info(f"Signal {signum} received, stopping server")
        stop_event.set()

        # Signal sse_starlette to close SSE connections gracefully.
        # This is needed because replacing signal handlers breaks sse_starlette's
        # ability to detect uvicorn shutdown via signal handler introspection.
        AppStatus.should_exit = True

        if callable(existing_handler):
            existing_handler(signum, frame)

    signal.signal(signal_num, handler)


def install_signal_handlers():
    for sig in GRACEFUL_SHUTDOWN_SIGNALS:
        install_signal_handler(sig)
    logger.info("Signal handlers installed for graceful shutdown")


tasks: asyncio.Queue[tuple[Callable[..., Coroutine[Any, Any, Any]], tuple]] = asyncio.Queue()


async def background_worker(shutdown_signal: asyncio.Event | None = None):
    task_group = asyncio.TaskGroup()
    async with task_group:
        while True:
            try:
                func, args = await tasks.get()
            except asyncio.QueueShutDown:
                break

            async def wrapper(func: Callable[..., Coroutine[Any, Any, Any]], args: tuple):
                try:
                    await func(*args, shutdown_signal=shutdown_signal or asyncio.Event())
                except Exception as e:
                    logger.error(f"Error in background task: {e}")
                finally:
                    tasks.task_done()

            task_group.create_task(wrapper(func, args))


def start_background_worker():
    global tasks, worker_task
    tasks = asyncio.Queue()
    worker_task = asyncio.create_task(background_worker(stop_event))


async def stop_background_worker():
    tasks.shutdown()
    if worker_task:
        await worker_task


def run_in_background(func: Callable[..., Coroutine[Any, Any, Any]], *args: Any) -> None:
    tasks.put_nowait((func, args))
