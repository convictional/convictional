from app.channels.base import BaseChannelMessage, message_type_registry
from app.routers.dependencies import EventMessage
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic


def test_event_message_registered():
    assert ChannelMessageType.EVENT in message_type_registry
    assert message_type_registry[ChannelMessageType.EVENT] is EventMessage


def test_event_message_serialization():
    topic = Topic("document_comments", document_id="abc-123")

    message = EventMessage(
        topic_stream=topic.stream,
        topic_params=topic.params,
        resource=ChannelEventResource.DOCUMENT_COMMENT,
        action=ChannelEventAction.REACTION_TOGGLED,
        data={"comment_id": "c-1", "reactions": {"thumbs_up": ["u-1", "u-2"]}},
    )

    dumped = message.model_dump()
    assert dumped["type"] == "event"
    assert dumped["resource"] == "document_comment"
    assert dumped["action"] == "reaction_toggled"
    assert dumped["data"]["comment_id"] == "c-1"
    assert dumped["data"]["reactions"] == {"thumbs_up": ["u-1", "u-2"]}
    assert dumped["topic_stream"] == topic.stream


def test_event_message_deserialization():
    topic = Topic("document_comments", document_id="abc-123")

    original = EventMessage(
        topic_stream=topic.stream,
        topic_params=topic.params,
        resource=ChannelEventResource.DOCUMENT_COMMENT,
        action=ChannelEventAction.REACTION_TOGGLED,
        data={"comment_id": "c-1"},
    )

    restored = BaseChannelMessage.from_dict(original.model_dump())
    assert isinstance(restored, EventMessage)
    assert restored.resource == ChannelEventResource.DOCUMENT_COMMENT
    assert restored.action == ChannelEventAction.REACTION_TOGGLED
    assert restored.data == {"comment_id": "c-1"}


def test_event_message_empty_data():
    topic = Topic("test", key="val")
    message = EventMessage(
        topic_stream=topic.stream,
        topic_params=topic.params,
        resource=ChannelEventResource.CHAT_MESSAGE,
        action=ChannelEventAction.CREATED,
    )
    assert message.data == {}
    assert message.model_dump()["data"] == {}
