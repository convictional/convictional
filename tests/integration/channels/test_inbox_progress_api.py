"""JSON-mode channel handler tests for the inbox_progress stream.

These exercise the EventMessage payloads emitted by the React-facing handler in
app/routers/api/inbox_progress.py. The HTML handler was deleted in the inbox
React switchover; there is no dual-dispatch on this stream anymore.
"""

from datetime import UTC, datetime

import pytest

from app.models.accounts import User
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_inbox_progress_broadcast_refetches_user_state(client: AppClient):
    """`channel.current_user` is loaded once at connect — the handler must reload to see DB updates.

    Without the reload, the event fires with stale sync-completion state and the React banner
    re-renders itself instead of clearing. Mirrors the HTML-handler test for commit 7d29cd50d.
    """
    user = await client.get_default_user()
    await user.mark_onboarding_mailbox_sync_started()
    topic = Topic("inbox_progress", user_id=user.id)

    async with client.connect_channel(topic) as websocket:
        await User.filter(id=user.id).update(onboarding_mailbox_sync_completed_at=datetime.now(UTC))
        assert user.onboarding_mailbox_sync_completed_at is None  # confirms staleness

        await topic.broadcast()

        event = await receive_event(websocket, ChannelEventResource.INBOX_PROGRESS)
        assert event["action"] == ChannelEventAction.UPDATED
        assert event["data"]["is_onboarding_mailbox_sync_complete"] is True


@pytest.mark.asyncio
async def test_inbox_progress_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe carrying another user's user_id is rejected at subscribe time."""
    await client.get_default_user()
    other_user = await create_user(name="Other User")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "inbox_progress",
                "topic_params": {"user_id": str(other_user.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
