import asyncio

import pytest

from infra.server import run_in_background, start_background_worker, stop_background_worker


@pytest.mark.asyncio
async def test_background_tasks_run_in_different_task():
    start_background_worker()

    caller_task = asyncio.current_task()
    background_task_id = None
    execution_complete = asyncio.Event()

    async def task(shutdown_signal: asyncio.Event):
        nonlocal background_task_id
        background_task_id = id(asyncio.current_task())
        execution_complete.set()

    run_in_background(task)
    await asyncio.wait_for(execution_complete.wait(), timeout=1.0)

    assert background_task_id != id(caller_task)

    await stop_background_worker()


@pytest.mark.asyncio
async def test_all_queued_tasks_complete_before_shutdown():
    start_background_worker()

    completed_tasks = []

    async def task(task_id: int, shutdown_signal: asyncio.Event):
        await asyncio.sleep(0.1)
        completed_tasks.append(task_id)

    for i in range(10):
        run_in_background(task, i)

    await stop_background_worker()

    assert len(completed_tasks) == 10
    assert set(completed_tasks) == set(range(10))


@pytest.mark.asyncio
async def test_shutdown_signal_passed_to_tasks():
    start_background_worker()

    received_signal = None
    execution_complete = asyncio.Event()

    async def task_with_signal(shutdown_signal: asyncio.Event):
        nonlocal received_signal
        received_signal = shutdown_signal
        execution_complete.set()

    run_in_background(task_with_signal)
    await asyncio.wait_for(execution_complete.wait(), timeout=1.0)

    assert received_signal is not None
    assert isinstance(received_signal, asyncio.Event)

    await stop_background_worker()


@pytest.mark.asyncio
async def test_tasks_with_args_and_shutdown_signal():
    start_background_worker()

    executed = False
    execution_complete = asyncio.Event()

    async def task_with_args(value: str, shutdown_signal: asyncio.Event):
        nonlocal executed
        assert value == "test"
        assert isinstance(shutdown_signal, asyncio.Event)
        executed = True
        execution_complete.set()

    run_in_background(task_with_args, "test")
    await asyncio.wait_for(execution_complete.wait(), timeout=1.0)

    assert executed

    await stop_background_worker()
