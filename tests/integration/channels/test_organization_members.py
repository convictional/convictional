import pytest
from fastapi import status

from app.models.accounts import Group, Invite
from config.enums import ChannelEventAction, ChannelEventResource, ChannelMessageType
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_organization_members_broadcasts_on_add_and_remove(client: AppClient):
    user = await client.get_default_user()
    await user.make_admin()
    topic = Topic("organization_members", organization_id=user.organization_id)

    async with client.connect_channel(topic) as websocket:
        # Every membership change broadcasts a single UPDATED event; the client
        # refetches the full payload, so the broadcast doesn't carry how it moved.
        invite = Invite(inviter=user, email="newbie@example.com")
        await invite.process()
        event = await receive_event(websocket, ChannelEventResource.ORGANIZATION_MEMBERS)
        assert event["action"] == ChannelEventAction.UPDATED

        # Deactivating a user also broadcasts UPDATED.
        other_user = await create_user(organization_id=user.organization_id)
        response = await client.patch(f"/api/organization/users/{other_user.id}", json={"active": False})
        assert response.status_code == status.HTTP_200_OK
        event = await receive_event(websocket, ChannelEventResource.ORGANIZATION_MEMBERS)
        assert event["action"] == ChannelEventAction.UPDATED

        # Reactivating broadcasts UPDATED too.
        response = await client.patch(f"/api/organization/users/{other_user.id}", json={"active": True})
        assert response.status_code == status.HTTP_200_OK
        event = await receive_event(websocket, ChannelEventResource.ORGANIZATION_MEMBERS)
        assert event["action"] == ChannelEventAction.UPDATED


@pytest.mark.asyncio
async def test_organization_members_broadcasts_on_group_changes(client: AppClient):
    user = await client.get_default_user()
    await user.make_admin()
    topic = Topic("organization_members", organization_id=user.organization_id)

    async with client.connect_channel(topic) as websocket:
        # Group create, rename, and delete all broadcast the same UPDATED event.
        await client.post("/api/groups", json={"name": "Engineering"})
        event = await receive_event(websocket, ChannelEventResource.ORGANIZATION_MEMBERS)
        assert event["action"] == ChannelEventAction.UPDATED

        group = await Group.get(organization_id=user.organization_id, name="Engineering")

        await client.patch(f"/api/groups/{group.id}", json={"name": "Platform"})
        event = await receive_event(websocket, ChannelEventResource.ORGANIZATION_MEMBERS)
        assert event["action"] == ChannelEventAction.UPDATED

        await client.delete(f"/api/groups/{group.id}")
        event = await receive_event(websocket, ChannelEventResource.ORGANIZATION_MEMBERS)
        assert event["action"] == ChannelEventAction.UPDATED


@pytest.mark.asyncio
async def test_organization_members_rejects_cross_org_subscription(client: AppClient):
    await client.get_default_user()
    other_user = await create_user(name="Other Org User")
    other_topic = Topic("organization_members", organization_id=other_user.organization_id)

    async with client.connect_websocket("/channels") as websocket:
        await websocket.send_json(
            {
                "type": ChannelMessageType.SUBSCRIBE,
                "topic_stream": other_topic.stream,
                "topic_params": other_topic.params,
            }
        )
        response = await websocket.receive_json()
        assert response["type"] == ChannelMessageType.SUBSCRIPTION_REJECTED
