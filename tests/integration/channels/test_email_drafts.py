import asyncio
import base64

import pytest
from pycrdt import YSyncMessageType, create_sync_message

from app.models.collaboration.live import LiveDocument
from app.models.workspaces.email.thread import EmailThread
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType, EmailDraftAction
from infra.db import transaction
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_collaborator, create_email_message, create_user


@pytest.mark.asyncio
async def test_email_draft_access_control(client: AppClient):
    """Test access control for email_draft channel subscription."""
    # Setup users
    owner = await client.get_default_user()
    collaborator = await create_user(organization_id=owner.organization_id)
    unauthorized_user = await create_user(organization_id=owner.organization_id)

    # Create email draft message
    draft_message = await create_email_message(
        user_id=owner.id,
        organization_id=owner.organization_id,
        external_thread_id="draft_access_test",
        subject="Test Draft Access",
        sender="sender@example.com",
        is_draft=True,
    )

    thread = await EmailThread.get(id=draft_message.thread_id)
    await thread.fetch_related("workspace")

    # Add collaborator to workspace
    await create_collaborator(
        user_id=collaborator.id,
        workspace_id=thread.workspace_id,
        organization_id=owner.organization_id,
    )

    draft_topic = Topic("email_draft", message_id=draft_message.id)

    # Owner should be able to subscribe
    client.current_user = owner
    async with client.connect_channel(draft_topic) as websocket:
        assert websocket is not None

    # Collaborator should be able to subscribe
    client.current_user = collaborator
    async with client.connect_channel(draft_topic) as websocket:
        assert websocket is not None

    # Unauthorized user should be rejected
    client.current_user = unauthorized_user
    with pytest.raises(Exception):
        async with client.connect_channel(draft_topic):
            pass

    # Missing message_id parameter should be rejected
    with pytest.raises(Exception):
        async with client.connect_channel(Topic("email_draft")):
            pass


@pytest.mark.asyncio
async def test_draft_removed_broadcast_fires_after_commit(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    received = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="broadcast_timing_test",
        subject="Test Timing",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=received.thread_id)
    await thread.fetch_related("workspace")
    await create_collaborator(
        user_id=other_user.id,
        workspace_id=thread.workspace_id,
        organization_id=user.organization_id,
    )
    await thread.start_draft(user=user, subject="Re: Test", body_plain="Content")

    topic = Topic("email_thread_draft", thread_id=thread.id)

    # Connect as other_user to receive broadcasts
    client.current_user = other_user
    async with client.connect_channel(topic) as websocket:
        # Call remove_draft() inside an explicit outer transaction to simulate the
        # router behavior. The broadcast should be deferred until after commit.
        broadcast_received_before_commit = False
        async with transaction() as connection:
            await thread.remove_draft(user=user, using_db=connection)

            # Still inside the outer transaction -- the broadcast should NOT have
            # fired yet because the deletion is not committed. Without after_commit()
            # the broadcast fires immediately on the auxiliary connection.
            try:
                await asyncio.wait_for(websocket.receive_json(), timeout=0.1)
                broadcast_received_before_commit = True
            except TimeoutError:
                pass

        assert not broadcast_received_before_commit, (
            "Broadcast was delivered before the outer transaction committed. "
            "Use after_commit() to defer the broadcast until the transaction commits."
        )

        # After the outer transaction commits, the broadcast must arrive
        event = await asyncio.wait_for(receive_event(websocket, ChannelEventResource.EMAIL_DRAFT), timeout=1.0)
        assert event["action"] == ChannelEventAction.DRAFT_REMOVED


@pytest.mark.asyncio
async def test_broadcasts_exclude_draft_creator(client: AppClient):
    """Test that broadcast events exclude the draft creator."""
    user = await client.get_default_user()

    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="exclusion_test",
        subject="Test Message",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=message.thread_id)
    topic = Topic("email_thread_draft", thread_id=thread.id)

    # Connect as the draft creator
    async with client.connect_channel(topic) as websocket:
        # Manually broadcast as if this user started a draft
        await topic.broadcast(action=EmailDraftAction.DRAFT_STARTED, user_id=user.id)

        # Should not receive any message because the handler excludes the creator
        # We'll timeout trying to receive, which proves exclusion works
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.receive_json(), timeout=0.1)


@pytest.mark.asyncio
async def test_partial_save_broadcast_preserves_populated_fields(client: AppClient):
    """The client gates each envelope field on a per-field dirty flag, so a PATCH
    where the user only touched the body sends `{}` (or just the dirty key). The
    server's update_fields protocol preserves untouched columns. The DRAFT_UPDATED
    broadcast to collaborators must reflect the populated state — not the empty
    request payload."""
    user_a = await client.get_default_user()
    user_b = await create_user(organization_id=user_a.organization_id)

    initial_message = await create_email_message(
        user_id=user_a.id,
        organization_id=user_a.organization_id,
        external_thread_id="state_parity_test",
        subject="Test Message",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=initial_message.thread_id)
    await thread.fetch_related("workspace")
    await create_collaborator(
        user_id=user_b.id, workspace_id=thread.workspace_id, organization_id=user_a.organization_id
    )

    draft = await thread.start_draft(
        user=user_a,
        subject="Hello",
        to=["x@y.com"],
        cc=["cc@y.com"],
        bcc=["bcc@y.com"],
        body_plain="",
    )

    topic = Topic("email_thread_draft", thread_id=thread.id)

    client.current_user = user_b
    async with client.connect_channel(topic) as websocket:
        # User A patches only the subject. The broadcast's envelope must still
        # carry the populated to/cc/bcc, not the empty form-payload values.
        await thread.save_draft(draft, user=user_a, update_fields={"subject"})

        event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert event["action"] == ChannelEventAction.DRAFT_UPDATED
        envelope = event["data"]["envelope"]
        assert envelope["to"] == ["x@y.com"]
        assert envelope["cc"] == ["cc@y.com"]
        assert envelope["bcc"] == ["bcc@y.com"]
        assert envelope["subject"] == "Hello"


@pytest.mark.asyncio
async def test_bidirectional_sync_server_sends_sync_step1_back(client: AppClient):
    """
    Test that when server receives SyncStep1, it responds with both:
    1. SyncStep2 (what client is missing from server)
    2. SyncStep1 (so client sends what server is missing - e.g. offline edits)

    This bidirectional sync is required by the Yjs protocol for client-server model.
    Without it, offline edits would be lost on reconnection.

    See: https://github.com/yjs/y-protocols/blob/master/sync.js
    """
    user = await client.get_default_user()

    # Create an email draft to get a live document topic
    draft_message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="bidirectional_sync_test",
        subject="Test Bidirectional Sync",
        sender="sender@example.com",
        is_draft=True,
    )

    draft_topic = Topic("email_draft", message_id=draft_message.id)

    # Add some content to the server's live document
    await LiveDocument.set_initial_content(draft_topic, "Server content")

    # Load the server document to get its state for creating a valid SyncStep1
    server_doc = await LiveDocument.for_topic(draft_topic)
    server_sync_step1 = create_sync_message(server_doc)

    # pycrdt creates messages with format [SYNC_PREFIX, type, length, data...]
    # but JavaScript y-protocols uses [type, data...]
    # Strip the first byte to match the wire format
    wire_format_sync_step1 = server_sync_step1[1:]

    async with client.connect_channel(draft_topic) as websocket:
        # Send SyncStep1 to server
        await websocket.send_json(
            {
                "type": ChannelMessageType.LIVE_DOCUMENT_SYNC,
                "topic_stream": draft_topic.stream,
                "topic_params": draft_topic.params,
                "data": base64.b64encode(wire_format_sync_step1).decode("utf-8"),
            }
        )

        # Collect sync responses from server
        sync_messages = []
        try:
            while True:
                response = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
                if response["type"] == ChannelMessageType.LIVE_DOCUMENT_SYNC:
                    sync_messages.append(response)
        except TimeoutError:
            pass  # Done receiving messages

        assert len(sync_messages) >= 2, f"Expected at least 2 sync messages, got {len(sync_messages)}"

        # Decode and check message types
        message_types = []
        for msg in sync_messages:
            data = base64.b64decode(msg["data"])
            # First byte is the message type
            message_type = data[0]
            message_types.append(message_type)

        # Should have received both SyncStep2 (type 1) and SyncStep1 (type 0)
        assert YSyncMessageType.SYNC_STEP1 in message_types, "Server should send SyncStep1 back for bidirectional sync"
        assert YSyncMessageType.SYNC_STEP2 in message_types, "Server should send SyncStep2 with missing updates"


#
# JSON broadcast handler tests — emit EVENT messages with resource=EMAIL_DRAFT
# and action-specific payloads. The legacy DOM_CHANGE handler has been removed.
#


@pytest.mark.asyncio
async def test_json_draft_updated_emits_envelope(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="json_updated",
        subject="Test",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=message.thread_id)
    await thread.fetch_related("workspace")
    await create_collaborator(
        user_id=other_user.id, workspace_id=thread.workspace_id, organization_id=user.organization_id
    )

    draft = await thread.start_draft(user=user, subject="Hello", to=["x@y.com"], cc=["c@y.com"], body_plain="")

    topic = Topic("email_thread_draft", thread_id=thread.id)
    client.current_user = other_user
    async with client.connect_channel(topic) as websocket:
        await thread.save_draft(draft, user=user)

        event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert event["action"] == ChannelEventAction.DRAFT_UPDATED
        envelope = event["data"]["envelope"]
        assert envelope["subject"] == "Hello"
        assert envelope["to"] == ["x@y.com"]
        assert envelope["cc"] == ["c@y.com"]


@pytest.mark.asyncio
async def test_json_draft_updated_broadcasts_to_actors_other_session(client: AppClient):
    """The actor's other browser session (same user_id) must receive DRAFT_UPDATED so
    a second window stays in sync with edits made in the first."""
    user = await client.get_default_user()

    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="json_actor_other_session_updated",
        subject="Test",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=message.thread_id)
    draft = await thread.start_draft(user=user, subject="Hello", to=["x@y.com"], body_plain="")

    topic = Topic("email_thread_draft", thread_id=thread.id)
    async with client.connect_channel(topic) as websocket:
        await thread.save_draft(draft, user=user)

        event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert event["action"] == ChannelEventAction.DRAFT_UPDATED
        envelope = event["data"]["envelope"]
        assert envelope["to"] == ["x@y.com"]
        assert envelope["subject"] == "Hello"


@pytest.mark.asyncio
async def test_json_draft_removed_broadcasts_to_actors_other_session(client: AppClient):
    """The actor's other browser session must receive DRAFT_REMOVED so a second window
    tears down its composer when the first window discards the draft."""
    user = await client.get_default_user()

    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="json_actor_other_session_removed",
        subject="Test",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=message.thread_id)
    draft = await thread.start_draft(user=user, subject="Hello", to=["x@y.com"], body_plain="")

    topic = Topic("email_thread_draft", thread_id=thread.id)
    async with client.connect_channel(topic) as websocket:
        await thread.remove_draft(user, draft=draft)

        event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert event["action"] == ChannelEventAction.DRAFT_REMOVED
        assert event["data"]["user_id"] == str(user.id)


@pytest.mark.asyncio
async def test_json_draft_started_payload_is_minimal(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="json_started",
        subject="Test",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=message.thread_id)
    await thread.fetch_related("workspace")
    await create_collaborator(
        user_id=other_user.id, workspace_id=thread.workspace_id, organization_id=user.organization_id
    )

    topic = Topic("email_thread_draft", thread_id=thread.id)
    client.current_user = other_user
    async with client.connect_channel(topic) as websocket:
        draft = await thread.start_draft(user=user, subject="Re: Test", body_plain="content")
        await thread.broadcast_draft_started(user)

        event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert event["action"] == ChannelEventAction.DRAFT_STARTED
        data = event["data"]
        assert data == {
            "user_id": str(user.id),
            "thread_id": str(thread.id),
            "draft_message_id": str(draft.message.id),
        }


@pytest.mark.asyncio
async def test_json_handler_skips_actor_only_on_draft_started(client: AppClient):
    """DRAFT_STARTED from your own action must not echo back, but DRAFT_UPDATED and
    DRAFT_REMOVED must reach the actor's other browser sessions so a second window
    stays in sync with edits made in the first."""
    user = await client.get_default_user()

    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="json_self_skip",
        subject="Test",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=message.thread_id)
    topic = Topic("email_thread_draft", thread_id=thread.id)

    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(action=EmailDraftAction.DRAFT_STARTED, user_id=user.id)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(websocket.receive_json(), timeout=0.1)

        await thread.start_draft(user=user, subject="Re: Test", body_plain="content")

        await topic.broadcast(action=EmailDraftAction.DRAFT_UPDATED, user_id=user.id)
        updated_event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert updated_event["action"] == ChannelEventAction.DRAFT_UPDATED

        await topic.broadcast(action=EmailDraftAction.DRAFT_REMOVED, user_id=user.id)
        removed_event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert removed_event["action"] == ChannelEventAction.DRAFT_REMOVED


@pytest.mark.asyncio
async def test_json_assignment_changed_emits_to_actor_too(client: AppClient):
    """ASSIGNMENT_CHANGED has no sender-skip — every collaborator (including the actor) needs the pill."""
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    message = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="json_assignment",
        subject="Test",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=message.thread_id)
    await thread.fetch_related("workspace__collaborators__user")
    await create_collaborator(
        user_id=other_user.id, workspace_id=thread.workspace_id, organization_id=user.organization_id
    )
    await thread.start_draft(user=user, subject="Draft", body_plain="content")

    topic = Topic("email_thread_draft", thread_id=thread.id)
    async with client.connect_channel(topic) as websocket:
        await thread.collaboration.assign_to(other_user, user)

        event = await receive_event(websocket, ChannelEventResource.EMAIL_DRAFT)
        assert event["action"] == ChannelEventAction.ASSIGNMENT_CHANGED
        data = event["data"]
        assert data["sendable_by"]
        assert "can_reply" in data
        assert "cannot_send_reason" in data


@pytest.mark.asyncio
async def test_email_draft_unsigned_subscribe_unauthorized(client: AppClient):
    """An unsigned subscribe with another org's message_id is rejected at subscribe time."""
    await client.get_default_user()
    other = await create_user(name="Other Org User")
    message = await create_email_message(creator_id=other.id, organization_id=other.organization_id, subject="Foreign")

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": "email_draft",
                "topic_params": {"message_id": str(message.id)},
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
