import asyncio
from collections.abc import Awaitable, Callable, ItemsView
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Protocol, TypeVar

from fastapi import status
from pydantic import BaseModel, Field, computed_field
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState
from tortoise.exceptions import DoesNotExist

from app.models.accounts import User
from config import logger, settings
from config.enums import ChannelMessageType
from config.logging import LoggingContext
from infra.messaging import Topic, subscribe, unsubscribe
from infra.server import stop_event as server_stop_event

if settings.sentry_dsn:
    import sentry_sdk

#
# Channels
#
#

LISTENER_CLEANUP_TIMEOUT_SECONDS = 1.0

message_type_registry: dict[ChannelMessageType, type["BaseChannelMessage"]] = {}


class BaseChannelMessage(BaseModel):
    _message_type: ClassVar[ChannelMessageType]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def type(self) -> ChannelMessageType:
        return self._message_type

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "_message_type"):
            message_type_registry[cls._message_type] = cls

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BaseChannelMessage":
        """Deserialize a dictionary into the appropriate message type."""
        message_type = data.get("type")
        if not message_type:
            raise ValueError("Message must have a 'type' field")

        message_class = message_type_registry.get(message_type)
        if not message_class:
            raise ValueError(f"Unknown message type: {message_type}")

        return message_class(**data)


class ChannelMessage(BaseChannelMessage):
    # A channel message identifies its topic by its `topic_stream` + `topic_params` — the client
    # names the topic from IDs it already holds, and the subscribe handler authorizes the params
    # against the authenticated user.
    topic_stream: str | None = None
    topic_params: dict[str, str] = Field(default_factory=dict)

    @property
    def topic(self) -> Topic:
        if self.topic_stream is not None:
            return Topic(self.topic_stream, **self.topic_params)
        raise ValueError("channel message requires topic_stream")


BaseChannelMessageModel = TypeVar("BaseChannelMessageModel", bound=BaseChannelMessage)
ChannelMessageModel = TypeVar("ChannelMessageModel", bound=ChannelMessage)


class SubscribeMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.SUBSCRIBE
    params: dict[str, Any] = Field(default_factory=dict)

    async def process(self, session: "WebSocketSession") -> None:
        if self.topic_stream is None:
            # A subscribe frame without topic_stream can't name a topic: it's a malformed
            # client request, not a server fault. Reject it at the boundary rather than
            # letting the missing topic surface deeper in the handler as a ValueError that
            # gets logged to Sentry as an internal error.
            await session.send(
                SubscriptionRejectedMessage(
                    topic_stream=None,
                    topic_params=self.topic_params,
                    error="subscribe requires topic_stream",
                )
            )
            return
        try:
            await self._handle_channel_subscription(session)
        except Exception:
            logger.exception("Error processing subscription")
            await session.send(
                SubscriptionRejectedMessage(
                    topic_stream=self.topic_stream,
                    topic_params=self.topic_params,
                    error="Failed to process subscription",
                )
            )

    async def _handle_channel_subscription(self, session: "WebSocketSession") -> None:
        was_handled = await channels.subscribe_handlers.execute(
            self.topic.stream, self.topic, session, self.params, require_decision=True
        )
        if not was_handled:
            await session.send(
                SubscriptionRejectedMessage(
                    topic_stream=self.topic.stream, topic_params=self.topic.params, error="No handler found"
                )
            )


class UnsubscribeMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.UNSUBSCRIBE

    async def process(self, session: "WebSocketSession") -> None:
        if self.topic_stream is None:
            # Same malformed-frame guard as SubscribeMessage: without a topic_stream there is
            # nothing to unsubscribe from, and accessing self.topic would raise the same
            # ValueError. Drop the frame instead of reporting a client error as a server fault.
            return
        try:
            await self._handle_unsubscribe(self.topic, session)
        except Exception:
            logger.exception("Error processing unsubscribe")

    async def _handle_unsubscribe(self, topic: Topic, session: "WebSocketSession") -> None:
        params = {}
        subscription = session.subscriptions.get(topic)
        if subscription:
            params = subscription.channel.params

        with LoggingContext(session.websocket.connection, topic, channel_handler="unsubscribe"):
            await channels.unsubscribe_handlers.execute(topic.stream, topic, session, params)

        if subscription:
            await subscription.stop()


class SubscriptionConfirmedMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.SUBSCRIPTION_CONFIRMED


class SubscriptionRejectedMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.SUBSCRIPTION_REJECTED
    error: str


class PingMessage(BaseChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.PING


class PongMessage(BaseChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.PONG
    data: str


class AssetVersionInfoMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.ASSET_VERSION_INFO
    version: str


class AssetVersionChangedMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.ASSET_VERSION_CHANGED
    version: str


class BroadcastHandler(Protocol):
    async def __call__(self, channel: "Channel", **data: Any) -> None: ...


class TemplateRenderer(Protocol):
    def __call__(self, template: str, **kwargs: Any) -> str: ...


@dataclass
class HandlerRegistry:
    handlers: dict[Any, list[Callable]] = field(default_factory=dict)

    def add(self, key: Any, handler: Callable) -> None:
        self.handlers.setdefault(key, []).append(handler)

    def extend(self, other: "HandlerRegistry") -> None:
        for key, handler_list in other.items():
            self.handlers.setdefault(key, []).extend(handler_list)

    def __contains__(self, key: Any) -> bool:
        return key in self.handlers

    def items(self) -> ItemsView[Any, list[Callable]]:
        return self.handlers.items()

    def clear(self) -> None:
        self.handlers.clear()

    def copy(self) -> dict[Any, list[Callable]]:
        return {k: list(v) for k, v in self.handlers.items()}

    # Overwrites keys present in other — used by test fixtures after clear() to restore from copy().
    def update(self, other: dict[Any, list[Callable]]) -> None:
        for key, handler_list in other.items():
            self.handlers[key] = list(handler_list)

    async def execute(
        self,
        key: Any,
        topic: Topic,
        session: "WebSocketSession",
        params: dict,
        handler_kwargs: dict | None = None,
        message: Any = None,
        require_decision: bool = False,
    ) -> bool:
        handlers = self.handlers.get(key)
        if not handlers:
            return False

        kwargs = handler_kwargs or {}
        channel = Channel(topic, session, params)
        for handler in handlers:
            try:
                if message is not None:
                    await handler(channel, message, **kwargs)
                else:
                    await handler(channel, **kwargs)
            except DoesNotExist:
                logger.warning(f"Handler for {key} raised DoesNotExist")
            except Exception:
                logger.exception(f"Handler for {key} failed")

        # Fail closed: a subscribe handler that never accepted or rejected has left the
        # subscription unauthorized. Reject explicitly rather than leaving the client hanging
        # (or, worse, silently subscribed), and surface the omission to Sentry.
        if require_decision and not channel._decided:
            logger.error(f"Subscribe handler for {key} returned without accept() or reject(); rejecting")
            await channel.reject("subscription not authorized")

        return True


@dataclass
class ChannelRouter:
    subscribe_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    unsubscribe_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    keepalive_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    receive_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)

    def on_subscribe(self, stream: str | None = None):
        def decorator(func: Callable[[Channel], Awaitable[None]]):
            name = stream or func.__name__
            self.subscribe_handlers.add(name, func)
            return func

        return decorator

    def on_unsubscribe(self, stream: str | None = None):
        def decorator(func: Callable[[Channel], Awaitable[None]]):
            name = stream or func.__name__
            self.unsubscribe_handlers.add(name, func)
            return func

        return decorator

    def on_keepalive(self, stream: str | None = None):
        def decorator(func: Callable[[Channel], Awaitable[None]]):
            name = stream or func.__name__
            self.keepalive_handlers.add(name, func)
            return func

        return decorator

    def on_receive(self, stream: str, message: type[ChannelMessageModel]):
        def decorator(
            func: Callable[["Channel", ChannelMessageModel], Awaitable[None]],
        ) -> Callable[["Channel", ChannelMessageModel], Awaitable[None]]:
            key = (stream, message._message_type)
            self.receive_handlers.add(key, func)
            return func

        return decorator


@dataclass
class Channel:
    topic: Topic
    session: "WebSocketSession"
    params: dict[str, Any] = field(default_factory=dict)
    # Set once the handler reaches an explicit accept()/reject(). With unsigned topic
    # subscription the handler is the only authorization boundary, so the registry fails
    # closed if a subscribe handler returns without deciding (see HandlerRegistry.execute).
    _decided: bool = field(default=False, init=False)

    @property
    def current_user(self):
        return self.session.current_user

    async def accept(self):
        self._decided = True
        subscription = await self.session.subscribe_to(self)
        await self.session.send(
            SubscriptionConfirmedMessage(topic_stream=self.topic.stream, topic_params=self.topic.params)
        )
        return subscription

    async def reject(self, error: str):
        self._decided = True
        await self.session.send(
            SubscriptionRejectedMessage(topic_stream=self.topic.stream, topic_params=self.topic.params, error=error)
        )

    def get_param(self, key: str, default=None):
        # Topic params (the subscription identity) take precedence over the looser SubscribeMessage params.
        if self.topic.params and key in self.topic.params:
            return self.topic.params[key] or default

        return self.params.get(key, default)


@dataclass
class ChannelSubscription:
    session: "WebSocketSession"
    channel: "Channel"
    callback: Callable[[Any], Awaitable[None]] | None = field(default=None, init=False)

    @property
    def topic(self) -> Topic:
        return self.channel.topic

    async def start(self):
        subscription_context = {"topic": self.topic.name, "stream": self.topic.stream}

        if settings.sentry_dsn:
            sentry_sdk.set_context("Channel", subscription_context)

        with LoggingContext(self.session.websocket.connection, self.topic, channel_handler="subscribe"):

            async def callback(data: Any):
                if settings.sentry_dsn:
                    sentry_sdk.add_breadcrumb(
                        category="websocket",
                        message=f"Broadcast: {self.topic.stream}",
                        level="info",
                    )
                await channels.broadcast_handlers.execute(
                    self.topic.stream, self.topic, self.session, self.channel.params, handler_kwargs=data
                )

            self.callback = callback
            await subscribe(self.topic, callback)

    async def stop(self):
        if not self.callback:
            return
        await unsubscribe(self.topic, self.callback)
        await self.session._remove_subscription(self)


@dataclass
class ChannelsApp:
    subscribe_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    unsubscribe_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    broadcast_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    keepalive_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)
    receive_handlers: HandlerRegistry = field(default_factory=HandlerRegistry)

    def include_router(self, router: ChannelRouter):
        self.subscribe_handlers.extend(router.subscribe_handlers)
        self.unsubscribe_handlers.extend(router.unsubscribe_handlers)
        self.keepalive_handlers.extend(router.keepalive_handlers)
        self.receive_handlers.extend(router.receive_handlers)

    def reset(self):
        self.subscribe_handlers.clear()
        self.unsubscribe_handlers.clear()
        self.broadcast_handlers.clear()
        self.receive_handlers.clear()
        self.keepalive_handlers.clear()


channels = ChannelsApp()

#
# WebSockets
#
#

WEBSOCKET_SEND_TIMEOUT_SECONDS = 5.0
WEBSOCKET_RECEIVE_TIMEOUT_SECONDS = 5.0
WEBSOCKET_PING_INTERVAL_SECONDS = 30.0
WEBSOCKET_KEEP_ALIVE_TIMEOUT_SECONDS = 90.0


@dataclass
class SafeWebSocket:
    connection: WebSocket

    @property
    def is_open(self) -> bool:
        return (
            self.connection.application_state == WebSocketState.CONNECTED
            and self.connection.client_state == WebSocketState.CONNECTED
        )

    async def send_json_safe(self, payload: Any, *, timeout: float = WEBSOCKET_SEND_TIMEOUT_SECONDS) -> bool:
        """
        This is a best-effort, exception-safe function to send a JSON payload.
        If the client is disconnected or the send times out, it returns False.
        """
        if not self.is_open:
            return False

        try:
            await asyncio.wait_for(self.connection.send_json(payload), timeout)
            return True
        except (TimeoutError, WebSocketDisconnect):
            return False

    async def receive_json_safe(self, *, timeout: float = WEBSOCKET_RECEIVE_TIMEOUT_SECONDS) -> Any | None:
        """
        This is a function that *only* raises when the client needs to do an orderly close around the WebSocket.
        Handle the WebSocketDisconnect exception in the caller to do any necessary cleanup.
        """
        if not self.is_open:
            raise WebSocketDisconnect(code=status.WS_1006_ABNORMAL_CLOSURE)

        try:
            return await asyncio.wait_for(self.connection.receive_json(), timeout)
        except TimeoutError:
            return None


@dataclass
class WebSocketSession:
    websocket: SafeWebSocket
    current_user: User
    context: dict[str, Any] = field(default_factory=dict)
    subscriptions: dict[Topic, ChannelSubscription] = field(default_factory=dict, init=False)
    stop: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    last_pong_time: datetime | None = field(default=None, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    async def handle(self) -> None:
        async with asyncio.TaskGroup() as task_group:
            task_group.create_task(self._keep_alive())
            await self._message_loop(task_group)

    async def subscribe_to(self, channel: "Channel"):
        """
        Subscribe to a channel and return the subscription object.
        If already subscribed, returns the existing subscription.
        This method is thread-safe and uses a lock to ensure that subscriptions are managed correctly.
        """
        async with self._lock:
            if channel.topic in self.subscriptions:
                return self.subscriptions[channel.topic]

            subscription = ChannelSubscription(self, channel)
            self.subscriptions[channel.topic] = subscription
            await subscription.start()
            return subscription

    async def send(self, message: BaseChannelMessage) -> bool:
        return await self.websocket.send_json_safe(message.model_dump())

    async def cleanup(self) -> None:
        """
        Clean up all subscriptions and their associated tasks.
        This method is called when the WebSocket session ends, either due to disconnection or normal closure.
        """
        async with self._lock:
            subscriptions = list(self.subscriptions.values())
            self.subscriptions.clear()

        for subscription in subscriptions:
            with LoggingContext(self.websocket.connection, subscription.topic, channel_handler="unsubscribe"):
                await channels.unsubscribe_handlers.execute(
                    subscription.topic.stream, subscription.topic, self, subscription.channel.params
                )
                await subscription.stop()

        self.stop.set()

    async def _remove_subscription(self, subscription: ChannelSubscription):
        async with self._lock:
            self.subscriptions.pop(subscription.topic, None)

    async def _message_loop(self, task_group: asyncio.TaskGroup) -> None:
        try:
            while not server_stop_event.is_set():
                data = await self.websocket.receive_json_safe()
                if data:
                    message = BaseChannelMessage.from_dict(data)
                    task_group.create_task(self._process_message(message))
            # Server is shutting down; close the socket so the client reconnects to the new revision
            # before Cloud Run sends SIGKILL and we tear down the DB pool mid-query.
            if self.websocket.connection.client_state == WebSocketState.CONNECTED:
                await self.websocket.connection.close(code=status.WS_1012_SERVICE_RESTART)
        except WebSocketDisconnect:
            pass
        finally:
            await self.cleanup()

    async def _process_message(self, message: BaseChannelMessage) -> None:
        if isinstance(message, SubscribeMessage):
            if settings.sentry_dsn:
                sentry_sdk.add_breadcrumb(
                    category="websocket",
                    message=f"Subscribe: {message.topic_stream}",
                    level="info",
                )
            try:
                await message.process(self)
            except Exception:
                logger.exception("Error processing subscribe message")
            return

        if isinstance(message, UnsubscribeMessage):
            if settings.sentry_dsn:
                sentry_sdk.add_breadcrumb(
                    category="websocket",
                    message=f"Unsubscribe: {message.topic_stream}",
                    level="info",
                )
            try:
                await message.process(self)
            except Exception:
                logger.exception("Error processing unsubscribe message")
            return

        if isinstance(message, PongMessage):
            self.last_pong_time = datetime.now(UTC)
            await self._route_keepalive()
            return

        if isinstance(message, ChannelMessage):
            await self._route_client_message(message)
            return

        logger.warning(f"Received unknown message type: {message.type}")

    async def _route_client_message(self, message: ChannelMessage):
        if message.topic_stream is None:
            # A topic-less client message (e.g. a `typing`/`yjs_awareness` frame with no
            # topic_stream) can't name a channel. Unlike the subscribe/unsubscribe branches in
            # _process_message, this routing path has no surrounding try/except, so the ValueError
            # from `message.topic` below would escape into the TaskGroup and tear down the whole
            # session. Drop the malformed frame at the boundary, like SubscribeMessage/UnsubscribeMessage.
            return
        topic = message.topic
        subscription_context = {"topic": topic.name, "stream": topic.stream}

        if settings.sentry_dsn:
            sentry_sdk.set_context("Channel", subscription_context)
            sentry_sdk.add_breadcrumb(
                category="websocket",
                message=f"Received: {message.type} on {topic.stream}",
                level="info",
            )

        with LoggingContext(self.websocket.connection, topic, channel_handler="receive", message_type=message.type):
            async with self._lock:
                subscription = self.subscriptions.get(topic)
                if not subscription:
                    logger.warning(f"Received message for unknown or inactive channel: {topic.name}")
                    return

                await channels.receive_handlers.execute(
                    (topic.stream, message.type), topic, self, subscription.channel.params, message=message
                )

    async def _route_keepalive(self):
        async with self._lock:
            for subscription in self.subscriptions.values():
                with LoggingContext(self.websocket.connection, subscription.topic, channel_handler="keepalive"):
                    await channels.keepalive_handlers.execute(
                        subscription.topic.stream, subscription.topic, self, subscription.channel.params
                    )

    async def _keep_alive(self) -> None:
        self.last_pong_time = datetime.now(UTC)
        while self.websocket.is_open:
            try:
                await asyncio.wait_for(self.stop.wait(), timeout=WEBSOCKET_PING_INTERVAL_SECONDS)
                break
            except TimeoutError:
                time_since_pong = datetime.now(UTC) - self.last_pong_time
                if time_since_pong.total_seconds() > WEBSOCKET_KEEP_ALIVE_TIMEOUT_SECONDS:
                    logger.warning(f"No pong received for {time_since_pong.total_seconds():.1f}s, closing connection")
                    if self.websocket.connection.client_state == WebSocketState.CONNECTED:
                        await self.websocket.connection.close(code=status.WS_1000_NORMAL_CLOSURE)
                    break
                if not await self.send(PingMessage()):
                    break
