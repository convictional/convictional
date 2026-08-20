import asyncio
from typing import Any, cast

import pytest
from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import DictLoader, Environment, select_autoescape
from starlette.websockets import WebSocket, WebSocketState

from app.channels.base import ChannelRouter, SafeWebSocket, WebSocketSession, channels
from app.routers.dependencies import Authentication, Channel, Helpers, handle_stream
from config.enums import ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_get_current_user_backfills_timezone_from_browser_cookie(client: AppClient):
    user = await client.get_default_user()

    async def reset_timezone(value: str | None) -> None:
        user.time_zone = value
        await user.save(update_fields=["time_zone", "updated_at"])

    # Backfills when user has no zone and the cookie is valid.
    await reset_timezone(None)
    client.cookies.set("timezone", "America/New_York")
    await client.get("/")
    await user.refresh_from_db()
    assert user.time_zone == "America/New_York"

    # Leaves an existing zone alone, even if the cookie disagrees.
    await reset_timezone("Europe/London")
    client.cookies.set("timezone", "America/New_York")
    await client.get("/")
    await user.refresh_from_db()
    assert user.time_zone == "Europe/London"

    # Skips invalid cookie values rather than persisting garbage.
    await reset_timezone(None)
    client.cookies.set("timezone", "Not/A_Real_Zone")
    await client.get("/")
    await user.refresh_from_db()
    assert user.time_zone is None


@pytest.mark.asyncio
async def test_soft_deleted_user_authentication():
    user = await create_user()
    await user.fetch_related("oauth_tokens")
    request = Request(scope={"type": "http", "session": {"user_id": str(user.id)}})

    # Test valid authentication with a non-deleted user
    authentication = Authentication(request)
    await authentication.load()
    assert authentication.current_user is not None
    assert authentication.current_user.id == user.id
    assert await authentication.has_valid_login()

    # Test invalid authentication with a soft-deleted user
    await user.soft_delete()
    await user.fetch_related("oauth_tokens")
    authentication = Authentication(request)
    await authentication.load()
    assert authentication.current_user is None
    assert not await authentication.has_valid_login()

    # Test invalid authentication with a soft-deleted user and a valid session
    request = Request(scope={"type": "http", "session": {"user_id": str(user.id)}})
    authentication = Authentication(request)
    authentication.current_user = user
    assert not await authentication.has_valid_login()
    await authentication._ensure_valid_session()
    assert authentication.current_user is None


#
# Channel router extension tests
#


@pytest.fixture(autouse=True)
def cleanup_channels():
    original_broadcast_handlers = channels.broadcast_handlers.copy()
    yield
    channels.broadcast_handlers.clear()
    channels.broadcast_handlers.update(original_broadcast_handlers)


def create_test_helpers(user):
    test_templates = Jinja2Templates(
        env=Environment(
            loader=DictLoader(
                {
                    "test.html": "<div>{{ message }}</div>",
                    "swap_test.html": "<span id='{{ target_id }}'>{{ content }}</span>",
                }
            ),
            autoescape=select_autoescape(["html"]),
        )
    )

    mock_request = Request(
        scope={"type": "http", "method": "GET", "path": "/test", "headers": [], "query_string": b"", "session": {}}
    )
    authentication = Authentication(mock_request)
    authentication.current_user = user
    return Helpers(connection=mock_request, templates=test_templates, authentication=authentication)


def create_channel(user, topic=None):
    if topic is None:
        topic = Topic("test_stream", workspace_id="123")

    helpers = create_test_helpers(user)
    authentication = helpers.authentication
    context = {"helpers": helpers, "authentication": authentication}

    class MockWebSocket:
        def __init__(self):
            self.sent_messages: list[Any] = []

        @property
        def application_state(self):
            return WebSocketState.CONNECTED

        @property
        def client_state(self):
            return WebSocketState.CONNECTED

        async def send_json(self, message: Any) -> None:
            self.sent_messages.append(message)

        async def receive_json(self) -> dict:
            return {"type": "test"}

        async def accept(self) -> None:
            pass

    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, context)

    return Channel(topic, session, {}, helpers=helpers, authentication=authentication), mock_websocket


@pytest.mark.asyncio
async def test_handle_stream_decorator():
    @handle_stream("test_decorator")
    async def test_handler(channel: Channel, **data):
        pass

    assert "test_decorator" in channels.broadcast_handlers


@pytest.mark.asyncio
async def test_subscription_with_topic_handler(client: AppClient):
    # Setup a test channel handler that accepts subscriptions
    router = ChannelRouter()
    received_topics = []

    @router.on_subscribe("topic_test")
    async def topic_test_handler(channel):
        await channel.accept()

    @handle_stream("topic_test")
    async def handle_topic(channel: Channel, **data):
        received_topics.append((channel.topic, data))

    channels.include_router(router)

    # Create a channel
    topic = Topic("topic_test", workspace_id="456")

    async with client.connect_websocket("/channels") as websocket:
        # Subscribe to channel
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)

        # Confirm subscription
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response["topic_stream"] == topic.stream

        # Verify topic handler is registered
        assert "topic_test" in channels.broadcast_handlers


@pytest.mark.asyncio
async def test_unsubscribe_stops_broadcasts(client: AppClient):
    router = ChannelRouter()
    received_messages = []
    first_message_received = asyncio.Event()

    @router.on_subscribe("test_unsubscribe")
    async def test_unsubscribe_handler(channel):
        await channel.accept()

    @handle_stream("test_unsubscribe")
    async def handle_broadcast(channel: Channel, **data):
        received_messages.append(data)
        if len(received_messages) == 1:
            first_message_received.set()

    channels.include_router(router)

    topic = Topic("test_unsubscribe", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Subscribe to channel
        await websocket.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED

        # Send a broadcast - should be received
        await topic.broadcast(message="before_unsubscribe")
        await asyncio.wait_for(first_message_received.wait(), timeout=1.0)
        assert len(received_messages) == 1

        # Unsubscribe
        await websocket.send_json({"type": "unsubscribe", "topic_stream": topic.stream, "topic_params": topic.params})

        # Wait briefly to ensure the second message would have been processed if subscription was active
        try:
            await asyncio.wait_for(asyncio.sleep(0.1), timeout=0.2)
        except TimeoutError:
            pass

        # Send another broadcast - should not be received
        await topic.broadcast(message="after_unsubscribe")

        # Wait briefly to ensure the second message would have been processed if subscription was active
        try:
            await asyncio.wait_for(asyncio.sleep(0.1), timeout=0.2)
        except TimeoutError:
            pass

        assert len(received_messages) == 1  # Still only 1 message
