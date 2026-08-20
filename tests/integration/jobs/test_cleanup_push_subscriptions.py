from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.cleanup_push_subscriptions import (
    PUSH_SUBSCRIPTION_RETENTION_DAYS,
    CleanupPushSubscriptionsJob,
)
from app.models.accounts import PushSubscription
from infra.db import allow_soft_deleted
from tests.helpers.factories import create_push_subscription

# Predicate, batching, and no-op behavior live on the model — see
# `tests/integration/models/test_push_subscription.py::test_hard_delete_stale_*`.
# This file only exercises the job-layer wiring: the cutoff is derived from
# `retention_days` and applied to the right model call.


@pytest.mark.asyncio
async def test_job_drives_retention_window():
    """The job's `retention_days` defaults to PUSH_SUBSCRIPTION_RETENTION_DAYS;
    a row one day past it disappears, a row one day inside it survives."""
    now = datetime.now(UTC)
    stale = await create_push_subscription()
    boundary = await create_push_subscription()
    stale.deleted_at = now - timedelta(days=PUSH_SUBSCRIPTION_RETENTION_DAYS + 1)
    boundary.deleted_at = now - timedelta(days=PUSH_SUBSCRIPTION_RETENTION_DAYS - 1)
    await stale.save()
    await boundary.save()

    await CleanupPushSubscriptionsJob().perform()

    async with allow_soft_deleted():
        ids = set(await PushSubscription.all().values_list("id", flat=True))
    assert stale.id not in ids
    assert boundary.id in ids
