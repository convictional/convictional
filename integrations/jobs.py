from app.jobs.mailbox import UnsnoozeMailboxEntryJob
from app.jobs.maintenance import HardDeleteUserJob
from app.models.accounts import User
from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.email.thread import EmailThread
from config import logger
from config.enums import AuthenticationProvider, Integration, JobQueue
from infra.jobs import JobDefinition, bulk_enqueue_jobs
from integrations.google.gmail import get_google_api_client
from integrations.google.jobs.gmail import RestoreGmailInboxLabelJob
from integrations.google.models import GmailAccount
from integrations.google.oauth import revoke_google_oauth_token
from integrations.slack.models import SlackContent


class HardDeleteUserWithIntegrationsJob(HardDeleteUserJob):
    """
    Extends HardDeleteUserJob to clean up integrations before deletion.

    Use this job instead of HardDeleteUserJob to ensure integration-specific
    cleanup is performed. For example, ensuring Gmail push notification watches
    are properly stopped before user deletion.
    """

    async def perform(self):
        # Stop Gmail watch BEFORE deletion
        user = await User.get_or_none(email=self.user_email).prefetch_related("oauth_tokens")
        if not user:
            return

        if user.is_integrated_with(Integration.GMAIL):
            await self._stop_gmail_watch(user)

        # Revoke after stopping the watch (which still needs working credentials) but before
        # deletion (which needs the token row to still exist).
        await self._revoke_google_oauth(user)

        if user.is_integrated_with(Integration.SLACK):
            slack_content_queryset = SlackContent.filter(
                SlackContent.filters.private & SlackContent.filters.by_accessor(user.id)
            )
            await self._cleanup_content(user, self.batch_size, slack_content_queryset)

        # Then call parent to perform the full deletion
        await super().perform()

    async def _stop_gmail_watch(self, user: User):
        google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
        if not google_token or not user.is_integrated_with(Integration.GMAIL):
            return

        gmail_account = await GmailAccount.get_or_none(GmailAccount.filters.by_user(user.id))
        if not gmail_account:
            return

        try:
            google = await get_google_api_client(user, gmail_account)
            await google.stop_watch()
            logger.info(f"Stopped Gmail watch for user {user.id} before deletion")
        except Exception:
            logger.exception(f"Failed to stop Gmail watch for user {user.id}")
            # Don't raise - allow deletion to proceed

    async def _revoke_google_oauth(self, user: User):
        """Revoke the Google OAuth grant at Google before the user's rows are deleted. Without
        this the grant survives deletion, so the user's next login silently reconstitutes the
        account (and its Gmail connection) via include_granted_scopes — i.e. a hard delete that
        doesn't actually keep them gone."""
        google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE)
        if not google_token:
            return

        token = google_token.refresh_token or google_token.access_token
        if not token:
            return

        try:
            await revoke_google_oauth_token(token)
            logger.info(f"Revoked Google OAuth grant for user {user.id} before deletion")
        except Exception:
            logger.exception(f"Failed to revoke Google OAuth grant for user {user.id}")
            # Don't raise - allow deletion to proceed


class CheckSnoozedMailboxEntriesJob(JobDefinition):
    """Recurring scan (invoked by the GCP Cloud Scheduler task) that wakes snoozed
    mailbox entries when their snooze expires. Lives at the integrations root rather
    than in a single integration because it composes the app-level UnsnoozeMailboxEntryJob
    with the Gmail-specific RestoreGmailInboxLabelJob."""

    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        entries = await MailboxEntry.filter(MailboxEntry.filters.is_snooze_expiring())
        if not entries:
            return
        logger.info(f"Unsnoozing {len(entries)} mailbox entries")

        await bulk_enqueue_jobs([UnsnoozeMailboxEntryJob(mailbox_entry_id=entry.id) for entry in entries])

        email_entries = [entry for entry in entries if entry.resource_type == EmailThread.__name__]
        if email_entries:
            await bulk_enqueue_jobs([RestoreGmailInboxLabelJob(mailbox_entry_id=entry.id) for entry in email_entries])
