from datetime import UTC, datetime

import pytest
from tortoise.exceptions import IntegrityError

from app.models.accounts import PushSubscription
from app.models.collaboration.workspace import Event, Notification
from app.models.workspaces.goals import Goal
from config.enums import DeliveryChannel, EventAction
from tests.helpers.factories import create_goal, create_push_subscription, create_user


async def _create_event(goal: Goal, creator_id) -> Event:
    return await Event.create(
        recordable_id=goal.id,
        recordable_type="Goal",
        action=EventAction.GOAL_CREATED,
        workspace_id=goal.workspace_id,
        creator_id=creator_id,
    )


@pytest.mark.asyncio
async def test_notification_defaults_to_email_channel():
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    event = await _create_event(goal, user.id)

    notification = await Notification.create(event_id=event.id, user_id=user.id)

    assert notification.channel == DeliveryChannel.EMAIL
    assert notification.device_id is None
    assert notification.device_label_snapshot is None


@pytest.mark.asyncio
async def test_push_notification_carries_device_and_label():
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    event = await _create_event(goal, user.id)
    subscription = await create_push_subscription(user_id=user.id, platform="Chrome on macOS")

    notification = await Notification.create(
        event_id=event.id,
        user_id=user.id,
        channel=DeliveryChannel.PUSH,
        device_id=subscription.id,
        device_label_snapshot=subscription.platform,
        delivered_at=datetime.now(UTC),
    )

    assert notification.channel == DeliveryChannel.PUSH
    assert notification.device_id == subscription.id
    assert notification.device_label_snapshot == "Chrome on macOS"


@pytest.mark.asyncio
async def test_unique_constraint_prevents_duplicate_push_per_device():
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    event = await _create_event(goal, user.id)
    subscription = await create_push_subscription(user_id=user.id)

    await Notification.create(
        event_id=event.id, user_id=user.id, channel=DeliveryChannel.PUSH, device_id=subscription.id
    )

    with pytest.raises(IntegrityError):
        await Notification.create(
            event_id=event.id, user_id=user.id, channel=DeliveryChannel.PUSH, device_id=subscription.id
        )


@pytest.mark.asyncio
async def test_unique_constraint_allows_distinct_channels_and_devices():
    # Postgres treats NULLs as distinct in unique indexes (default NULLS DISTINCT),
    # so multiple email rows (device_id IS NULL) for the same (event, user) still co-exist.
    # Push rows for different devices co-exist because device_id differs.
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    event = await _create_event(goal, user.id)
    subscription_a = await create_push_subscription(user_id=user.id)
    subscription_b = await create_push_subscription(user_id=user.id)

    email_row = await Notification.create(event_id=event.id, user_id=user.id)
    email_row_duplicate = await Notification.create(event_id=event.id, user_id=user.id)
    push_a = await Notification.create(
        event_id=event.id, user_id=user.id, channel=DeliveryChannel.PUSH, device_id=subscription_a.id
    )
    push_b = await Notification.create(
        event_id=event.id, user_id=user.id, channel=DeliveryChannel.PUSH, device_id=subscription_b.id
    )

    assert email_row.id != email_row_duplicate.id
    assert push_a.id != push_b.id


@pytest.mark.asyncio
async def test_push_subscription_delete_sets_device_id_null():
    # ON DELETE SET NULL preserves the ledger row when the subscription is
    # later hard-deleted; the device_label_snapshot is what keeps the audit trail.
    user = await create_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id)
    event = await _create_event(goal, user.id)
    subscription = await create_push_subscription(user_id=user.id, platform="Safari on iOS")
    notification = await Notification.create(
        event_id=event.id,
        user_id=user.id,
        channel=DeliveryChannel.PUSH,
        device_id=subscription.id,
        device_label_snapshot=subscription.platform,
        delivered_at=datetime.now(UTC),
    )

    await PushSubscription.filter(id=subscription.id).delete()

    reloaded = await Notification.get(id=notification.id)
    assert reloaded.device_id is None
    assert reloaded.device_label_snapshot == "Safari on iOS"
    assert reloaded.channel == DeliveryChannel.PUSH
