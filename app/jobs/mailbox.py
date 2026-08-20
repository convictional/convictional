from uuid import UUID

from app.models.collaboration.mailbox import Mailbox, MailboxEntry, mailbox_entry_for
from app.models.collaboration.workspace import Event
from config import logger
from config.enums import JobQueue
from infra.jobs import JobDefinition


class SyncMailboxJob(JobDefinition):
    """Refreshes the inbox view of a resource for every user who cares about it.

    Notifier.record_and_notify enqueues one of these per recorded event. The
    job recomputes affected rows from current state, so it's idempotent and
    safe to retry. One job per event (not per recipient) keeps it the single
    writer for inbox state on Notifier-mediated mutations.

    Per-person row outcomes are decided by `InboxUpdate.for_event` (in mailbox.py):
    reach (ALL-level + @mention + DM force-include, from
    `SubscriberResolver.resolve_for_inbox`) decides whether the event alerts you
    or — if you sent it — just refreshes your row; an existing live row keeps
    tracking content even below ALL. The settings-page promise that "@mentions
    and direct asks always reach you" is the reach half; row continuity is a
    mailbox-UX concern layered on at the mailbox boundary.
    """

    default_queue = JobQueue.UI
    event_id: UUID

    async def perform(self):
        event = await Event.get_or_none(id=self.event_id).prefetch_related("workspace")
        if not event:
            return

        resource = await event.workspace.fetch_resource_or_none()
        if not resource:
            return

        if not mailbox_entry_for(resource):
            return

        # Reach — including direct-recipient derivation — lives on SubscriberResolver, invoked
        # inside Mailbox.sync. The job stays a thin post-commit shell.
        await Mailbox.sync(resource, event=event)


class UnsnoozeMailboxEntryJob(JobDefinition):
    """Returns a single snoozed entry to the inbox when its snooze expires, for any
    resource type. Enqueued per expiring entry by CheckSnoozedMailboxEntriesJob."""

    default_queue = JobQueue.MISCELLANEOUS
    mailbox_entry_id: UUID

    async def perform(self):
        mailbox_entry = await MailboxEntry.get_or_none(id=self.mailbox_entry_id).prefetch_related("owner")
        if not mailbox_entry or not mailbox_entry.is_snoozed:
            logger.info(f"Unsnoozing mailbox entry {self.mailbox_entry_id} - not found or not snoozed")
            return
        logger.info(f"Unsnoozing mailbox entry {self.mailbox_entry_id}")

        resource = await mailbox_entry.resource_gid.get_or_none()
        if not resource:
            # The resource was deleted while snoozed. Soft-delete the orphaned entry so future
            # scans stop re-enqueuing it — don't unsnooze, which would resurface a ghost entry
            # pointing at a deleted resource into the inbox as unread.
            await mailbox_entry.soft_delete()
            return

        await Mailbox(mailbox_entry.owner).unsnooze(resource)
