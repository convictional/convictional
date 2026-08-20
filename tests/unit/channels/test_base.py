import pytest

from app.channels.base import ChannelRouter, ChannelsApp, SubscribeMessage


def test_channel_message_resolves_topic_from_unsigned_fields():
    # React islands subscribe by naming the topic directly — no signed token.
    message = SubscribeMessage(topic_stream="goal_timeline", topic_params={"goal_id": "5"})
    assert message.topic.stream == "goal_timeline"
    assert message.topic.params == {"goal_id": "5"}
    assert message.topic.name == "goal_timeline:goal_id:5"


def test_channel_message_without_topic_raises():
    message = SubscribeMessage()
    with pytest.raises(ValueError):
        _ = message.topic


def test_channel_router_decorator():
    router = ChannelRouter()

    @router.on_subscribe()
    async def workspace_handler(channel):
        pass

    @router.on_subscribe("custom_name")
    async def other_handler(channel):
        pass

    assert "workspace_handler" in router.subscribe_handlers
    assert "custom_name" in router.subscribe_handlers


def test_channels_app_include_router():
    app = ChannelsApp()
    router = ChannelRouter()

    @router.on_subscribe("workspace")
    async def workspace_handler(channel):
        pass

    @router.on_subscribe("user")
    async def user_handler(channel):
        pass

    app.include_router(router)
    assert "workspace" in app.subscribe_handlers
    assert "user" in app.subscribe_handlers


def test_multiple_handlers_per_stream():
    app = ChannelsApp()

    async def handler_a(channel, **data):
        pass

    async def handler_b(channel, **data):
        pass

    app.broadcast_handlers.add("my_stream", handler_a)
    app.broadcast_handlers.add("my_stream", handler_b)

    assert "my_stream" in app.broadcast_handlers
    handlers = app.broadcast_handlers.handlers["my_stream"]
    assert len(handlers) == 2
    assert handlers[0] is handler_a
    assert handlers[1] is handler_b
