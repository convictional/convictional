import base64
import html
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fastapi import status
from googleapiclient.errors import HttpError

from app.jobs.content import ContentIndexingJob
from app.models.accounts import User
from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.workspaces.email.thread import EmailMessage, EmailThread
from config import logger, settings
from config.enums import AuthenticationProvider, EmailLabel, EmailMessageType, Integration, JobQueue
from config.logging import LoggingContext
from infra.db import allow_soft_deleted
from infra.jobs import JobDefinition, bulk_enqueue_jobs, enqueue_job
from integrations.google.constants import (
    GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_TIMEOUT_SECONDS,
    GMAIL_TO_EMAIL_LABEL,
)
from integrations.google.email_mime_builder import EmailMimeBuilder
from integrations.google.enums import GmailLabel
from integrations.google.gmail import (
    GmailMessageExtractor,
    GmailMessageLoader,
    get_google_api_client,
)
from integrations.google.helpers import gmail_oauth_error_handling
from integrations.google.jobs.contacts import SyncGmailContactsJob
from integrations.google.jobs.gmail_onboarding_sync import (
    OnboardingMailboxSyncGmailJob,
    ProgressiveThreadMessageSyncJob,
)
from integrations.google.models import GmailAccount
from integrations.google.oauth import GOOGLE_GMAIL_SCOPES
from integrations.google.types import GmailHistory, gmail_headers_to_email_headers

#
# Gmail account setup jobs
#
#


class SetupGmailAccountJob(JobDefinition):
    default_queue = JobQueue.UI
    user_id: UUID

    async def perform(self):
        user = await User.get_with_scopes(self.user_id, GOOGLE_GMAIL_SCOPES, AuthenticationProvider.GOOGLE)
        if not user:
            return

        email_address = None
        async with gmail_oauth_error_handling(user):
            google = await get_google_api_client(user, None)
            profile = await google.fetch_profile()
            if not profile:
                logger.warning(f"Could not fetch Gmail profile for user {user.id}")
                await user.remove_integration(Integration.GMAIL)
                await user.mark_onboarding_mailbox_sync_complete()
                return
            email_address = profile.get("emailAddress")

        if not email_address:
            logger.warning(f"Could not get email address for user {user.id}")
            return

        gmail_account, is_new = await GmailAccount.get_or_create(
            user=user,
            email=email_address,
            defaults={"history_id": "0", "last_sync_at": None, "watch_expires_at": None},
        )

        # Clear any previous error state since Gmail setup succeeded
        if gmail_account.last_auth_errored_at:
            gmail_account.clear_auth_error()
            await gmail_account.save(update_fields=gmail_account.changes.keys())

        if is_new:
            await enqueue_job(OnboardingMailboxSyncGmailJob(user_id=user.id, unique=True))
            await enqueue_job(SyncGmailContactsJob(user_id=user.id))

            if settings.enable_gmail_watch:
                # Need to re-init the gmail client with the new gmail_account
                google = await get_google_api_client(user, gmail_account)
                await google.setup_watch()


class ReconnectGmailAccountJob(JobDefinition):
    default_queue = JobQueue.UI
    user_id: UUID

    async def perform(self):
        user = await User.get_with_scopes(self.user_id, GOOGLE_GMAIL_SCOPES, AuthenticationProvider.GOOGLE)
        if not user:
            return

        gmail_account = await GmailAccount.get_authed_for_user(self.user_id)
        if not gmail_account:
            logger.warning(f"No Gmail account found for user {self.user_id}")
            return

        email_address = None
        async with gmail_oauth_error_handling(user):
            google = await get_google_api_client(user, gmail_account)
            profile = await google.fetch_profile()
            if not profile:
                logger.warning(f"Could not fetch Gmail profile for user {user.id}")
                return
            email_address = profile.get("emailAddress")

        if not email_address:
            logger.warning(f"Could not get email address for user {user.id}")
            return

        user.email = email_address
        gmail_account.email = email_address

        if gmail_account.last_auth_errored_at:
            gmail_account.clear_auth_error()

        if user.changes:
            await user.save(update_fields=user.changes.keys())

        if gmail_account.changes:
            await gmail_account.save(update_fields=gmail_account.changes.keys())


class RenewGmailWatchesJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    is_recurring = True
    retry_count = 0

    async def perform(self):
        gmail_accounts = await GmailAccount.filter(
            GmailAccount.filters.expiring_soon() & GmailAccount.filters.has_valid_gmail_oauth()
        ).prefetch_related("user__oauth_tokens")

        for gmail_account in gmail_accounts:
            try:
                async with gmail_oauth_error_handling(gmail_account.user):
                    google = await get_google_api_client(gmail_account.user, gmail_account)
                    await google.setup_watch()
            except Exception:
                logger.exception("Failed to renew Gmail watch for account")


#
# Gmail history processing jobs
#
#


# We need to increase the timeout here because fetching attachments can take longer than the default timeout.
GMAIL_TIMEOUT_SECONDS_FETCH_MESSAGE_DATA = 300
# Maximum number of history results per page, 100 is the default value for Gmail history API.
# The maxiumum allowed is 500 based on the API docs https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.history/list
MAX_HISTORY_RESULTS = 100


@dataclass
class GmailHistoryChanges:
    entries: list[GmailHistory]
    # The mailbox's live historyId at scan time. Used ONLY to advance the caught-up marker
    # (synced_history_id) — never the resume cursor, which must not overshoot lagging records.
    response_history_id: str | None = None
    is_history_expired: bool = False


class ProcessGmailHistoryJob(JobDefinition):
    default_queue = JobQueue.EMAIL
    gmail_account_id: UUID
    history_id: str
    retry_count = 1

    async def perform(self):
        gmail_account = await GmailAccount.get_authed_by_id(self.gmail_account_id)
        if not gmail_account:
            return

        with LoggingContext(
            gmail_account_id=gmail_account.id,
            history_id=self.history_id,
            stored_history_id=gmail_account.history_id,
        ):
            if gmail_account.is_history_older_or_equal(self.history_id):
                # History can be received out of order, so we only process if the history ID has advanced.
                logger.info("Skipping history, already processed")
                return

            if not await gmail_account.acquire_history_sync_lock():
                # Check if the history_id has been updated by another job
                await gmail_account.refresh_from_db()
                if gmail_account.is_history_older_or_equal(self.history_id):
                    logger.info("Skipping history, already processed")
                    return
                else:
                    logger.warning(
                        f"Lock contention: could not acquire history sync lock, "
                        f"locked at {gmail_account.history_sync_locked_at}"
                    )
                    # The history_id is still behind, so we should retry this job
                    # We don't know when the lock will be released, so we re-enqueue the job after a timeout
                    perform_at = datetime.now(UTC) + timedelta(
                        seconds=GMAIL_ACCOUNT_HISTORY_SYNC_LOCK_DEFAULT_TIMEOUT_SECONDS
                    )
                    await enqueue_job(
                        ProcessGmailHistoryJob(
                            gmail_account_id=self.gmail_account_id,
                            history_id=self.history_id,
                            perform_at=perform_at,
                            unique=True,
                        )
                    )
                    logger.info(f"Re-enqueued history job to run at {perform_at}")
                    return

            try:
                logger.info(f"Acquired history sync lock at {gmail_account.history_sync_locked_at}")
                # Re-check history_id after acquiring lock (paranoia check)
                refreshed_account = await GmailAccount.get(id=gmail_account.id)
                if refreshed_account.is_history_older_or_equal(self.history_id):
                    return

                history_changes = await self._get_history_changes(gmail_account)
                await self._process_changes_in_order(gmail_account, history_changes.entries)

                # Resume cursor: advance only to the max processed record id, never the response historyId.
                # Gmail history is eventually consistent, so the response historyId can exceed the records
                # actually returned; overshooting the cursor wholesale-skips lagging records' webhooks.
                # The monotonic-advance guard (is_history_newer) and persist step (mark_synced) are shared
                # with OnboardingMailboxSyncGmailJob; the expired-history fallback and synced_history_id
                # caught-up marker below are specific to incremental history processing.
                max_processed_history_id = max(
                    (int(h.get("id") or "0") for h in history_changes.entries), default=None
                )
                if max_processed_history_id is not None and gmail_account.is_history_newer(
                    str(max_processed_history_id)
                ):
                    cursor_history_id = str(max_processed_history_id)
                elif history_changes.is_history_expired:
                    cursor_history_id = self.history_id
                else:
                    cursor_history_id = gmail_account.history_id

                # Caught-up marker: the live historyId we've now fully scanned through, advanced even when
                # the scan returned no records. The health check compares against this, so the normal gap
                # between the live historyId and the trailing cursor no longer re-triggers a no-op sync.
                await gmail_account.mark_synced(
                    cursor_history_id,
                    synced_history_id=history_changes.response_history_id or cursor_history_id,
                )

            finally:
                # Always release the lock when done
                await gmail_account.release_history_sync_lock()
                logger.info("Released history sync lock")

    async def _process_changes_in_order(
        self, gmail_account: GmailAccount, history_entries: list[GmailHistory]
    ) -> None:
        for history in history_entries:
            # Note that message processors are not jobs themselves because we need to ensure history entries are
            # processed in order since they can affect each other (e.g. a messageAdded followed by a labelsAdded),
            # running them as jobs would not guarantee order and leads to incorrect state.
            for deleted_data in history.get("messagesDeleted", []):
                logger.info(
                    f"GmailHistory message deleted for account {gmail_account.id}, "
                    f"message ID: {deleted_data['message']['id']}"
                )
                deleted_processor = GmailMessageDeletedProcessor(
                    gmail_account_id=gmail_account.id, external_message_id=deleted_data["message"]["id"]
                )
                await deleted_processor.perform()

            for message_data in history.get("messagesAdded", []):
                logger.info(
                    f"GmailHistory message added for account {gmail_account.id}, "
                    f"message ID: {message_data['message']['id']}"
                )
                added_processor = GmailMessageAddedProcessor(
                    gmail_account_id=gmail_account.id, external_message_id=message_data["message"]["id"]
                )
                await added_processor.perform()

            for label_data in history.get("labelsAdded", []):
                logger.info(
                    f"GmailHistory labels added for account {gmail_account.id}, "
                    f"message ID: {label_data['message']['id']}"
                )
                state_processor = GmailMessageStateProcessor(
                    gmail_account_id=gmail_account.id, external_message_id=label_data["message"]["id"]
                )
                await state_processor.perform()

            for label_data in history.get("labelsRemoved", []):
                logger.info(
                    f"GmailHistory labels removed for account {gmail_account.id}, "
                    f"message ID: {label_data['message']['id']}"
                )
                state_processor = GmailMessageStateProcessor(
                    gmail_account_id=gmail_account.id, external_message_id=label_data["message"]["id"]
                )
                await state_processor.perform()

    async def _get_history_changes(self, gmail_account: GmailAccount) -> GmailHistoryChanges:
        history_results: list[GmailHistory] = []
        response_history_id: str | None = None
        try:
            async with gmail_oauth_error_handling(gmail_account.user):
                google = await get_google_api_client(gmail_account.user, gmail_account)

                page_token: Any = None
                while True:
                    result = await google.list_history(
                        max_results=MAX_HISTORY_RESULTS,
                        start_history_id=int(gmail_account.history_id) if gmail_account.history_id else None,
                        history_types=["messageAdded", "labelAdded", "labelRemoved", "messageDeleted"],
                        page_token=page_token,
                    )
                    if result:
                        history_results.extend(result.get("history", []))
                        response_history_id = result.get("historyId") or response_history_id
                        if "nextPageToken" not in result:
                            break
                        page_token = result["nextPageToken"]
                    else:
                        break
            # Sort history results by the historyId to ensure they are processed in order
            history_results.sort(key=lambda x: int(x.get("id") or "0"))
            return GmailHistoryChanges(entries=history_results, response_history_id=response_history_id)
        except HttpError as error:
            if error.status_code == status.HTTP_404_NOT_FOUND:
                logger.warning(f"History ID expired for account {gmail_account.id}, skipping sync")
                return GmailHistoryChanges(entries=[], is_history_expired=True)
            else:
                raise


@dataclass
class GmailMessageAddedProcessor:
    gmail_account_id: UUID
    external_message_id: str

    async def perform(self):
        gmail_account = await GmailAccount.get_authed_by_id(self.gmail_account_id)
        if not gmail_account:
            return

        google = await get_google_api_client(
            gmail_account.user, gmail_account, request_timeout_seconds=GMAIL_TIMEOUT_SECONDS_FETCH_MESSAGE_DATA
        )
        message_data = await google.fetch_message(self.external_message_id)
        if not message_data:
            logger.warning(f"Message {self.external_message_id} not found in Gmail account {gmail_account.id}")
            return

        # Skip draft messages
        gmail_labels = message_data.get("labelIds", [])
        if GmailLabel.DRAFT in gmail_labels:
            return

        extractor = GmailMessageExtractor()
        loader = GmailMessageLoader(gmail_account)
        payload = message_data.get("payload")
        headers_list = payload.get("headers", []) if payload else []
        headers = gmail_headers_to_email_headers(headers_list)

        existing_email = await EmailMessage.get_or_none(
            EmailMessage.filters.by_external_message_id(
                external_message_id=self.external_message_id, user_id=gmail_account.user.id
            )
            | EmailMessage.filters.by_message_id(message_id=headers.message_id or "", user_id=gmail_account.user.id)
        )
        if existing_email:
            return

        if payload:
            body_plain, body_html = extractor.extract_email_body(payload)
            attachments_data = extractor.find_attachments(payload)
        else:
            body_plain, body_html = None, None
            attachments_data = []

        new_message_result = await loader.create_email_record(message_data, headers, body_plain, body_html)
        await loader.process_attachments(google, new_message_result.email, attachments_data)
        await Mailbox.sync(new_message_result.thread)
        await enqueue_job(
            ContentIndexingJob.from_model(new_message_result.thread.organization_id, new_message_result.thread)
        )

        if new_message_result.was_new_thread and new_message_result.email.is_reply:
            await enqueue_job(
                ProgressiveThreadMessageSyncJob(user_id=gmail_account.user.id, thread_id=new_message_result.thread.id)
            )


@dataclass
class GmailMessageStateProcessor:
    gmail_account_id: UUID
    external_message_id: str

    async def perform(self):
        gmail_account = await GmailAccount.get_authed_by_id(self.gmail_account_id)
        if not gmail_account:
            return

        # Find the existing email message. Scope by user_id because Gmail's per-mailbox
        # message IDs aren't globally unique — EmailMessage.unique_together is
        # (external_message_id, user_id), so an unscoped lookup can match another user's row.
        email_message = cast(
            EmailMessage | None,
            await EmailMessage.unscoped.get_queryset()
            .filter(
                EmailMessage.filters.by_external_message_id(
                    external_message_id=self.external_message_id, user_id=gmail_account.user.id
                )
            )
            .get_or_none(),
        )
        if not email_message:
            return

        # Thread may have been soft-deleted by trashing messages in earlier history entries
        async with allow_soft_deleted():
            await email_message.fetch_related("thread")

        # Get current message data from Gmail to get the full label list
        google = await get_google_api_client(gmail_account.user, gmail_account)

        try:
            message_data = await google.fetch_message(self.external_message_id, format="minimal")
            if not message_data:
                logger.warning(f"Gmail message {self.external_message_id} not found for state update")
                return
            gmail_labels = message_data.get("labelIds", [])
        except HttpError as error:
            if error.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND):
                logger.warning(f"Failed to fetch Gmail message {self.external_message_id}: {error}")
                return
            else:
                raise

        # Convert Gmail labels to our email labels, filtering out TRASH
        filtered_labels = [
            GMAIL_TO_EMAIL_LABEL[GmailLabel(gmail_label)]
            for gmail_label in gmail_labels
            if gmail_label in [label.value for label in GmailLabel] and gmail_label != GmailLabel.TRASH.value
        ]

        # Gmail can return stale DRAFT labels for messages our system has already transitioned
        # to SENDING or SENT — strip DRAFT from Gmail's response to prevent it from undoing
        # the send job's correct label state on the MailboxEntry.
        if email_message.message_type in (EmailMessageType.SENDING, EmailMessageType.SENT):
            filtered_labels = [label for label in filtered_labels if label != EmailLabel.DRAFT]

        # Capture the thread's inbox membership before this message's label change. A thread
        # is in the inbox when any of its messages carries INBOX, so the archive below keys off
        # the thread leaving the inbox — not this single message — to avoid over-archiving a
        # multi-message thread when one message loses INBOX while a sibling still has it.
        thread_was_inbox = email_message.thread.is_inbox

        # Update the email message labels
        email_message.labels = filtered_labels

        # Handle soft delete for TRASH label
        if GmailLabel.TRASH in gmail_labels and not email_message.is_deleted:
            logger.info(f"Marking email message {email_message.id} as deleted (TRASH label added)")
            email_message.deleted_at = datetime.now(UTC)
        elif GmailLabel.TRASH not in gmail_labels and email_message.is_deleted:
            logger.info(f"Restoring email message {email_message.id} (TRASH label removed)")
            email_message.deleted_at = None

        if email_message.changes:
            await email_message.save(update_fields=email_message.changes.keys())
            await email_message.thread.update_metadata_from_messages()
            await Mailbox.sync(email_message.thread)

            # Authoritative Gmail-archive signal: the thread transitioned out of the inbox
            # (every message lost INBOX). A trash (TRASH added, INBOX dropped) is handled by the
            # soft-delete path above, not here — archiving it would, once the entry is soft-deleted,
            # raise on the archive lookup. Lives here rather than in _sync_inbox_state to avoid the
            # outgoing-only false-archive regression (an all-outgoing thread is never is_inbox, so
            # this transition never fires for it).
            thread = email_message.thread
            trashed = GmailLabel.TRASH in gmail_labels
            if thread_was_inbox and not thread.is_inbox and not trashed and not thread.is_deleted:
                await Mailbox(gmail_account.user).archive(thread)


@dataclass
class GmailMessageDeletedProcessor:
    gmail_account_id: UUID
    external_message_id: str

    async def perform(self):
        gmail_account = await GmailAccount.get_authed_by_id(self.gmail_account_id)
        if not gmail_account:
            return

        email_message = await EmailMessage.get_or_none(
            user_id=gmail_account.user_id, external_message_id=self.external_message_id
        ).prefetch_related("thread")
        if not email_message:
            return

        if not email_message.is_deleted:
            await email_message.thread.remove_message(email_message)

        await Mailbox.sync(email_message.thread)


#
# Gmail write operations
#
#


class UpdateGmailThreadLabelsJob(JobDefinition):
    default_queue = JobQueue.UI
    user_id: UUID
    external_thread_id: str
    labels_to_add: list[str] | None = None
    labels_to_remove: list[str] | None = None

    async def perform(self):
        gmail_account = await GmailAccount.get_authed_for_user(self.user_id)
        if not gmail_account:
            return

        thread = await EmailThread.get_or_none(
            creator_id=gmail_account.user_id, external_thread_id=self.external_thread_id
        )
        if not thread:
            logger.warning(f"Email thread {self.external_thread_id} not found")
            return

        google = await get_google_api_client(gmail_account.user, gmail_account)

        payload: dict[str, Any] = {}
        if self.labels_to_add:
            payload["addLabelIds"] = self.labels_to_add
        if self.labels_to_remove:
            payload["removeLabelIds"] = self.labels_to_remove

        if payload:
            await google.modify_thread(self.external_thread_id, payload)


class SendEmailThroughGmailJob(JobDefinition):
    default_queue = JobQueue.UI
    email_thread_id: UUID
    sender_user_id: UUID | None = None

    async def perform(self):
        thread = await EmailThread.get_or_none(id=self.email_thread_id).prefetch_related("messages", "workspace")
        if not thread:
            logger.warning(f"Email thread {self.email_thread_id} not found")
            return

        email_draft = await thread.get_draft(EmailMessageType.SENDING)
        if not email_draft:
            logger.warning(f"Email draft not found for thread {self.email_thread_id}")
            await thread.update_metadata_from_messages()
            await Mailbox.sync(thread)
            return

        # Use sender_user_id if provided (assignee sending), otherwise fall back to draft creator
        sending_user_id = self.sender_user_id or email_draft.user_id
        sender = await User.get_or_none(id=sending_user_id, organization_id=thread.organization_id)
        if not sender or not thread.can_reply(sender):
            logger.warning(f"User {sending_user_id} not authorized to send on thread {self.email_thread_id}")
            return

        gmail_account = await GmailAccount.get_authed_for_user(sending_user_id)
        if not gmail_account:
            return

        google = await get_google_api_client(gmail_account.user, gmail_account)

        # Build the MIME message for sending
        # BCC can be included when using messages.send because gmail will handle splitting it out
        # into individual envelopes for each bcc recipient
        raw_message = await EmailMimeBuilder.build_mime_string_from_draft(email_draft, include_bcc=True)
        message_body = {"raw": base64.urlsafe_b64encode(raw_message.encode("utf-8")).decode("utf-8")}

        # Resolve the threadId in the *sender's* mailbox. Local `external_thread_id`
        # values can refer to a different user's mailbox (e.g. when a compose-and-send
        # via assignee leaves a SENT message whose threadId came from the assignee's
        # Gmail), so we ask Gmail directly via the parent's RFC 2822 Message-Id.
        # Falls back to omitting threadId so Gmail starts a fresh thread on this
        # sender's side rather than 404-ing on a foreign threadId.
        parent = email_draft.message.in_reply_to
        if parent and parent.message_id:
            external_thread_id = await google.find_thread_id_for_rfc822_message_id(parent.message_id)
            if external_thread_id:
                message_body["threadId"] = external_thread_id

        sent_message = await google.send_message(message_body)

        if not sent_message or not sent_message.get("id") or not sent_message.get("threadId"):
            raise ValueError("Failed to get sent message ID from Gmail API response")

        # Fetch complete message data to get all required fields (symmetric with receiving)
        message_data = await google.fetch_message(sent_message["id"])
        if not message_data:
            raise ValueError("Failed to fetch sent message data from Gmail API")

        payload = message_data.get("payload")
        headers_list = payload.get("headers", []) if payload else []
        headers = gmail_headers_to_email_headers(headers_list)

        await thread.mark_draft_sent(
            email_draft,
            sender=gmail_account.user,
            external_message_id=str(message_data.get("id")),
            external_thread_id=str(message_data.get("threadId")),
            external_history_id=str(message_data.get("historyId")),
            message_id=str(headers.message_id or ""),
            headers=headers,
            preview=html.unescape(message_data.get("snippet", "")),
            raw_data=cast(dict[str, Any], message_data),
        )
        await thread.update_metadata_from_messages()
        await Mailbox.sync(thread)


#
# Health checks
#
#


class GmailHealthCheckJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    user_id: UUID

    async def perform(self):
        gmail_account = await GmailAccount.get_authed_for_user(self.user_id)
        if not gmail_account:
            return

        current_history_id = None
        async with gmail_oauth_error_handling(gmail_account.user):
            google = await get_google_api_client(gmail_account.user, gmail_account)
            # Get the most recent history ID
            profile = await google.fetch_profile()
            if not profile:
                logger.warning(f"Could not fetch Gmail profile for user {self.user_id}")
                return
            current_history_id = profile.get("historyId", "0")

        if not current_history_id:
            logger.warning("Could not get history ID for user")
            return
        if gmail_account.is_health_check_behind(current_history_id):
            # Behind the caught-up marker means real records likely went unprocessed (e.g. a dropped
            # webhook), so re-sync to recover them. This is info, not a warning: the comparison is
            # against synced_history_id, which advances even on empty scans, so it fires only on a
            # genuine gap rather than on the normal lag between the live historyId and the resume cursor.
            logger.info(
                f"Gmail history ID behind for user {self.user_id}: "
                f"synced {gmail_account.synced_history_id}, cursor {gmail_account.history_id}, "
                f"current {current_history_id}"
            )
            # Trigger a sync if history ID is out of sync
            # This could lead to duplicate syncs if pubsub is just backed up, but it's better than missing messages.
            await enqueue_job(
                ProcessGmailHistoryJob(gmail_account_id=gmail_account.id, history_id=current_history_id, unique=True)
            )
            # Undelivered mail with no recent push means the watch has silently stopped delivering
            # (it can lapse before watch_expires_at, so RenewGmailWatchesJob won't otherwise retouch it).
            # Mark it expired so the renewal job re-establishes it and real-time delivery resumes.
            if gmail_account.is_push_stale():
                logger.info(
                    f"Gmail watch appears dead for user {self.user_id} "
                    f"(last push {gmail_account.last_push_received_at}); marking for renewal"
                )
                await gmail_account.mark_watch_expired()
        elif gmail_account.is_history_older(current_history_id):
            logger.error(
                f"Gmail history ID {current_history_id} is less than stored history ID {gmail_account.history_id} "
                f"for user {self.user_id}. This should never happen and may indicate a sync issue."
            )
        # Do nothing if the history ID matches, this is the ideal state.


class EnqueueGmailHealthCheckJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        gmail_accounts = await GmailAccount.filter(
            GmailAccount.filters.onboarding_mailbox_sync_completed & GmailAccount.filters.has_valid_gmail_oauth()
        ).prefetch_related("user__oauth_tokens")

        await bulk_enqueue_jobs(
            [GmailHealthCheckJob(user_id=account.user_id, unique=True) for account in gmail_accounts],
        )


#
# Snoozing
#
#


class RestoreGmailInboxLabelJob(JobDefinition):
    """Restores a woken email thread to the original recipient's Gmail inbox. Enqueued
    alongside UnsnoozeMailboxEntryJob by CheckSnoozedMailboxEntriesJob for EmailThread
    entries; the generic unsnooze handles our own inbox state."""

    default_queue = JobQueue.MISCELLANEOUS
    mailbox_entry_id: UUID

    async def perform(self):
        mailbox_entry = await MailboxEntry.get_or_none(id=self.mailbox_entry_id)
        if not mailbox_entry:
            return

        resource = await mailbox_entry.resource_gid.get_or_none()
        if not isinstance(resource, EmailThread) or not resource.is_original_recipient(mailbox_entry.owner_id):
            return
        if not resource.external_thread_id:
            return

        gmail_account = await GmailAccount.get_authed_for_user(mailbox_entry.owner_id)
        if not gmail_account:
            return

        google = await get_google_api_client(gmail_account.user, gmail_account)
        logger.info(f"Restoring Gmail inbox label for thread {resource.id}")
        await google.modify_thread(resource.external_thread_id, {"addLabelIds": [GmailLabel.INBOX]})
