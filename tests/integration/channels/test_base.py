import asyncio
import json
from datetime import datetime
from typing import Any, cast
from urllib.parse import urlparse

import pytest
from fastapi import status
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from jinja2 import DictLoader, Environment, select_autoescape
from starlette.datastructures import Headers
from starlette.websockets import WebSocket, WebSocketState

from app.channels import base as channels_base
from app.channels.base import (
    BaseChannelMessage,
    Channel,
    ChannelRouter,
    PingMessage,
    PongMessage,
    SafeWebSocket,
    SubscribeMessage,
    WebSocketSession,
    channels,
)
from app.channels.dependencies import TypingMessage
from app.routers.dependencies import Authentication, Helpers
from config.enums import ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import create_user


class MockWebSocket:
    def __init__(self, messages: list[str] = []):
        self.messages = iter(messages)
        self.sent_messages: list[Any] = []

    @property
    def url(self):
        return urlparse("ws://localhost:8000/channels")

    @property
    def headers(self):
        return Headers({"user-agent": "test-agent"})

    @property
    def client(self):
        return None

    @property
    def application_state(self):
        return WebSocketState.CONNECTED

    @property
    def client_state(self):
        return WebSocketState.CONNECTED

    async def send_json(self, message: Any) -> None:
        self.sent_messages.append(message)

    async def receive_json(self) -> dict:
        try:
            message_text = next(self.messages)
            return json.loads(message_text)
        except StopIteration:
            raise Exception("Connection closed")

    async def accept(self) -> None:
        pass


@pytest.fixture(autouse=True)
def cleanup_channels():
    # Store original state of channels
    original_subscribe_handlers = channels.subscribe_handlers.copy()
    original_unsubscribe_handlers = channels.unsubscribe_handlers.copy()
    original_broadcast_handlers = channels.broadcast_handlers.copy()
    original_client_message_handlers = channels.receive_handlers.copy()

    yield
    channels.reset()

    # Restore original state
    channels.subscribe_handlers.update(original_subscribe_handlers)
    channels.unsubscribe_handlers.update(original_unsubscribe_handlers)
    channels.broadcast_handlers.update(original_broadcast_handlers)
    channels.receive_handlers.update(original_client_message_handlers)


def create_test_context(user):
    test_templates = Jinja2Templates(
        env=Environment(
            loader=DictLoader({"test.html": "<div>Test: {{ message }}</div>"}),
            autoescape=select_autoescape(["html"]),
        )
    )
    mock_request = Request(
        scope={"type": "http", "method": "GET", "path": "/test", "headers": [], "query_string": b""}
    )
    authentication = Authentication(mock_request)
    authentication.current_user = user
    helpers = Helpers(connection=mock_request, templates=test_templates, authentication=authentication)

    return {"helpers": helpers, "authentication": authentication}


@pytest.mark.asyncio
async def test_channels_endpoint_connection(client: AppClient):
    async with client.connect_websocket("/channels") as websocket:
        # A subscribe frame with no topic_stream is malformed and cannot name a topic.
        test_message = {"type": "subscribe"}
        await websocket.send_json(test_message)

        # The malformed frame is rejected at the boundary as a client error, not routed
        # through the generic handler-failure path (which would log an exception to Sentry).
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
        assert "subscribe requires topic_stream" in response["error"]


@pytest.mark.asyncio
async def test_topic_less_client_message_does_not_crash_session(client: AppClient):
    # A topic-less client frame (here a `typing` message with no topic_stream) is routed through
    # _route_client_message, which — unlike the subscribe/unsubscribe branches — has no try/except.
    # Pre-fix, accessing message.topic raised ValueError into the TaskGroup and tore down the whole
    # session. The boundary guard must drop the malformed frame and leave the session alive.
    router = ChannelRouter()

    @router.on_subscribe("post_typing_stream")
    async def post_typing_handler(channel: Channel):
        await channel.accept()

    channels.include_router(router)

    topic = Topic("post_typing_stream", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Malformed frame: a valid message type but no topic_stream to name a channel.
        await websocket.send_json({"type": "typing", "is_typing": True})

        # The session is still alive: a subsequent well-formed subscribe still gets confirmed.
        await websocket.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response["topic_stream"] == topic.stream


@pytest.mark.asyncio
async def test_channel_subscription_flow(client: AppClient):
    router = ChannelRouter()

    @router.on_subscribe("test_workspace")
    async def test_workspace_handler(channel: Channel):
        await channel.accept()

    channels.include_router(router)

    topic = Topic("test_workspace", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Send subscription request
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)

        # Should receive confirmation
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response["topic_stream"] == topic.stream

        # Unsubscribe from the channel
        unsubscribe_message = {"type": "unsubscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(unsubscribe_message)
        await asyncio.sleep(0.1)  # Give time for processing

        # Re-subscribe to verify it works after unsubscribe
        await websocket.send_json(subscription_message)

        # Should receive confirmation again
        response2 = await websocket.receive_json()
        assert response2["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response2["topic_stream"] == topic.stream


@pytest.mark.asyncio
async def test_channel_rejection(client: AppClient):
    # Create a channel for unregistered stream
    topic = Topic("unregistered_stream", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Send subscription request
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)

        # Should receive rejection
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
        assert "No handler found" in response["error"]


@pytest.mark.asyncio
async def test_subscribe_handler_without_decision_fails_closed(client: AppClient):
    """A subscribe handler that never accepts or rejects must fail closed with a rejection.

    With unsigned topic subscription the handler is the only authorization boundary, so an
    omitted accept()/reject() must not leave the client silently subscribed or hanging.
    """
    router = ChannelRouter()

    @router.on_subscribe("undecided_stream")
    async def undecided_handler(channel: Channel):
        # Intentionally neither accepts nor rejects.
        pass

    channels.include_router(router)

    topic = Topic("undecided_stream", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})

        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
        assert "not authorized" in response["error"]


@pytest.mark.asyncio
async def test_multiple_channel_subscriptions(client: AppClient):
    # Setup multiple test channel handlers
    router = ChannelRouter()

    @router.on_subscribe("workspace")
    async def workspace_handler(channel: Channel):
        await channel.accept()

    @router.on_subscribe("notifications")
    async def notifications_handler(channel: Channel):
        await channel.accept()

    channels.include_router(router)

    # Create channels
    workspace_topic = Topic("workspace", workspace_id="789")
    notifications_topic = Topic("notifications", user_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Subscribe to first channel
        await websocket.send_json(
            {"type": "subscribe", "topic_stream": workspace_topic.stream, "topic_params": workspace_topic.params}
        )

        response1 = await websocket.receive_json()
        assert response1["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response1["topic_stream"] == workspace_topic.stream

        # Subscribe to second channel
        await websocket.send_json(
            {
                "type": "subscribe",
                "topic_stream": notifications_topic.stream,
                "topic_params": notifications_topic.params,
            }
        )

        response2 = await websocket.receive_json()
        assert response2["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response2["topic_stream"] == notifications_topic.stream


@pytest.mark.asyncio
async def test_channels_connection_subscribe_to():
    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    # Create channels and topics
    topic1 = Topic("stream1", param="value1")
    topic2 = Topic("stream2", param="value2")
    channel1 = Channel(topic1, session)
    channel2 = Channel(topic2, session)

    # Subscribe to first channel
    await session.subscribe_to(channel1)
    assert topic1 in session.subscriptions

    # Subscribe to second channel
    await session.subscribe_to(channel2)
    assert topic2 in session.subscriptions
    assert len(session.subscriptions) == 2

    # Subscribe to same channel again (should not create duplicate)
    channel1_duplicate = Channel(topic1, session)
    await session.subscribe_to(channel1_duplicate)
    assert len(session.subscriptions) == 2

    # Cleanup
    await session.cleanup()
    assert len(session.subscriptions) == 0


@pytest.mark.asyncio
async def test_channel_stream_and_unsubscribe():
    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))
    topic = Topic("test_stream", workspace_id="123")
    channel = Channel(topic, session)

    # Start streaming
    await channel.accept()
    subscription = session.subscriptions.get(topic)
    assert subscription is not None
    assert subscription.channel == channel

    # Should have sent auto-confirmation message
    assert len(mock_websocket.sent_messages) == 1
    confirm_msg = mock_websocket.sent_messages[0]
    assert confirm_msg["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
    assert confirm_msg["topic_stream"] == topic.stream

    # Cleanup will happen automatically when session ends


@pytest.mark.asyncio
async def test_channel_accept_and_reject():
    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))
    topic = Topic("test_stream", workspace_id="123")
    channel = Channel(topic, session)

    # Test accept
    await channel.accept()
    assert len(mock_websocket.sent_messages) == 1
    accept_msg = mock_websocket.sent_messages[0]
    assert accept_msg["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
    assert accept_msg["topic_stream"] == topic.stream

    # Test reject
    channel2 = Channel(Topic("test_stream2"), session)
    await channel2.reject("Access denied")
    assert len(mock_websocket.sent_messages) == 2
    reject_msg = mock_websocket.sent_messages[1]
    assert reject_msg["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
    assert reject_msg["error"] == "Access denied"


@pytest.mark.asyncio
async def test_websocket_client_message_processing():
    # Setup a test handler
    router = ChannelRouter()

    @router.on_subscribe("test_client")
    async def test_client_handler(channel: Channel):
        await channel.accept()

    channels.include_router(router)

    # Create test messages
    topic = Topic("test_client", workspace_id="789")
    valid_subscription = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}

    messages = [
        json.dumps(valid_subscription),
        json.dumps({"type": "invalid"}),  # Invalid message type
        '{"invalid": "json"',  # Invalid JSON
    ]

    user = await create_user()
    mock_websocket = MockWebSocket(messages)
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    # Process first message (valid subscription)
    subscription_message = BaseChannelMessage.from_dict(valid_subscription)
    await session._process_message(subscription_message)

    # Should have sent confirmation
    assert len(mock_websocket.sent_messages) == 1
    assert mock_websocket.sent_messages[0]["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED


@pytest.mark.asyncio
async def test_workspace_channel_with_user_authentication(client: AppClient):
    # Create a user and get their organization
    user = await client.get_default_user()
    organization_id = str(user.organization_id)

    # Setup a workspace channel handler that uses user context
    router = ChannelRouter()

    @router.on_subscribe("workspace_activity")
    async def workspace_activity_handler(channel: Channel):
        # In a real implementation, you might check if user has access to this workspace
        workspace_id = channel.get_param("workspace_id")
        if workspace_id and workspace_id == organization_id:
            await channel.accept()
        else:
            await channel.reject("Access denied to workspace")

    channels.include_router(router)

    # Create a channel for the user's organization
    topic = Topic("workspace_activity", workspace_id=organization_id)

    async with client.connect_websocket("/channels") as websocket:
        # Send subscription request
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)

        # Should receive confirmation
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response["topic_stream"] == topic.stream


@pytest.mark.asyncio
async def test_channel_parameter_extraction(client: AppClient):
    router = ChannelRouter()
    extracted_params = {}

    @router.on_subscribe("parameterized_channel")
    async def parameterized_handler(channel: Channel):
        # Extract various parameters
        extracted_params["workspace_id"] = channel.get_param("workspace_id")
        extracted_params["user_id"] = channel.get_param("user_id")
        extracted_params["missing_param"] = channel.get_param("missing_param", "default_value")
        extracted_params["stream_name"] = channel.topic.stream
        await channel.accept()

    channels.include_router(router)

    # Create channel with multiple parameters
    topic = Topic("parameterized_channel", workspace_id="ws123", user_id="user456")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})

        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED

        # Verify parameters were extracted correctly
        assert extracted_params["workspace_id"] == "ws123"
        assert extracted_params["user_id"] == "user456"
        assert extracted_params["missing_param"] == "default_value"
        assert extracted_params["stream_name"] == "parameterized_channel"


@pytest.mark.asyncio
async def test_on_subscribe_decorator(client: AppClient):
    """Test that the new on_subscribe decorator works"""
    router = ChannelRouter()
    subscribe_called = False

    @router.on_subscribe("test_subscribe_stream")
    async def test_subscribe_handler(channel: Channel):
        nonlocal subscribe_called
        subscribe_called = True
        await channel.accept()

    channels.include_router(router)

    topic = Topic("test_subscribe_stream", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Send subscription request
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)

        # Should receive confirmation
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert response["topic_stream"] == topic.stream
        assert subscribe_called, "Subscribe handler should have been called"


@pytest.mark.asyncio
async def test_on_unsubscribe_decorator(client: AppClient):
    """Test that the new on_unsubscribe decorator works"""
    router = ChannelRouter()
    subscribe_called = False
    unsubscribe_called = False

    @router.on_subscribe("test_unsubscribe_stream")
    async def test_subscribe_handler(channel: Channel):
        nonlocal subscribe_called
        subscribe_called = True
        await channel.accept()

    @router.on_unsubscribe("test_unsubscribe_stream")
    async def test_unsubscribe_handler(channel: Channel):
        nonlocal unsubscribe_called
        unsubscribe_called = True

    channels.include_router(router)

    topic = Topic("test_unsubscribe_stream", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Subscribe first
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)

        # Should receive confirmation
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
        assert subscribe_called, "Subscribe handler should have been called"

        # Now unsubscribe
        unsubscribe_message = {"type": "unsubscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(unsubscribe_message)

        # Give time for unsubscribe processing
        await asyncio.sleep(0.1)
        assert unsubscribe_called, "Unsubscribe handler should have been called"


@pytest.mark.asyncio
async def test_on_subscribe_and_unsubscribe_with_parameters(client: AppClient):
    """Test that subscribe/unsubscribe handlers receive correct channel parameters"""
    router = ChannelRouter()
    received_params = {}

    @router.on_subscribe("test_params_stream")
    async def test_subscribe_handler(channel: Channel):
        received_params["subscribe_user_id"] = channel.get_param("user_id")
        received_params["subscribe_workspace_id"] = channel.get_param("workspace_id")
        await channel.accept()

    @router.on_unsubscribe("test_params_stream")
    async def test_unsubscribe_handler(channel: Channel):
        received_params["unsubscribe_user_id"] = channel.get_param("user_id")
        received_params["unsubscribe_workspace_id"] = channel.get_param("workspace_id")

    channels.include_router(router)

    topic = Topic("test_params_stream", user_id="user123", workspace_id="workspace456")

    async with client.connect_websocket("/channels") as websocket:
        # Subscribe
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)
        await websocket.receive_json()  # subscription confirmed

        # Unsubscribe
        unsubscribe_message = {"type": "unsubscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(unsubscribe_message)
        await asyncio.sleep(0.1)  # Give time for processing

        # Verify parameters were passed correctly to both handlers
        assert received_params["subscribe_user_id"] == "user123"
        assert received_params["subscribe_workspace_id"] == "workspace456"
        assert received_params["unsubscribe_user_id"] == "user123"
        assert received_params["unsubscribe_workspace_id"] == "workspace456"


@pytest.mark.asyncio
async def test_unsubscribe_handler_error_handling(client: AppClient):
    """Test that errors in unsubscribe handlers don't break the unsubscribe process"""
    router = ChannelRouter()

    @router.on_subscribe("test_error_stream")
    async def test_subscribe_handler(channel: Channel):
        await channel.accept()

    @router.on_unsubscribe("test_error_stream")
    async def test_unsubscribe_handler(channel: Channel):
        raise Exception("Intentional error in unsubscribe handler")

    channels.include_router(router)

    topic = Topic("test_error_stream", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Subscribe
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)
        await websocket.receive_json()  # subscription confirmed

        # Unsubscribe (should still work despite handler error)
        unsubscribe_message = {"type": "unsubscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(unsubscribe_message)

        # Give time for processing - should work despite handler error
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_unsubscribe_without_handler(client: AppClient):
    """Test that unsubscribe works even when no unsubscribe handler is defined"""
    router = ChannelRouter()

    @router.on_subscribe("no_unsubscribe_handler_stream")
    async def subscribe_only_handler(channel: Channel):
        await channel.accept()

    # Note: No unsubscribe handler defined

    channels.include_router(router)

    topic = Topic("no_unsubscribe_handler_stream", workspace_id="123")

    async with client.connect_websocket("/channels") as websocket:
        # Subscribe
        subscription_message = {"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(subscription_message)
        await websocket.receive_json()  # subscription confirmed

        # Unsubscribe (should work even without handler)
        unsubscribe_message = {"type": "unsubscribe", "topic_stream": topic.stream, "topic_params": topic.params}
        await websocket.send_json(unsubscribe_message)

        # Give time for processing - should work without handler
        await asyncio.sleep(0.1)


@pytest.mark.asyncio
async def test_unsubscribe_handlers_called_on_websocket_disconnect():
    """Test that unsubscribe handlers are called when websocket disconnects (e.g., browser tab closed)"""

    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    # Setup router with unsubscribe handler
    router = ChannelRouter()
    unsubscribe_called = False
    unsubscribed_user_id = None

    @router.on_subscribe("test_disconnect_stream")
    async def test_subscribe_handler(channel: Channel):
        await channel.accept()

    @router.on_unsubscribe("test_disconnect_stream")
    async def test_unsubscribe_handler(channel: Channel):
        nonlocal unsubscribe_called, unsubscribed_user_id
        unsubscribe_called = True
        unsubscribed_user_id = channel.current_user.id

    channels.include_router(router)

    # Subscribe to a channel
    topic = Topic("test_disconnect_stream", user_id=str(user.id))
    channel = Channel(topic, session)
    await session.subscribe_to(channel)

    # Verify subscription exists
    assert len(session.subscriptions) == 1
    assert not unsubscribe_called

    # Simulate websocket disconnect by calling cleanup (this is what happens when browser tab closes)
    await session.cleanup()

    # Verify unsubscribe handler was called during cleanup
    assert unsubscribe_called, "Unsubscribe handler should be called during websocket disconnect/cleanup"
    assert unsubscribed_user_id == user.id, "Unsubscribe handler should receive correct user context"
    assert len(session.subscriptions) == 0, "Subscriptions should be cleared after cleanup"


@pytest.mark.asyncio
async def test_message_loop_closes_with_service_restart_on_server_shutdown():
    user = await create_user()

    class CloseTrackingMockWebSocket(MockWebSocket):
        def __init__(self):
            super().__init__()
            self.close_calls: list[int] = []

        async def close(self, code: int = 1000) -> None:
            self.close_calls.append(code)

    mock_websocket = CloseTrackingMockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    channels_base.server_stop_event.set()
    try:
        async with asyncio.TaskGroup() as task_group:
            await session._message_loop(task_group)
    finally:
        channels_base.server_stop_event.clear()

    assert mock_websocket.close_calls == [status.WS_1012_SERVICE_RESTART]


@pytest.mark.asyncio
async def test_client_message_handling():
    """Test that pong messages are properly routed to keepalive handlers."""

    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    # Setup router with keepalive handler
    router = ChannelRouter()
    handler_called = False
    received_channel = None

    @router.on_subscribe("test_client_message")
    async def test_subscribe_handler(channel: Channel):
        await channel.accept()

    @router.on_keepalive("test_client_message")
    async def test_keepalive_handler(channel: Channel):
        nonlocal handler_called, received_channel
        handler_called = True
        received_channel = channel

    channels.include_router(router)

    # Subscribe to the channel
    topic = Topic("test_client_message", user_id=str(user.id))
    channel = Channel(topic, session)
    await session.subscribe_to(channel)

    # Create and process a pong message
    message = PongMessage(data="test_data")

    await session._process_message(message)

    # Verify keepalive handler was called with correct parameters
    assert handler_called, "Keepalive handler should be called"
    assert received_channel is not None, "Handler should receive channel context"
    assert received_channel.current_user.id == user.id, "Channel should have correct user context"


@pytest.mark.asyncio
async def test_client_message_deserialization():
    """Test that client messages can be deserialized from JSON dict."""
    # Test data that would come from WebSocket client
    message_data = {"type": "pong", "data": "test_data"}

    # Test deserialization using the message registry
    message = BaseChannelMessage.from_dict(message_data)

    assert isinstance(message, PongMessage), "Should deserialize to correct message type"
    assert message.type == ChannelMessageType.PONG, "Type should be preserved"
    assert message.data == "test_data", "Data should be preserved"


@pytest.mark.asyncio
async def test_client_message_deserialization_with_params():
    """A subscribe message names its topic via topic_stream/topic_params and carries optional params."""
    message_data = {
        "type": "subscribe",
        "topic_stream": "test_stream",
        "topic_params": {"workspace_id": "123", "user_id": "456"},
        "params": {"additional": "data"},
    }

    message = BaseChannelMessage.from_dict(message_data)

    assert isinstance(message, SubscribeMessage), "Should deserialize to correct message type"
    assert message.topic_stream == "test_stream", "topic_stream should be preserved"
    assert message.topic_params == {
        "workspace_id": "123",
        "user_id": "456",
    }, "topic_params should be preserved"
    assert message.params == {"additional": "data"}, "params should be preserved"
    assert message.topic == Topic("test_stream", workspace_id="123", user_id="456")


@pytest.mark.asyncio
async def test_client_message_router_registration():
    """Test that client message handlers are properly registered."""
    router = ChannelRouter()

    @router.on_receive("test_stream", TypingMessage)
    async def test_handler(channel: Channel, message: TypingMessage):
        pass

    # Verify handler was registered in router
    key = ("test_stream", ChannelMessageType.TYPING)
    assert key in router.receive_handlers


@pytest.mark.asyncio
async def test_pong_message_handling():
    """Test that pong messages update last_pong_time."""
    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    # Initially last_pong_time should be None
    assert session.last_pong_time is None

    # Process a pong message
    pong_message = PongMessage(data="1234567890")
    await session._process_message(pong_message)

    # Verify last_pong_time was set
    assert session.last_pong_time is not None
    assert isinstance(session.last_pong_time, datetime)


@pytest.mark.asyncio
async def test_ping_pong_integration():
    """Test basic ping-pong integration using MockWebSocket."""
    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    # Send a ping message as if it came from the server's keep-alive
    ping_message = PingMessage()
    sent_successfully = await session.send(ping_message)

    assert sent_successfully, "Ping should be sent successfully"
    assert len(mock_websocket.sent_messages) == 1

    sent_ping = mock_websocket.sent_messages[0]
    assert sent_ping["type"] == "ping"

    # Simulate client responding with pong
    pong_message = PongMessage(data="test_timestamp")
    await session._process_message(pong_message)

    # Verify pong was processed
    assert session.last_pong_time is not None


@pytest.mark.asyncio
async def test_client_message_handler_error_handling():
    """Test that errors in client message handlers are properly handled."""

    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    # # Setup router with failing client message handler
    router = ChannelRouter()

    @router.on_subscribe("error_stream")
    async def test_subscribe_handler(channel: Channel):
        await channel.accept()

    @router.on_receive("error_stream", TypingMessage)
    async def failing_handler(channel: Channel, message: TypingMessage):
        raise ValueError("Test error")

    channels.include_router(router)

    # Subscribe to the channel
    topic = Topic("error_stream", user_id=str(user.id))
    channel = Channel(topic, session)
    await session.subscribe_to(channel)

    # Create and route a client message
    message = TypingMessage(topic_stream=topic.stream, topic_params=topic.params, is_typing=True)

    # This should not raise an exception despite handler error
    await session._route_client_message(message)
    # Test passes if no exception is raised


@pytest.mark.asyncio
async def test_multiple_broadcast_handlers_both_execute():
    """Both broadcast handlers for the same stream should fire on a single broadcast."""
    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    called = []

    async def handler_a(channel, **data):
        called.append("a")

    async def handler_b(channel, **data):
        called.append("b")

    channels.broadcast_handlers.add("dual_stream", handler_a)
    channels.broadcast_handlers.add("dual_stream", handler_b)

    topic = Topic("dual_stream", param="value")
    result = await channels.broadcast_handlers.execute(topic.stream, topic, session, {}, handler_kwargs={"foo": "bar"})

    assert result is True
    assert called == ["a", "b"]


@pytest.mark.asyncio
async def test_broadcast_handler_failure_does_not_skip_remaining():
    """A failing handler should not prevent subsequent handlers from running."""
    user = await create_user()
    mock_websocket = MockWebSocket()
    session = WebSocketSession(SafeWebSocket(cast(WebSocket, mock_websocket)), user, create_test_context(user))

    called = []

    async def failing_handler(channel, **data):
        raise RuntimeError("boom")

    async def healthy_handler(channel, **data):
        called.append("ok")

    channels.broadcast_handlers.add("isolated_stream", failing_handler)
    channels.broadcast_handlers.add("isolated_stream", healthy_handler)

    topic = Topic("isolated_stream", param="value")
    result = await channels.broadcast_handlers.execute(topic.stream, topic, session, {})

    assert result is True
    assert called == ["ok"]
