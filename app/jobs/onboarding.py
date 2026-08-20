from uuid import UUID

from app.jobs.email_contacts import UpdateContactInteractionsJob
from app.jobs.mailers import SendOnboardingMailboxSyncCompletedEmailJob
from app.jobs.research import start_research_from_question
from app.models.accounts import User
from app.models.commands import ResearchQuestion
from config import logger
from config.enums import JobQueue
from infra.db import transaction
from infra.jobs import JobDefinition, enqueue_job
from infra.messaging import Topic


class CompleteOnboardingMailboxSyncJob(JobDefinition):
    """Mark user's onboarding mailbox sync complete and trigger post-sync actions.

    Email provider integrations (Gmail, Outlook, etc.) should enqueue this job
    when their initial onboarding mailbox sync/backfill completes. This job:
    1. Updates User.onboarding_mailbox_sync_completed_at timestamp
    2. Orchestrates all post-completion actions (notifications, contact updates, etc.)

    The job is idempotent - safe to call multiple times for the same user.
    """

    default_queue = JobQueue.UI
    user_id: UUID

    async def perform(self):
        user = await User.get_or_none(id=self.user_id)
        if not user:
            return

        if not user.is_onboarding_mailbox_sync_complete:
            await user.mark_onboarding_mailbox_sync_complete()
            await Topic("inbox_progress", user_id=user.id).broadcast()

            await enqueue_job(SendOnboardingMailboxSyncCompletedEmailJob(user_id=user.id))
            await enqueue_job(UpdateContactInteractionsJob(user_id=user.id, window_hours=None))
            await self._start_pending_research(user)

    async def _start_pending_research(self, user: User):
        """Start any research questions that were waiting for onboarding mailbox sync to complete."""
        pending_commands = (
            await ResearchQuestion.filter(ResearchQuestion.filters.by_creator(user.id))
            .filter(ResearchQuestion.filters.pending)
            .prefetch_related("creator__organization")
        )

        if not pending_commands:
            return

        for command in pending_commands:
            try:
                async with transaction() as connection:
                    await start_research_from_question(command, connection)

                logger.info(f"Started pending research command {command.id} for user {user.id}")
            except Exception:
                logger.exception(f"Failed to start pending research command {command.id} for user {user.id}")
