from datetime import UTC, datetime, timedelta

import pytest
from tortoise.exceptions import IntegrityError

from app.models.accounts import PushSubscription, User
from infra.db import allow_soft_deleted
from tests.helpers.factories import create_push_subscription, create_user


@pytest.mark.asyncio
async def test_create_and_unique_active_endpoint():
    user = await create_user()
    subscription = await create_push_subscription(
        user_id=user.id,
        endpoint="https://fcm.googleapis.com/fcm/send/abc123",
        platform="Chrome on macOS",
    )

    assert subscription.id is not None
    assert subscription.deleted_at is None

    # The partial unique index forbids two *active* rows for the same endpoint.
    with pytest.raises(IntegrityError):
        await create_push_subscription(user_id=user.id, endpoint="https://fcm.googleapis.com/fcm/send/abc123")


@pytest.mark.asyncio
async def test_soft_delete_then_resubscribe_same_endpoint():
    user = await create_user()
    endpoint = "https://fcm.googleapis.com/fcm/send/dup"
    first = await create_push_subscription(user_id=user.id, endpoint=endpoint)
    await first.soft_delete()

    # Soft-deleted row doesn't occupy the active slot, so re-enabling on the same
    # endpoint can create a fresh row without colliding with the prior one.
    second = await create_push_subscription(user_id=user.id, endpoint=endpoint)
    assert second.id != first.id

    # Default manager hides soft-deleted rows.
    visible = await PushSubscription.filter(user_id=user.id).all()
    assert [s.id for s in visible] == [second.id]

    async with allow_soft_deleted():
        all_rows = await PushSubscription.filter(user_id=user.id).all()
    assert {s.id for s in all_rows} == {first.id, second.id}


@pytest.mark.asyncio
async def test_restore_clears_deleted_at():
    subscription = await create_push_subscription()
    await subscription.soft_delete()
    assert subscription.is_deleted

    await subscription.restore()
    assert subscription.deleted_at is None


@pytest.mark.asyncio
async def test_user_delete_cascades_to_push_subscription():
    user = await create_user()
    subscription = await create_push_subscription(user_id=user.id)

    await User.filter(id=user.id).delete()

    async with allow_soft_deleted():
        remaining = await PushSubscription.filter(id=subscription.id).first()
    assert remaining is None


async def _soft_delete_at(subscription: PushSubscription, when: datetime) -> None:
    # `soft_delete()` writes now(); the retention contract keys on age so the
    # test needs to set the timestamp explicitly.
    subscription.deleted_at = when
    await subscription.save()


@pytest.mark.asyncio
async def test_hard_delete_stale_drops_long_soft_deleted_rows_only():
    """The retention contract: rows whose `deleted_at` predates the cutoff are
    gone; rows inside the window stay; active rows are untouched even when
    older than the cutoff."""
    now = datetime.now(UTC)
    long_gone = await create_push_subscription()
    just_deleted = await create_push_subscription()
    active = await create_push_subscription()

    await _soft_delete_at(long_gone, now - timedelta(days=31))
    await _soft_delete_at(just_deleted, now - timedelta(days=1))

    deleted = await PushSubscription.hard_delete_stale(older_than=now - timedelta(days=30), batch_size=100)
    assert deleted == 1

    async with allow_soft_deleted():
        remaining = set(await PushSubscription.all().values_list("id", flat=True))
    assert long_gone.id not in remaining
    assert {just_deleted.id, active.id} <= remaining


@pytest.mark.asyncio
async def test_hard_delete_stale_no_op_when_empty():
    """Empty queue is the steady state — the call must return 0 without raising."""
    active = await create_push_subscription()
    recently_deleted = await create_push_subscription()
    await _soft_delete_at(recently_deleted, datetime.now(UTC) - timedelta(days=1))

    deleted = await PushSubscription.hard_delete_stale(
        older_than=datetime.now(UTC) - timedelta(days=30), batch_size=100
    )
    assert deleted == 0

    async with allow_soft_deleted():
        assert await PushSubscription.filter(id=active.id).exists()
        assert await PushSubscription.filter(id=recently_deleted.id).exists()


@pytest.mark.asyncio
async def test_hard_delete_stale_caps_at_batch_size():
    """A single call hard-deletes at most batch_size rows. Caller's next run
    drains the rest — keeps a backlog from monopolizing one worker."""
    now = datetime.now(UTC)
    stale = [await create_push_subscription() for _ in range(5)]
    for subscription in stale:
        await _soft_delete_at(subscription, now - timedelta(days=31))

    deleted = await PushSubscription.hard_delete_stale(older_than=now - timedelta(days=30), batch_size=2)
    assert deleted == 2

    async with allow_soft_deleted():
        remaining = await PushSubscription.filter(id__in=[s.id for s in stale]).count()
    assert remaining == 3
