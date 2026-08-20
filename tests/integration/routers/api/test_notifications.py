import pytest
from fastapi import status

from app.models.collaboration.workspace import Subscription, SubscriptionPreference
from app.models.workspaces.goals import Goal
from app.models.workspaces.posts import PostGroupMute
from config import settings
from config.enums import SubscriptionLevel
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_goal,
    create_group,
    create_group_member,
    create_post_group_mute,
    create_push_subscription,
)


@pytest.mark.asyncio
async def test_get_notifications(client: AppClient):
    user = await client.get_default_user()
    # User belongs to two groups; one is muted, the other is not.
    group_a = await create_group(organization_id=user.organization_id, name="Marketing")
    group_b = await create_group(organization_id=user.organization_id, name="Engineering")
    await create_group_member(group_a.id, user.id)
    await create_group_member(group_b.id, user.id)
    await create_post_group_mute(user_id=user.id, group_id=group_b.id)

    response = await client.get("/api/notifications")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    types = {p["resource_type"] for p in data["preferences"]}
    assert types == {"Chat", "Document", "EmailThread", "Goal", "Meeting", "Post"}

    # Each preference is pure data — no presentation strings, no aggregate counts.
    post_pref = next(p for p in data["preferences"] if p["resource_type"] == "Post")
    assert "important_includes" not in post_pref
    assert "existing_count" not in post_pref
    assert post_pref["default_level"] in ("all", "broadcasts", "relevant_only")

    # Group mutes: alphabetical, both member groups present, muted flag only on group_b.
    mutes = data["post_group_mutes"]
    assert [m["group_name"] for m in mutes] == ["Engineering", "Marketing"]
    eng = next(m for m in mutes if m["group_name"] == "Engineering")
    mkt = next(m for m in mutes if m["group_name"] == "Marketing")
    assert eng["muted"] is True
    assert mkt["muted"] is False

    # Push field is always present; vapid key flows through here (D3) and the
    # devices list is empty for a user with no registered devices.
    assert data["push"] == {
        "devices": [],
        "vapid_public_key": settings.vapid_public_key,
        "working_hours": None,
    }


@pytest.mark.asyncio
async def test_get_notifications_includes_push_devices(client: AppClient):
    user = await client.get_default_user()
    active = await create_push_subscription(user_id=user.id, platform="Chrome on macOS")
    soft_deleted = await create_push_subscription(user_id=user.id)
    await soft_deleted.soft_delete()

    response = await client.get("/api/notifications")
    devices = response.json()["push"]["devices"]
    assert [d["id"] for d in devices] == [str(active.id)]
    assert devices[0]["platform"] == "Chrome on macOS"


@pytest.mark.asyncio
async def test_patch_preference_leaves_existing_subscriptions(client: AppClient):
    # Policy is forward-looking by design: flipping the default never touches
    # existing per-resource Subscription rows. Cleanup is a different surface.
    user = await client.get_default_user()
    goal_a = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="A")
    goal_b = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="B")
    # In the explicit-rows world, no auto-subscribe row exists. Write explicit rows
    # to simulate the user having previously clicked the bell on these resources.
    sub_a = await Subscription.create(
        workspace_id=goal_a.workspace_id, subscriber_id=user.id, level=SubscriptionLevel.ALL
    )
    sub_b = await Subscription.create(
        workspace_id=goal_b.workspace_id, subscriber_id=user.id, level=SubscriptionLevel.ALL
    )

    response = await client.patch(
        "/api/notifications/goal",
        json={"default_level": "relevant_only"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["default_level"] == "relevant_only"

    # SubscriptionPreference flips, existing Subscription rows untouched.
    pref = await SubscriptionPreference.get(subscriber_id=user.id, resource_type=Goal.record_type)
    assert pref.default_level == SubscriptionLevel.RELEVANT_ONLY

    sub_a_reloaded = await Subscription.get(id=sub_a.id)
    sub_b_reloaded = await Subscription.get(id=sub_b.id)
    assert sub_a_reloaded.level == SubscriptionLevel.ALL
    assert sub_b_reloaded.level == SubscriptionLevel.ALL


@pytest.mark.asyncio
async def test_patch_preference_unknown_resource_type(client: AppClient):
    await client.get_default_user()
    response = await client.patch(
        "/api/notifications/nope",
        json={"default_level": "all"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_patch_preference_broadcasts_only_valid_for_post(client: AppClient):
    await client.get_default_user()

    # Post accepts broadcasts.
    response = await client.patch("/api/notifications/post", json={"default_level": "broadcasts"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["default_level"] == "broadcasts"

    # Other resource types reject it.
    response = await client.patch("/api/notifications/chat", json={"default_level": "broadcasts"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_patch_post_group_mute_lifecycle(client: AppClient):
    user = await client.get_default_user()
    group = await create_group(organization_id=user.organization_id, name="Design")
    await create_group_member(group.id, user.id)

    response = await client.patch(
        f"/api/notifications/posts/groups/{group.id}/mute",
        json={"muted": True},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["muted"] is True
    assert await PostGroupMute.exists(user_id=user.id, group_id=group.id)

    # Mute again → idempotent (still just one row, response still muted).
    response = await client.patch(
        f"/api/notifications/posts/groups/{group.id}/mute",
        json={"muted": True},
    )
    assert response.json()["muted"] is True
    assert await PostGroupMute.filter(user_id=user.id, group_id=group.id).count() == 1

    # Unmute → deletes the row.
    response = await client.patch(
        f"/api/notifications/posts/groups/{group.id}/mute",
        json={"muted": False},
    )
    assert response.json()["muted"] is False
    assert not await PostGroupMute.exists(user_id=user.id, group_id=group.id)

    # Unmute when no row exists → idempotent (still no row, still unmuted).
    response = await client.patch(
        f"/api/notifications/posts/groups/{group.id}/mute",
        json={"muted": False},
    )
    assert response.json()["muted"] is False
    assert not await PostGroupMute.exists(user_id=user.id, group_id=group.id)


@pytest.mark.asyncio
async def test_patch_post_group_mute_unknown_group(client: AppClient):
    await client.get_default_user()
    other_org_group = await create_group(name="Other")
    response = await client.patch(
        f"/api/notifications/posts/groups/{other_org_group.id}/mute",
        json={"muted": True},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_patch_post_group_mute_rejects_non_member(client: AppClient):
    user = await client.get_default_user()
    # Group exists in the user's org, but user isn't a member.
    group = await create_group(organization_id=user.organization_id, name="Unjoined")

    response = await client.patch(
        f"/api/notifications/posts/groups/{group.id}/mute",
        json={"muted": True},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert not await PostGroupMute.exists(user_id=user.id, group_id=group.id)
