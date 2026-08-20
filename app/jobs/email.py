from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.jobs.content import ContentIndexingJob
from app.models.accounts import User
from app.models.workspaces.email.thread import EmailMessage, EmailThread, SendSideEffectOptions
from config import logger
from config.enums import EmailMessageType, JobQueue
from infra.db import transaction
from infra.email import get_email_client
from infra.jobs import Job, JobDefinition, enqueue_job

# How long a scheduled draft may sit past its send time before the sweeper treats it as stranded
# (its Cloud Task was lost/never dispatched) and re-enqueues the send. Comfortably longer than a
# healthy fire, so a normally-firing draft is never swept.
SCHEDULED_SEND_OVERDUE_GRACE = timedelta(minutes=15)

# Bound the per-run scan; overdue drafts are a rare failure mode, and any remainder is caught on the
# next tick. Logged when hit so the cap is never silent.
SCHEDULED_SEND_SWEEP_LIMIT = 500


class ScheduledDraftSendJob(JobDefinition):
    default_queue = JobQueue.UI
    email_thread_id: UUID
    message_id: UUID
    sender_user_id: UUID | None = None
    should_archive: bool = False

    async def perform(self):
        # Fire the scheduled draft exactly as the immediate-send endpoint does: transition to
        # SENDING and hand delivery to the email client (which enqueues SendEmailThroughGmailJob).
        # The row lock is the authoritative race arbiter against unschedule/delete/duplicate fire —
        # if the message is no longer a scheduled draft (unscheduled, deleted, or already
        # delivered) there is nothing to do.
        async with transaction() as connection:
            locked = await EmailMessage.select_for_update().using_db(connection).get_or_none(id=self.message_id)
            if not locked or locked.message_type != EmailMessageType.DRAFT or not locked.is_scheduled:
                return

            thread = await EmailThread.get_or_none(id=self.email_thread_id, using_db=connection).prefetch_related(
                "messages", "workspace"
            )
            if not thread:
                return

            sending_user_id = self.sender_user_id or locked.user_id
            sender = await User.get_or_none(
                id=sending_user_id, organization_id=thread.organization_id, using_db=connection
            )
            if not sender or not thread.can_reply(sender):
                logger.warning(f"User {sending_user_id} not authorized to send on thread {self.email_thread_id}")
                return

            draft = await thread.get_draft(EmailMessageType.DRAFT, using_db=connection)
            if not draft:
                return

            await thread.send_draft(
                draft,
                sender,
                # pin_to_inbox=False: a scheduled fire respects the entry's state at send time.
                # If the sender archived the thread between scheduling and now, it stays archived
                # (surfacing in Sent) rather than being resurrected into the inbox.
                SendSideEffectOptions(should_archive=self.should_archive, pin_to_inbox=False),
                get_email_client(),
                using_db=connection,
            )

        await enqueue_job(ContentIndexingJob.from_model(thread.organization_id, thread))


class SweepOverdueScheduledDraftsJob(JobDefinition):
    """Safety net for scheduled sends whose Cloud Task was lost or never dispatched.

    The precise `perform_at` task is the primary trigger; `EnqueueOutboxJob` already recovers a task
    that was never dispatched (`task_name IS NULL`), but a task that was dispatched and then dropped
    by Cloud Tasks is only *terminated* by `TerminateDeadCloudTasksJob`, never re-fired. This job
    reconciles on message state instead: any draft still scheduled well past its send time gets a
    fresh `ScheduledDraftSendJob`. Re-enqueue is safe — the fire job's `select_for_update` guard
    makes a duplicate delivery a no-op if the original task also fires.
    """

    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        cutoff = datetime.now(UTC) - SCHEDULED_SEND_OVERDUE_GRACE
        overdue = (
            await EmailMessage.filter(
                message_type=EmailMessageType.DRAFT,
                scheduled_for__isnull=False,
                scheduled_for__lte=cutoff,
            )
            .only("id")
            .limit(SCHEDULED_SEND_SWEEP_LIMIT)
        )
        if not overdue:
            return

        if len(overdue) == SCHEDULED_SEND_SWEEP_LIMIT:
            logger.warning(f"Sweeping {SCHEDULED_SEND_SWEEP_LIMIT} overdue scheduled drafts (capped); more remain")
        else:
            logger.warning(f"Sweeping {len(overdue)} overdue scheduled draft(s)")

        for message in overdue:
            # Lock and re-check per row: the "lost" task may in fact fire concurrently and
            # mark the draft SENDING (clearing scheduled_for / scheduled_send_job_id). Re-pointing
            # the id without the lock could resurrect a stale job id on an already-sent message.
            async with transaction() as connection:
                locked = await EmailMessage.select_for_update().using_db(connection).get_or_none(id=message.id)
                if not locked or locked.message_type != EmailMessageType.DRAFT or not locked.is_scheduled:
                    continue
                job = await enqueue_job(await self._rebuild_send_job(locked), using_db=connection)
                # Keep scheduled_send_job_id pointing at the live job so unschedule/delete cancel
                # the re-fired task rather than the lost one.
                locked.scheduled_send_job_id = job.id
                await locked.save(using_db=connection, update_fields=["scheduled_send_job_id"])

    async def _rebuild_send_job(self, message: EmailMessage) -> ScheduledDraftSendJob:
        # Recover the original archive disposition from the job that was meant to fire (that option
        # lives only in its args); fall back to a plain send if that row is gone. perform_at is
        # intentionally unset so the rebuilt job fires immediately.
        if message.scheduled_send_job_id:
            original = await Job.get_or_none(id=message.scheduled_send_job_id)
            if original and original.job_type == ScheduledDraftSendJob.job_type():
                return ScheduledDraftSendJob(**original.job_details)
        return ScheduledDraftSendJob(
            email_thread_id=message.thread_id,
            message_id=message.id,
            sender_user_id=message.user_id,
        )
