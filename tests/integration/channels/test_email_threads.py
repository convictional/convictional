import pytest

from app.models.collaboration.mailbox import Mailbox
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_email_message, create_user


def _new_message_payload(user, message, **overrides) -> dict:
    payload = {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "external_message_id": "msg_new_123",
        "external_thread_id": message.external_thread_id,
        "external_history_id": "999999",
        "message_id": "new_message_123@example.com",
        "message_type": "received",
        "subject": "Re: Test Email Thread",
        "sender": "Alice Smith <alice@example.com>",
        "to": [user.email],
        "cc": [],
        "bcc": [],
        "body_plain": "This is a reply to the test email.",
        "body_html": "<p>This is a reply to the test email.</p>",
        "preview": "This is a reply to the test email.",
        "received_at": "2024-01-01T12:00:00Z",
        "sent_at": "2024-01-01T12:00:00Z",
        "labels": ["inbox"],
        "raw_data": {},
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_email_thread_received_message(client: AppClient):
    user = await client.get_default_user()
    other = await create_user(organization_id=user.organization_id)

    message = await create_email_message(
        creator_id=user.id, organization_id=user.organization_id, subject="Test Email Thread"
    )
    await message.fetch_related("thread")
    await Mailbox.sync(message.thread)
    topic = Topic("email_thread", thread_id=str(message.thread.id))

    async with client.connect_channel(topic) as websocket:
        # Broadcast from another user so the sender-skip filter doesn't apply.
        await message.thread.receive_message(_new_message_payload(user, message, user_id=other.id))

        event_response = await receive_event(websocket, ChannelEventResource.EMAIL_THREAD)
        assert event_response["topic_stream"] == topic.stream
        assert event_response["action"] == ChannelEventAction.MESSAGE_ADDED
        assert event_response["data"]["thread_id"] == str(message.thread_id)
        assert event_response["data"]["message"]["sender_email"]


@pytest.mark.asyncio
async def test_email_thread_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe with another org's thread_id is rejected at subscribe time."""
    await client.get_default_user()
    other_user = await create_user(name="Other Org User")
    message = await create_email_message(
        creator_id=other_user.id, organization_id=other_user.organization_id, subject="Foreign Thread"
    )
    await message.fetch_related("thread")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "email_thread",
                "topic_params": {"thread_id": str(message.thread.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED


# Note: the JSON handler has a sender-skip guard, but `EmailThread.receive_message`
# does not pass the actor's `user_id` in its broadcast — only `new_message_id`. So
# the guard is currently a no-op for the incoming-message path. The React tab
# dedupes by message id on its end. Outbound broadcasts (`send_draft`) have the
# same gap; closing it is out of scope for the cutover PR.
