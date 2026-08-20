import asyncio
from uuid import uuid4

import pytest

from app.models.collaboration.live import Presence, workspace_scope_key
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_email_message, create_goal, create_user


async def _receive_action(websocket, resource: ChannelEventResource, action: ChannelEventAction) -> dict:
    """Wait for an EVENT with the given resource AND action (presence + view-state share a resource)."""
    while True:
        message = await websocket.receive_json()
        if (
            message.get("type") == ChannelMessageType.EVENT
            and message.get("resource") == resource
            and message.get("action") == action
        ):
            return message


@pytest.mark.asyncio
async def test_workspace_collaborators_presence_broadcast(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    other_user = await create_user(name="Bob Clams", organization_id=user.organization_id)
    email_message = await create_email_message(creator_id=user.id, organization_id=user.organization_id)
    await email_message.fetch_related("thread__workspace")
    await email_message.thread.collaboration.add(user, user)
    topic = Topic("workspace_collaborators", workspace_id=email_message.thread.workspace_id)

    async with client.connect_channel(topic) as websocket:
        # Connecting fires a presence broadcast handled by the React-facing JSON handler.
        event = await websocket.receive_json()
        assert event["type"] == ChannelMessageType.EVENT
        assert event["resource"] == ChannelEventResource.WORKSPACE_COLLABORATORS
        assert event["action"] == ChannelEventAction.UPDATED
        assert str(user.id) in event["data"]["present_user_ids"]

        # Adding a collaborator fires a CREATED event so other clients refetch.
        await email_message.thread.collaboration.add(other_user, user)
        event = await websocket.receive_json()
        assert event["type"] == ChannelMessageType.EVENT
        assert event["resource"] == ChannelEventResource.WORKSPACE_COLLABORATORS
        assert event["action"] == ChannelEventAction.CREATED

        # Removing a collaborator fires a DELETED event.
        await email_message.thread.collaboration.remove(other_user)
        event = await websocket.receive_json()
        assert event["type"] == ChannelMessageType.EVENT
        assert event["resource"] == ChannelEventResource.WORKSPACE_COLLABORATORS
        assert event["action"] == ChannelEventAction.DELETED


@pytest.mark.asyncio
async def test_view_state_broadcast_to_other_collaborators_on_visit(client: AppClient, use_postgres_cache):
    """Recording a visit broadcasts VIEW_STATE_CHANGED so other viewers refetch their view state."""
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    await create_collaborator(workspace_id=goal.workspace_id, user_id=other_user.id)
    topic = Topic("workspace_collaborators", workspace_id=goal.workspace_id)

    with client.current_user_as(other_user):
        async with client.connect_channel(topic) as websocket:
            with client.current_user_as(user):
                await client.post(f"/api/workspaces/{goal.workspace_id}/visits", json={})
            event = await _receive_action(
                websocket, ChannelEventResource.WORKSPACE_COLLABORATORS, ChannelEventAction.VIEW_STATE_CHANGED
            )
            assert event["action"] == ChannelEventAction.VIEW_STATE_CHANGED


@pytest.mark.asyncio
async def test_view_state_broadcast_skips_visiting_user(client: AppClient, use_postgres_cache):
    """The visitor's own tab already knows; they receive no VIEW_STATE_CHANGED for their own visit."""
    user = await client.get_default_user()
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    topic = Topic("workspace_collaborators", workspace_id=goal.workspace_id)

    async with client.connect_channel(topic) as websocket:
        await client.post(f"/api/workspaces/{goal.workspace_id}/visits", json={})
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                _receive_action(
                    websocket, ChannelEventResource.WORKSPACE_COLLABORATORS, ChannelEventAction.VIEW_STATE_CHANGED
                ),
                timeout=0.5,
            )


@pytest.mark.asyncio
async def test_workspace_collaborators_unsigned_subscribe_unauthorized(client: AppClient, use_postgres_cache):
    """An unsigned subscribe for another org's workspace is rejected, and rejection is terminal:
    the handler must not fall through to accept() and leak the user into presence."""
    user = await client.get_default_user()
    other_user = await create_user(name="Other Org User")
    email_message = await create_email_message(creator_id=other_user.id, organization_id=other_user.organization_id)
    await email_message.fetch_related("thread__workspace")
    await email_message.thread.collaboration.add(other_user, other_user)
    workspace_id = email_message.thread.workspace_id
    topic = Topic("workspace_collaborators", workspace_id=workspace_id)

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {"type": ChannelMessageType.SUBSCRIBE, "topic_stream": topic.stream, "topic_params": topic.params}
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED

        # No SUBSCRIPTION_CONFIRMED or presence EVENT may follow the rejection.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(websocket.receive_json(), timeout=0.5)

    presence = Presence(scope_key=workspace_scope_key(workspace_id))
    assert user.id not in await presence.get_active_user_ids()


@pytest.mark.asyncio
async def test_workspace_collaborators_missing_workspace_rejected(client: AppClient, use_postgres_cache):
    """A subscribe for a workspace that no longer exists (e.g. deleted mid-session) rejects cleanly
    rather than raising DoesNotExist and falling through to the fail-closed error path."""
    await client.get_default_user()
    topic = Topic("workspace_collaborators", workspace_id=uuid4())

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {"type": ChannelMessageType.SUBSCRIBE, "topic_stream": topic.stream, "topic_params": topic.params}
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED

        with pytest.raises(TimeoutError):
            await asyncio.wait_for(websocket.receive_json(), timeout=0.5)


@pytest.mark.asyncio
async def test_workspace_collaborators_pong_handling(client: AppClient, use_postgres_cache):
    user = await client.get_default_user()
    email_message = await create_email_message(creator_id=user.id, organization_id=user.organization_id)
    await email_message.fetch_related("thread__workspace")
    await email_message.thread.collaboration.add(user, user)
    topic = Topic("workspace_collaborators", workspace_id=email_message.thread.workspace_id)

    async with client.connect_channel(topic) as websocket:
        pong_message = {"type": ChannelMessageType.PONG, "data": "test"}
        await websocket.send_json(pong_message)

        event = await websocket.receive_json()
        assert event["resource"] == ChannelEventResource.WORKSPACE_COLLABORATORS

        presence = Presence(scope_key=workspace_scope_key(email_message.thread.workspace_id))
        present_user_ids = await presence.get_active_user_ids()
        assert user.id in present_user_ids
