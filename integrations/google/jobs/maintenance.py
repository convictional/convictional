from asyncio import Semaphore, gather
from typing import cast
from uuid import UUID

from tortoise.expressions import Q

from app.models.collaboration.mailbox import MailboxEntry
from app.models.workspaces.email.thread import EmailMessage, EmailThread
from config import logger
from config.enums import AuthenticationProvider, EmailMailboxLabel, JobQueue, MailboxLabel
from config.logging import LoggingContext
from infra.db import GlobalID
from infra.jobs import JobDefinition, enqueue_job
from integrations.google.gmail import get_google_api_client
from integrations.google.jobs.gmail_onboarding_sync import (
    ONBOARDING_SYNC_BATCH_SIZE,
    ONBOARDING_SYNC_THREAD_CONCURRENCY,
    GmailThreadOnboardingSyncProcessor,
    OnboardingSyncResult,
)
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES

BACKFILL_QUERIES = ["in:sent", "-in:inbox -in:drafts -in:spam"]
# Archived stage mirrors the mailbox_archived router filter (app/models/workspaces/email/mailbox.py),
# which excludes only inbox/draft/spam — NOT sent. Sent-then-archived threads appear in mailbox_archived,
# so the backfill must include them. Dedup in GmailThreadOnboardingSyncProcessor handles overlap with
# the sent stage.


def _mailbox_entry_filter_for_stage(query_index: int) -> Q:
    """Build the MailboxEntry Q filter that matches the router view for a given backfill stage.

    Index 0 (sent) mirrors EmailMailboxEntryFilters.sent().
    Index 1 (archived) mirrors EmailMailboxEntryFilters.archived().
    """
    if query_index == 0:
        return Q(labels__contains=[EmailMailboxLabel.SENT])
    return (
        ~Q(labels__contains=[MailboxLabel.INBOX])
        & ~Q(labels__contains=[EmailMailboxLabel.SPAM])
        & ~Q(labels__contains=[EmailMailboxLabel.DRAFT])
        & Q(snoozed_until__isnull=True)
    )


class BackfillGmailEmailsJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    user_id: UUID
    max_messages: int = 10000
    page_token: str | None = None
    current_query_index: int = 0
    messages_created: int = 0
    before_timestamp: int | None = None

    async def perform(self):
        with LoggingContext(user_id=self.user_id):
            if self.messages_created >= self.max_messages:
                logger.info("Gmail backfill skipped: messages_created already at max_messages")
                return

            gmail_account = await GmailAccount.get_or_none(user_id=self.user_id).prefetch_related("user__oauth_tokens")
            if not gmail_account:
                logger.info("Gmail backfill skipped: no GmailAccount for user")
                return

            if not gmail_account.onboarding_mailbox_sync_completed_at:
                logger.info("Gmail backfill skipped: onboarding mailbox sync not completed")
                return

            user = gmail_account.user
            google_token = user.oauth_token_for_provider(AuthenticationProvider.GOOGLE) if user else None
            if not user or not google_token or not google_token.has_scopes(GOOGLE_GMAIL_SCOPES):
                logger.info("Gmail backfill skipped: user, token, or Gmail scopes missing")
                return

            if self.current_query_index >= len(BACKFILL_QUERIES):
                logger.info("Gmail backfill skipped: current_query_index past end of queries")
                return

            before_timestamp = self.before_timestamp
            if not before_timestamp:
                before_timestamp = await self._resolve_before_timestamp()

            current_query = BACKFILL_QUERIES[self.current_query_index]
            if before_timestamp:
                current_query = f"{current_query} before:{before_timestamp}"

            with LoggingContext(
                before_timestamp=before_timestamp or "none",
                query=current_query,
                messages_created=self.messages_created,
                max_messages=self.max_messages,
                query_index=f"{self.current_query_index + 1}/{len(BACKFILL_QUERIES)}",
            ):
                google = await get_google_api_client(gmail_account.user, gmail_account)
                processor = GmailThreadOnboardingSyncProcessor(self.user_id)

                threads_response = await google.list_threads(
                    query=current_query, max_results=ONBOARDING_SYNC_BATCH_SIZE, page_token=self.page_token
                )

                threads = (threads_response or {}).get("threads", [])
                if not threads:
                    await self._enqueue_next_query(self.messages_created)
                    return

                seen_thread_ids: set[str] = set()
                unique_threads = []
                for thread in threads:
                    thread_id = thread["id"]
                    if thread_id not in seen_thread_ids:
                        seen_thread_ids.add(thread_id)
                        unique_threads.append(thread)

                semaphore = Semaphore(ONBOARDING_SYNC_THREAD_CONCURRENCY)

                async def process_thread(external_thread_id: str):
                    async with semaphore:
                        # Per-task client so concurrent fetches don't share a googleapiclient
                        # Resource (not thread-safe). Each task gets its own credentials, Http,
                        # and Resource.
                        task_google = await get_google_api_client(gmail_account.user, gmail_account)
                        thread_data = await task_google.fetch_thread_data(external_thread_id)
                        if not thread_data:
                            return None
                        return await processor.process_thread_messages(
                            gmail_account, external_thread_id, thread_data.get("messages", [])
                        )

                results = await gather(
                    *[process_thread(thread["id"]) for thread in unique_threads],
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, Exception):
                        logger.exception("Failed to process Gmail thread during backfill", exc_info=result)

                valid_results = [r for r in results if isinstance(r, OnboardingSyncResult)]
                page_new_count = sum(r.messages_created for r in valid_results)
                total_messages_created = self.messages_created + page_new_count
                next_page_token = (threads_response or {}).get("nextPageToken")

                with LoggingContext(
                    page_new_count=page_new_count,
                    total_messages_created=total_messages_created,
                    has_next_page=bool(next_page_token),
                ):
                    if total_messages_created >= self.max_messages:
                        logger.info("Gmail backfill completed - reached max messages")
                        return

                    if next_page_token:
                        await enqueue_job(
                            BackfillGmailEmailsJob(
                                user_id=self.user_id,
                                max_messages=self.max_messages,
                                page_token=next_page_token,
                                current_query_index=self.current_query_index,
                                messages_created=total_messages_created,
                                before_timestamp=before_timestamp,
                                unique=True,
                            )
                        )
                    else:
                        await self._enqueue_next_query(total_messages_created)

    async def _enqueue_next_query(self, messages_created: int):
        if messages_created >= self.max_messages:
            logger.info("Gmail backfill completed - reached max messages (%d created)", messages_created)
            return

        next_query_index = self.current_query_index + 1
        if next_query_index < len(BACKFILL_QUERIES):
            await enqueue_job(
                BackfillGmailEmailsJob(
                    user_id=self.user_id,
                    max_messages=self.max_messages,
                    page_token=None,
                    current_query_index=next_query_index,
                    messages_created=messages_created,
                    before_timestamp=None,
                    unique=True,
                )
            )
        else:
            logger.info("Gmail backfill completed - all queries processed (%d created)", messages_created)

    async def _resolve_before_timestamp(self) -> int | None:
        """Anchor the Gmail `before:` clause at the oldest message this user has synced
        in the stage's mailbox view, so each run picks up where the last left off.

        Using the oldest synced message (rather than a count-based offset) means a mid-run
        restart won't re-fetch already-synced pages. If the user has nothing synced for the
        stage yet, return None and let Gmail serve from most recent.

        The anchor is computed per-owner: we look at threads where THIS user's MailboxEntry
        matches the stage's router filter, not at raw EmailMessage.labels. This prevents
        collaborator-sent messages on shared threads from affecting the anchor.
        """
        entry_filter = _mailbox_entry_filter_for_stage(self.current_query_index)
        # Tortoise values_list(flat=True) returns list[GlobalID] at runtime but mypy sees tuple[Any, ...]
        resource_gids = cast(
            list[GlobalID],
            await MailboxEntry.filter(MailboxEntry.filters.by_owner(self.user_id))
            .filter(entry_filter)
            .filter(resource_gid__startswith=f"gid://convictional/{EmailThread.__name__}/")
            .values_list("resource_gid", flat=True),
        )

        thread_ids = [gid.record_id for gid in resource_gids if gid and gid.record_id]
        if not thread_ids:
            return None

        edge = (
            await EmailMessage.filter(user_id=self.user_id, thread_id__in=thread_ids).order_by("received_at").first()
        )
        if not edge or not edge.received_at:
            return None
        return int(edge.received_at.timestamp())
