import asyncio
import hashlib
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from enum import StrEnum
from typing import Any, Protocol, Self
from uuid import uuid4 as generate_uuid

from asyncpg import Connection
from tortoise import connections
from tortoise.backends.asyncpg.client import AsyncpgDBClient

from config import logger
from infra.cache import cache
from lib.json import JSONDumps, JSONLoads

MESSAGE_QUEUE_MAX_SIZE = 1000
POSTGRES_TOPIC_NAME_MAX_BYTES = 63
POSTGRES_TOPIC_NAME_VALID_CHARS = re.compile(r"[^A-Za-z0-9_]")
POSTGRES_TOPIC_NAME_HASH_LENGTH = 8
TOPIC_NAME_SEPARATOR = ":"


# PostgreSQL NOTIFY has an 8000 byte limit, but we use a conservative limit
# to account for JSON encoding overhead and other metadata
MAX_NOTIFY_PAYLOAD_SIZE = 7000


class Topic:
    def __init__(self, stream: str, **params):
        self.stream = stream
        self.params = {k: str(v) for k, v in params.items()}

    @classmethod
    def from_name(cls, name: str) -> Self:
        parts = name.split(TOPIC_NAME_SEPARATOR, 1)
        if len(parts) == 1:
            return cls(parts[0])

        stream = parts[0]
        params = {}
        param_parts = parts[1].split(TOPIC_NAME_SEPARATOR)

        for i in range(0, len(param_parts), 2):
            if i + 1 < len(param_parts):
                key = param_parts[i]
                value = param_parts[i + 1]
                params[key] = value

        return cls(stream, **params)

    @property
    def name(self) -> str:
        if not self.params:
            return self.stream

        param_str = TOPIC_NAME_SEPARATOR.join(f"{k}{TOPIC_NAME_SEPARATOR}{v}" for k, v in sorted(self.params.items()))
        return f"{self.stream}{TOPIC_NAME_SEPARATOR}{param_str}"

    def matches(self, other: Self) -> bool:
        if not isinstance(other, Topic):
            return False

        return self.stream == other.stream and self.params == other.params

    def __eq__(self, other: Any) -> bool:
        return self.matches(other)

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Topic('{self.stream}', {self.params})"

    async def broadcast(self, **data: Any) -> None:
        if not subscription_adapter:
            logger.error("Subscription adapter not initialized; skipping broadcast", extra=self.log_context())
            return
        await subscription_adapter.broadcast(self.name, data)

    def log_context(self) -> dict[str, Any]:
        return {"topic": self.name, "stream": self.stream, **{f"topic_param_{k}": v for k, v in self.params.items()}}


SubscriptionCallback = Callable[[Any], Awaitable[None]]


class SubscriptionAdapter(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def subscribe(self, topic_name: str, callback: SubscriptionCallback) -> None: ...
    async def unsubscribe(self, topic_name: str, callback: SubscriptionCallback) -> None: ...
    async def broadcast(self, topic_name: str, data: Any) -> None: ...


@asynccontextmanager
async def acquire_asyncpg_connection(connection_name: str = "auxiliary") -> AsyncGenerator[Connection]:
    db = connections.get(connection_name)
    if not isinstance(db, AsyncpgDBClient):
        raise RuntimeError(f"Connection '{connection_name}' is {type(db).__name__}, not AsyncpgDBClient")

    async with db.acquire_connection() as connection:
        yield connection


class SubscriptionAction(StrEnum):
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"


@dataclass
class SubscriptionCommand:
    action: SubscriptionAction
    topic_name: str
    callback: SubscriptionCallback
    done: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class PostgreSQLSubscriptionAdapter:
    _callback_wrappers: dict[tuple[str, SubscriptionCallback], Callable] = field(default_factory=dict, init=False)
    _command_queue: asyncio.Queue[SubscriptionCommand] = field(default_factory=asyncio.Queue, init=False)
    started: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _listen_task: asyncio.Task | None = field(default=None, init=False)

    async def start(self) -> None:
        if self.started.is_set():
            return
        self._listen_task = asyncio.create_task(self._listen_loop())
        await self.started.wait()

    async def stop(self) -> None:
        if not self.started.is_set():
            return
        self._command_queue.shutdown()

        # Ensure listen loop completes
        if self._listen_task:
            await self._listen_task

    async def subscribe(self, topic_name: str, callback: SubscriptionCallback):
        command = SubscriptionCommand(action=SubscriptionAction.SUBSCRIBE, topic_name=topic_name, callback=callback)

        await self._command_queue.put(command)
        await command.done.wait()  # Wait for the command to be processed

    async def unsubscribe(self, topic_name: str, callback: SubscriptionCallback) -> None:
        command = SubscriptionCommand(action=SubscriptionAction.UNSUBSCRIBE, topic_name=topic_name, callback=callback)

        await self._command_queue.put(command)
        await command.done.wait()  # Wait for the command to be processed

    async def _listen_loop(self):
        while True:
            try:
                async with acquire_asyncpg_connection() as connection:
                    try:
                        for (topic_name, callback), wrapped_callback in self._callback_wrappers.items():
                            await connection.add_listener(topic_name, wrapped_callback)

                        self.started.set()

                        # Process commands and wait for stop signal
                        await self._process_commands_loop(connection)
                    finally:
                        for (topic_name, callback), wrapped_callback in self._callback_wrappers.items():
                            await connection.remove_listener(topic_name, wrapped_callback)
            except asyncio.QueueShutDown:
                break
            except Exception as e:
                logger.warning(f"Connection lost in _listen_loop: {e}. Will retry.")
                await asyncio.sleep(1)

    def _create_wrapped_callback(self, callback: SubscriptionCallback) -> Callable:
        async def wrapped_callback(con_ref: Any, pid: int, channel: str, payload: Any):
            try:
                data = JSONLoads(payload)
                if isinstance(data, dict) and "_cache_key" in data:
                    cached_message = await cache.read(data["_cache_key"])
                    if cached_message is None:
                        logger.warning(
                            f"Cache key '{data['_cache_key']}' not found for large message on channel '{channel}'"
                        )
                        return
                    data = JSONLoads(cached_message)
                await callback(data)
            except Exception:
                logger.exception(f"Error processing message on channel '{channel}': {payload}")

        return wrapped_callback

    async def _process_commands_loop(self, connection: Connection):
        while True:
            command = await self._command_queue.get()

            await self._process_command(connection, command)

    async def _process_command(self, connection: Connection, command: SubscriptionCommand):
        topic_name = create_postgres_topic_name(command.topic_name)

        if command.action == SubscriptionAction.SUBSCRIBE:
            wrapped_callback = self._create_wrapped_callback(command.callback)
            self._callback_wrappers[(topic_name, command.callback)] = wrapped_callback
            await connection.add_listener(topic_name, wrapped_callback)
        elif command.action == SubscriptionAction.UNSUBSCRIBE:
            try:
                wrapped_callback = self._callback_wrappers.pop((topic_name, command.callback))
                await connection.remove_listener(topic_name, wrapped_callback)
            except KeyError:
                logger.warning(f"Callback for topic '{topic_name}' not found, cannot unsubscribe")

        command.done.set()

    async def broadcast(self, topic_name: str, data: Any) -> None:
        postgres_topic_name = create_postgres_topic_name(topic_name)
        message = JSONDumps(data)

        if len(message.encode("utf-8")) > MAX_NOTIFY_PAYLOAD_SIZE:
            cache_key = f"messaging_payloads:{topic_name}:{str(generate_uuid())}"
            await cache.write(cache_key, message, timedelta(hours=24))
            message = JSONDumps({"_cache_key": cache_key})

        escaped_message = message.replace("'", "''")
        async with acquire_asyncpg_connection() as connection:
            await connection.execute(f"NOTIFY \"{postgres_topic_name}\", '{escaped_message}'")


def create_postgres_topic_name(logical_name: str) -> str:
    # Clean up the logical name to be a valid PostgreSQL identifier
    logical = POSTGRES_TOPIC_NAME_VALID_CHARS.sub("_", logical_name)
    if not logical:
        logical = "_"
    elif not (logical[0].isalpha() or logical[0] == "_"):
        logical = "_" + logical
    logical = logical.lower()

    if len(logical.encode("utf-8")) <= POSTGRES_TOPIC_NAME_MAX_BYTES:
        return logical

    hash_suffix = hashlib.sha256(logical.encode("utf-8")).hexdigest()[:POSTGRES_TOPIC_NAME_HASH_LENGTH]
    prefix_bytes = POSTGRES_TOPIC_NAME_MAX_BYTES - POSTGRES_TOPIC_NAME_HASH_LENGTH - 1
    prefix = logical.encode("utf-8")[:prefix_bytes].decode("utf-8", "ignore")

    return f"{prefix}_{hash_suffix}"


subscription_adapter: PostgreSQLSubscriptionAdapter | None = None


async def subscribe(topic: Topic, callback: SubscriptionCallback) -> None:
    if not subscription_adapter:
        raise RuntimeError("Subscription adapter not initialized")
    return await subscription_adapter.subscribe(topic.name, callback)


async def unsubscribe(topic: Topic, callback: SubscriptionCallback) -> None:
    if not subscription_adapter:
        raise RuntimeError("Subscription adapter not initialized")
    return await subscription_adapter.unsubscribe(topic.name, callback)


async def start_subscription() -> None:
    global subscription_adapter
    # Start a new one because asyncio events are loop-scoped
    subscription_adapter = PostgreSQLSubscriptionAdapter()
    """Start the subscription adapter."""
    await subscription_adapter.start()


async def stop_subscription() -> None:
    if not subscription_adapter:
        raise RuntimeError("Subscription adapter not initialized")
    """Stop the subscription adapter."""
    await subscription_adapter.stop()
