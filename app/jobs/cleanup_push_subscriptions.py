from datetime import UTC, datetime, timedelta

from app.models.accounts import PushSubscription
from config import logger
from config.enums import JobQueue
from infra.jobs import JobDefinition

# Soft-deleted PushSubscription rows are kept around long enough to ride out
# late deliveries and any debugging that needs to inspect them, then garbage-
# collected. 30 days is well past Cloud Tasks's max retry horizon.
PUSH_SUBSCRIPTION_RETENTION_DAYS = 30
PUSH_SUBSCRIPTION_DELETE_BATCH = 500


class CleanupPushSubscriptionsJob(JobDefinition):
    """Daily sweep that hard-deletes long-soft-deleted PushSubscription rows.

    Soft-delete happens in two places: the user disabling a device via the API
    (`api_push_subscriptions_delete`), and the push pipeline observing a 404/410
    from the relay (`_deliver_to_device`). After the retention window the row
    serves no further purpose — the user has either re-enabled (a fresh row)
    or moved on. Active rows are never touched.
    """

    default_queue = JobQueue.MAINTENANCE
    is_recurring = True
    retry_count = 0
    retention_days: int = PUSH_SUBSCRIPTION_RETENTION_DAYS
    batch_size: int = PUSH_SUBSCRIPTION_DELETE_BATCH

    async def perform(self):
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)
        deleted = await PushSubscription.hard_delete_stale(older_than=cutoff, batch_size=self.batch_size)
        if deleted:
            logger.info(f"Hard-deleted {deleted} stale push subscriptions")
