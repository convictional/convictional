import asyncio
from uuid import UUID

import pytest

from infra.cache import cache
from infra.messaging import MAX_NOTIFY_PAYLOAD_SIZE, PostgreSQLSubscriptionAdapter, Topic
from tests.helpers.cache import use_postgres_cache  # noqa: F401


@pytest.mark.asyncio
async def test_broadcaster_listener_integration():
    topic_name = "test_integration"
    adapter = PostgreSQLSubscriptionAdapter()
    test_data = {"message": "hello", "value": 42}
    received_data = None
    received_event = asyncio.Event()

    async def callback(data):
        nonlocal received_data
        received_data = data
        received_event.set()

    try:
        await adapter.start()
        await adapter.subscribe(topic_name, callback)
        try:
            await adapter.broadcast(topic_name, test_data)
            await asyncio.wait_for(received_event.wait(), timeout=2.0)
            assert received_data == test_data
        finally:
            await adapter.unsubscribe(topic_name, callback)
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_multiple_broadcasts_single_listener():
    topic_name = "test_multiple_broadcasts"
    adapter = PostgreSQLSubscriptionAdapter()
    test_messages = [
        {"id": 1, "message": "first"},
        {"id": 2, "message": "second"},
        {"id": 3, "message": "third"},
    ]
    received_messages = []
    received_count = 0
    all_received_event = asyncio.Event()

    async def callback(data):
        nonlocal received_count
        received_messages.append(data)
        received_count += 1
        if received_count == len(test_messages):
            all_received_event.set()

    try:
        await adapter.start()
        await adapter.subscribe(topic_name, callback)
        try:
            for message in test_messages:
                await adapter.broadcast(topic_name, message)

            await asyncio.wait_for(all_received_event.wait(), timeout=2.0)
            assert received_messages == test_messages
        finally:
            await adapter.unsubscribe(topic_name, callback)
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_multiple_subscribers_same_channel():
    """Test that multiple subscribers can simultaneously listen to the same channel."""
    topic_name = "test_multiple_subscribers"
    adapter = PostgreSQLSubscriptionAdapter()
    test_message = {"message": "broadcast to all", "timestamp": 12345}

    received_messages = {}
    received_count = 0
    all_received_event = asyncio.Event()

    def make_callback(subscriber_id):
        async def callback(data):
            nonlocal received_count
            received_messages[subscriber_id] = data
            received_count += 1
            if received_count == 30:
                all_received_event.set()

        return callback

    try:
        await adapter.start()

        # Create 30 subscribers
        callbacks = []
        for i in range(30):
            callback = make_callback(i)
            await adapter.subscribe(topic_name, callback)
            callbacks.append(callback)

        try:
            # Send message to the channel
            await adapter.broadcast(topic_name, test_message)

            # Wait for all subscribers to receive the message
            try:
                await asyncio.wait_for(all_received_event.wait(), timeout=2.0)
            except TimeoutError:
                assert False, f"Only {received_count} out of 30 subscribers received message within timeout"

            # Verify all received messages are identical
            assert len(received_messages) == 30
            for subscriber_id, received in received_messages.items():
                assert received == test_message, f"Subscriber {subscriber_id} received incorrect message"
        finally:
            # Cleanup all subscriptions
            for callback in callbacks:
                await adapter.unsubscribe(topic_name, callback)
    finally:
        await adapter.stop()


@pytest.mark.asyncio
async def test_topic_broadcast_method():
    # Test topic creation with parameters
    email_topic = Topic("email_inbox", user_id="1234")
    assert email_topic.stream == "email_inbox"
    assert email_topic.params == {"user_id": "1234"}

    # Test sending a message (should not raise an exception)
    try:
        await email_topic.broadcast(action="new_email", email_thread_id="5678", subject="Test Email")
        # If we get here, the send method worked without error
        assert True
    except Exception as e:
        pytest.fail(f"Topic.broadcast() raised an exception: {e}")

    # Test UUID to cover JSON encoding
    test_uuid = UUID("550e8400-e29b-41d4-a716-446655440000")
    try:
        await email_topic.broadcast(action="restore_message", email_thread_id=test_uuid)
        assert True
    except Exception as e:
        pytest.fail(f"Topic.broadcast() with UUID email_thread_id raised an exception: {e}")

    # Test topic without parameters
    broadcast_topic = Topic("system_announcements")
    assert broadcast_topic.stream == "system_announcements"
    assert broadcast_topic.params == {}

    try:
        await broadcast_topic.broadcast(
            level="info", message="System maintenance scheduled", timestamp="2024-01-01T00:00:00Z"
        )
        assert True
    except Exception as e:
        pytest.fail(f"Topic.send() raised an exception: {e}")

    # Test topic with multiple parameters
    notification_topic = Topic("notifications", user_id="123", workspace_id="456")
    assert notification_topic.params == {"user_id": "123", "workspace_id": "456"}

    try:
        await notification_topic.broadcast(
            type="mention", message="You were mentioned in a document", document_id="doc_123"
        )
        assert True
    except Exception as e:
        pytest.fail(f"Topic.broadcast() raised an exception: {e}")


@pytest.mark.asyncio
async def test_large_message_broadcast_and_receive(use_postgres_cache):  # noqa: F811
    """Test that large messages are automatically cached and received correctly."""

    await cache.clear()

    topic_name = "test_large_message"
    adapter = PostgreSQLSubscriptionAdapter()

    # Create a large message that exceeds MAX_NOTIFY_PAYLOAD_SIZE
    large_content = "x" * (MAX_NOTIFY_PAYLOAD_SIZE + 1000)
    large_message = {"type": "large_test", "content": large_content, "id": "large_msg_123"}

    received_message = None
    message_received = asyncio.Event()

    async def large_message_callback(data):
        nonlocal received_message
        received_message = data
        message_received.set()

    try:
        await adapter.start()
        await adapter.subscribe(topic_name, large_message_callback)

        # Broadcast the large message
        await adapter.broadcast(topic_name, large_message)

        # Wait for the message to be received
        await asyncio.wait_for(message_received.wait(), timeout=3.0)

        # Verify the message was received correctly
        assert received_message is not None, "Large message was not received"
        assert received_message["type"] == "large_test", "Message type doesn't match"
        assert received_message["content"] == large_content, "Message content doesn't match"
        assert received_message["id"] == "large_msg_123", "Message ID doesn't match"

    finally:
        await adapter.unsubscribe(topic_name, large_message_callback)
        await adapter.stop()
        await cache.clear()
