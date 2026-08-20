from asyncio import Semaphore, gather
from dataclasses import dataclass
from uuid import UUID

from tortoise.expressions import Q

from app.jobs.content import ContentIndexingJob
from app.jobs.onboarding import CompleteOnboardingMailboxSyncJob
from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.email.thread import EmailMessage, EmailMessageFilters, EmailThread
from config import logger, settings
from config.enums import AuthenticationProvider, JobQueue
from infra.db import transaction
from infra.email import EmailHeaders
from infra.jobs import JobDefinition, enqueue_job
from infra.messaging import Topic
from integrations.google.gmail import GmailMessageExtractor, GmailMessageLoader, get_google_api_client
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from integrations.google.types import GmailMessage, gmail_headers_to_email_headers

ISO_8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


ONBOARDING_SYNC_BATCH_SIZE = 100
ONBOARDING_SYNC_THREAD_CONCURRENCY = 10
ONBOARDING_SYNC_QUERIES = ["in:inbox", "in:sent", "-in:inbox -in:sent -in:drafts -in:spam"]
GMAIL_TIMEOUT_SECONDS_FETCH_MESSAGE_DATA = 300
GMAIL_ONBOARDING_SYNC_ATTACHMENTS_PROCESSING_DELAY_SECONDS = 300
INDEXING_BATCH_DELAY_SECONDS = 120


@dataclass
class OnboardingSyncResult:
    messages_created: int
    max_history_id: str | None


@dataclass
class GmailThreadOnboardingSyncProcessor:
    """Service class for processing Gmail threads during onboarding mailbox sync"""

    user_id: UUID

    async def process_thread_messages(
        self, gmail_account: GmailAccount, external_thread_id: str, messages: list[GmailMessage]
    ) -> OnboardingSyncResult:
        max_history_id = max((int(m.get("historyId", "0")) for m in messages), default=None)

        message_headers = await self._get_message_headers(messages)
        existing_messages = await self._get_existing_messages(messages, message_headers, gmail_account.user.id)

        # Prepare batch data for messages that don't exist
        extractor = GmailMessageExtractor()
        loader = GmailMessageLoader(gmail_account)

        messages_to_create = []
        attachment_jobs = []

        for i, message_data in enumerate(messages):
            external_message_id = message_data.get("id", "")
            headers = message_headers[i]
            message_id = headers.message_id or ""

            # Skip if message already exists
            if self._message_exists(external_message_id, message_id, existing_messages):
                continue

            # Extract body content for batch creation
            payload = message_data.get("payload")
            if payload:
                body_plain, body_html = extractor.extract_email_body(payload)
                messages_to_create.append((message_data, headers, body_plain, body_html))

                # Check for attachments to process later
                attachments_data = extractor.find_attachments(payload)
            else:
                body_plain, body_html = None, None
                messages_to_create.append((message_data, headers, body_plain, body_html))
                attachments_data = []
            if attachments_data:
                attachment_jobs.append(
                    {"external_message_id": external_message_id, "attachments_data": attachments_data}
                )

        # Batch create all messages
        if messages_to_create:
            await loader.create_onboarding_sync_email_records_batch(messages_to_create)

            # Enqueue attachment processing jobs
            for attachment_job_data in attachment_jobs:
                await self._process_message_attachments(gmail_account, attachment_job_data)

            await self._update_thread_metadata_for_thread(external_thread_id, gmail_account)

        return OnboardingSyncResult(
            messages_created=len(messages_to_create),
            max_history_id=str(max_history_id) if max_history_id else None,
        )

    async def _process_message_attachments(self, gmail_account: GmailAccount, attachment_job_data: dict):
        google = await get_google_api_client(gmail_account.user, gmail_account)
        loader = GmailMessageLoader(gmail_account)
        attachments_data = attachment_job_data.get("attachments_data", [])
        external_message_id = attachment_job_data.get("external_message_id")
        if attachments_data:
            email_message = await EmailMessage.get_or_none(
                external_message_id=external_message_id, user_id=gmail_account.user.id
            )
            if not email_message:
                logger.warning(f"Email message {external_message_id} not found for account {gmail_account.id}")
                return

            await loader.process_attachments(google, email_message, attachments_data)

    async def _update_thread_metadata_for_thread(self, external_thread_id: str, gmail_account: GmailAccount):
        """Update thread metadata directly without using a job"""
        thread = await EmailThread.get_or_none(external_thread_id=external_thread_id, creator_id=self.user_id)
        if not thread:
            logger.warning(
                f"Email thread with external_thread_id {external_thread_id} not found for user {self.user_id}"
            )
            return

        async with transaction() as connection:
            await thread.update_metadata_from_messages(using_db=connection)
            await thread.refresh_from_db(using_db=connection)
            await enqueue_job(ContentIndexingJob.from_model(thread.organization_id, thread), using_db=connection)
        await Mailbox.sync(thread)

    async def _get_existing_messages(
        self, messages: list[GmailMessage], message_headers: list[EmailHeaders], user_id: UUID
    ) -> set[tuple[str, str]]:
        """Parse headers and batch check for existing messages"""
        external_ids = []
        message_ids = []

        for i, message_data in enumerate(messages):
            external_id = message_data.get("id")
            if external_id:
                external_ids.append(external_id)

            message_id = message_headers[i].message_id or ""
            if message_id:
                message_ids.append(message_id)

        if not external_ids and not message_ids:
            return set()

        query = None
        if external_ids and message_ids:
            query = EmailMessage.filter(
                Q(user_id=user_id, external_message_id__in=external_ids)
                | Q(user_id=user_id, message_id__in=message_ids)
            )
        elif external_ids:
            query = EmailMessage.filter(Q(user_id=user_id, external_message_id__in=external_ids))
        elif message_ids:
            query = EmailMessage.filter(Q(user_id=user_id, message_id__in=message_ids))

        if not query:
            return set()

        existing_messages = await query.values_list("external_message_id", "message_id")

        return set(existing_messages)

    async def _get_message_headers(self, messages: list[GmailMessage]) -> list[EmailHeaders]:
        message_headers = []

        for message_data in messages:
            headers_data = message_data.get("payload", {}).get("headers", [])
            headers = gmail_headers_to_email_headers(headers_data)
            message_headers.append(headers)

        return message_headers

    def _message_exists(
        self, external_message_id: str, message_id: str, existing_messages: set[tuple[str, str]]
    ) -> bool:
        """Check if message exists in the set of existing messages"""
        return any(ext_id == external_message_id or msg_id == message_id for ext_id, msg_id in existing_messages)


class OnboardingMailboxSyncGmailJob(JobDefinition):
    default_queue = JobQueue.ONBOARDING_SYNC
    user_id: UUID
    page_token: str | None = None
    current_query_index: int = 0

    async def perform(self):
        gmail_account = await GmailAccount.get_or_none(user_id=self.user_id).prefetch_related("user__oauth_tokens")
        if not gmail_account:
            return

        user = gmail_account.user
        google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE) if user else None
        if not user or not google_token or not google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
            return

        # Initialize onboarding mailbox sync tracking on first run
        if self.current_query_index == 0 and not gmail_account.onboarding_mailbox_sync_started_at:
            await gmail_account.start_onboarding_mailbox_sync()
            await user.mark_onboarding_mailbox_sync_started()
            # The mailbox page renders before the worker picks up this job, so the
            # syncing banner is absent on first paint. Push it in via the
            # `inbox_progress` channel so the user sees it without a refresh.
            await Topic("inbox_progress", user_id=user.id).broadcast()

        total_synced = await EmailMessage.filter(EmailMessageFilters.by_user(self.user_id)).count()
        if total_synced >= settings.email_messages_onboarding_sync_limit:
            await self._complete_onboarding_mailbox_sync(gmail_account, "reached max messages")
            return

        if self.current_query_index >= len(ONBOARDING_SYNC_QUERIES):
            await self._complete_onboarding_mailbox_sync(gmail_account, "all queries processed")
            return

        current_query = ONBOARDING_SYNC_QUERIES[self.current_query_index]

        google = await get_google_api_client(gmail_account.user, gmail_account)
        processor = GmailThreadOnboardingSyncProcessor(self.user_id)

        threads_response = await google.list_threads(
            query=current_query, max_results=ONBOARDING_SYNC_BATCH_SIZE, page_token=self.page_token
        )

        if not threads_response:
            logger.info(f"No response from Gmail API for user {user.id} query: {current_query}")
            await self._enqueue_next_query(user.id, gmail_account)
            return

        threads = threads_response.get("threads", [])
        if not threads:
            logger.info(f"No more threads found for user {user.id} query: {current_query}")

            await self._enqueue_next_query(user.id, gmail_account)
            return

        # Deduplicate thread IDs — the same thread can appear in multiple Gmail queries
        seen_thread_ids: set[str] = set()
        unique_threads = []
        for thread in threads:
            thread_id = thread["id"]
            if thread_id not in seen_thread_ids:
                seen_thread_ids.add(thread_id)
                unique_threads.append(thread)

        # Process threads in this batch
        semaphore = Semaphore(ONBOARDING_SYNC_THREAD_CONCURRENCY)

        async def process_thread(external_thread_id: str):
            async with semaphore:
                # Per-task client so concurrent fetches don't share a googleapiclient Resource
                # (not thread-safe). Each task gets its own credentials, Http, and Resource.
                task_google = await get_google_api_client(gmail_account.user, gmail_account)
                thread_data = await task_google.fetch_thread_data(external_thread_id)
                if not thread_data:
                    raise ValueError(f"Gmail thread {external_thread_id} not found for user {self.user_id}")

                return await processor.process_thread_messages(
                    gmail_account, external_thread_id, thread_data.get("messages", [])
                )

        results = await gather(*[process_thread(thread["id"]) for thread in unique_threads])

        # Advance history_id to track onboarding progress
        max_history_id = max(
            (int(r.max_history_id) for r in results if r and r.max_history_id),
            default=None,
        )
        if max_history_id and gmail_account.is_history_newer(str(max_history_id)):
            await gmail_account.mark_synced(str(max_history_id))

        # Check if we need to continue with the next page or next query
        next_page_token = threads_response.get("nextPageToken") if threads_response else None
        if next_page_token:
            await enqueue_job(
                OnboardingMailboxSyncGmailJob(
                    user_id=user.id,
                    page_token=next_page_token,
                    current_query_index=self.current_query_index,
                    unique=True,
                )
            )
        else:
            await self._enqueue_next_query(user.id, gmail_account)

    async def _enqueue_next_query(self, user_id: UUID, gmail_account: GmailAccount):
        next_query_index = self.current_query_index + 1

        if next_query_index < len(ONBOARDING_SYNC_QUERIES):
            logger.info(f"Enqueuing next query for user {user_id}: {ONBOARDING_SYNC_QUERIES[next_query_index]}")

            await enqueue_job(
                OnboardingMailboxSyncGmailJob(
                    user_id=user_id,
                    page_token=None,
                    current_query_index=next_query_index,
                    unique=True,
                )
            )
        else:
            await self._complete_onboarding_mailbox_sync(gmail_account, "all queries processed")

    async def _complete_onboarding_mailbox_sync(self, gmail_account: GmailAccount, reason: str):
        logger.info(f"Gmail onboarding mailbox sync for user {self.user_id} completed - {reason}")

        # Mark gmail account onboarding mailbox sync complete
        await gmail_account.complete_onboarding_mailbox_sync()

        # Delegate to app-layer for orchestration
        await enqueue_job(CompleteOnboardingMailboxSyncJob(user_id=self.user_id))


class ProgressiveThreadMessageSyncJob(JobDefinition):
    """Ensures that all messages in a thread are present when a new thread is created in the application.
    Guarantees that we have all messages for a thread that is receiving a new message.
    """

    default_queue = JobQueue.ONBOARDING_SYNC
    user_id: UUID
    thread_id: UUID

    async def perform(self):
        gmail_account = await GmailAccount.get_or_none(user_id=self.user_id).prefetch_related("user__oauth_tokens")
        if not gmail_account:
            return

        user = gmail_account.user
        google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE) if user else None
        if not user or not google_token or not google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
            return

        thread = await EmailThread.get_or_none(id=self.thread_id, creator_id=self.user_id).prefetch_related("messages")
        if not thread or not thread.external_thread_id:
            return

        google = await get_google_api_client(gmail_account.user, gmail_account)
        processor = GmailThreadOnboardingSyncProcessor(self.user_id)

        thread_data = await google.fetch_thread_data(thread.external_thread_id)
        if not thread_data:
            logger.warning(f"Gmail thread {thread.external_thread_id} not found for user {self.user_id}")
            return

        messages = thread_data.get("messages", [])
        new_message_count = len(messages) - len(thread.messages)

        if new_message_count <= 0:
            return

        logger.info(
            f"Thread message sync starting for thread {thread.external_thread_id} - {new_message_count} new messages"
        )

        await processor.process_thread_messages(gmail_account, thread.external_thread_id, messages)
