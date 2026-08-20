from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar, Self

from tortoise import BaseDBAsyncClient
from tortoise.expressions import Q

from app.models.accounts import User
from app.models.collaboration.mailbox import (
    CONTENT_REVISION_ACTIONS,
    BaseMailboxEntry,
    BaseMailboxEntryFilters,
    Mailbox,
    MailboxEntry,
)
from app.models.collaboration.workspace import Event
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailThread
from config.enums import EmailMailboxLabel, EmailMessageType, EventAction
from infra.db import RecordModel, transaction


class EmailMailboxEntryFilters(BaseMailboxEntryFilters):
    @classmethod
    def inbox(cls) -> Q:
        return super().inbox() & ~Q(labels__contains=[EmailMailboxLabel.SPAM])

    @classmethod
    def archived(cls) -> Q:
        return (
            super().archived()
            & ~Q(labels__contains=[EmailMailboxLabel.SPAM])
            & ~Q(labels__contains=[EmailMailboxLabel.DRAFT])
        )

    @classmethod
    def sent(cls) -> Q:
        return cls._type_scope() & Q(labels__contains=[EmailMailboxLabel.SENT])

    @classmethod
    def draft(cls) -> Q:
        return cls._type_scope() & Q(labels__contains=[EmailMailboxLabel.DRAFT]) & Q(is_shared=False)


@dataclass
class EmailMailboxEntry(BaseMailboxEntry):
    resource_model: ClassVar[type] = EmailThread
    entry_filters: ClassVar[type[BaseMailboxEntryFilters]] = EmailMailboxEntryFilters
    email_thread: EmailThread

    prefetch_for_sync: ClassVar[tuple[str, ...]] = (
        "workspace__collaborators__user",
        "comments",
        "workspace__events",
        "workspace__attachments",
        "messages__attachments",
    )

    @classmethod
    def from_resource(cls, resource: RecordModel) -> Self:
        assert isinstance(resource, EmailThread)
        return cls(email_thread=resource)

    @property
    def resource(self) -> EmailThread:
        return self.email_thread

    async def touch(self, user: User, *, using_db: BaseDBAsyncClient | None = None) -> None:
        await self.email_thread.fetch_related(*self.prefetch_for_sync, using_db=using_db)

        if sync := await self.refresh_row_and_mark_unread(user, using_db=using_db):
            await sync.broadcast()

    async def mark_as_read(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.mark_as_read(using_db=connection)

            if self.email_thread.is_original_recipient(user.id):
                await self.email_thread.mark_as_read(using_db=connection)

            # Use refresh_row_content, not touch: touch routes through
            # refresh_row_and_mark_unread → _sync_read_state, which can call
            # label_as_unread() when has_new_activity=True (e.g. a new message
            # arrived between the read-action and this sync), silently undoing
            # the read state we just saved. refresh_row_content refreshes
            # content fields without re-evaluating inbox/unread labels.
            await self.email_thread.fetch_related(*self.prefetch_for_sync, using_db=connection)
            if sync := await self.refresh_row_content(user, using_db=connection):
                await sync.broadcast()

    async def mark_as_unread(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.mark_as_unread(using_db=connection)

            if self.email_thread.is_original_recipient(user.id):
                await self.email_thread.mark_as_unread(using_db=connection)

            # Same rationale as mark_as_read: touch's _sync_read_state branch
            # can label_as_read() the entry when the thread is read with no
            # unread-from-others, undoing the unread state we just saved.
            await self.email_thread.fetch_related(*self.prefetch_for_sync, using_db=connection)
            if sync := await self.refresh_row_content(user, using_db=connection):
                await sync.broadcast()

    async def archive(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            if not entry.is_archived:
                entry.label_as_archived()
                for label in (EmailMailboxLabel.SPAM, EmailMailboxLabel.DRAFT):
                    if label in entry.labels:
                        entry.labels.remove(label)
                await entry.save(update_fields=["labels"], using_db=connection)

            if self.email_thread.is_original_recipient(user.id):
                await self.email_thread.archive(using_db=connection)

    async def unarchive(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.unarchive(using_db=connection)

            if self.email_thread.is_original_recipient(user.id):
                await self.email_thread.unarchive(using_db=connection)

    def _refresh_content_and_mark_unread(self, entry: MailboxEntry) -> None:
        # Email attention isn't a simple unread flag: inbox/read state is derived from Gmail
        # thread labels, so this overrides the GATED surface. (The base _refresh_content —
        # content only — is reused as-is for mark_as_read/unread, which must not re-evaluate
        # the labels they just set.) The FORCED surface is NOT overridden: an explicit
        # @mention/decision surfaces the row past Gmail gating via the generic base method.
        has_new_activity = self._refresh_content(entry)
        self._sync_inbox_state(entry, has_new_activity)
        self._sync_read_state(entry, has_new_activity)
        if has_new_activity and entry.is_snoozed:
            entry.snoozed_until = None

    def _refresh_content(self, entry: MailboxEntry) -> bool:
        self._sync_basic_metadata(entry)
        self._sync_comment_info(entry)
        self._sync_preview_kind(entry)
        self._sync_deletion(entry)

        last_activity_at, has_new_activity = self._sync_activity_tracking(entry)
        entry.last_activity_at = last_activity_at

        self._sync_email_labels(entry)
        self._sync_counts(entry)
        return has_new_activity

    def _sync_basic_metadata(self, entry: MailboxEntry) -> None:
        entry.title = self.email_thread.title
        entry.preview = self.email_thread.preview
        entry.is_shared = self.email_thread.creator_id != entry.owner_id
        entry.assignee_id = self.email_thread.workspace.assignee_id

    def _sync_comment_info(self, entry: MailboxEntry) -> None:
        most_recent = self.email_thread.most_recent_comment
        if most_recent:
            entry.last_comment = most_recent.content
            entry.last_comment_author_id = most_recent.user_id
        else:
            # No live comment (e.g. the last one was deleted) — clear the preview so a deleted
            # comment's text doesn't linger in the mailbox row.
            entry.last_comment = None
            entry.last_comment_author_id = None

    def _sync_preview_kind(self, entry: MailboxEntry) -> None:
        # Email is the one asymmetric preview: its messages are ingested, not recorded as
        # workspace events (thread.py), so the line can't just be "newest event wins". It's a
        # three-way race between the last message, the last comment, and the last activity event:
        #
        #   activity  — a collaborator add / assignment / decision newer than BOTH the last
        #               message and the last comment; pin last_event for the client to phrase.
        #   comment   — a comment newer than the last message; rides last_comment as a chip.
        #   message   — otherwise the message snippet (entry.preview, set in _sync_basic_metadata).
        #
        # The comment-vs-message decision stays exactly is_most_recent_activity_comment, so a
        # message or comment being newest renders byte-for-byte as before — activity only adds a
        # new branch on top, it never changes the existing two.
        entry.last_event_id = None
        entry.is_preview_comment = False

        latest_activity = self._latest_activity_event()
        if latest_activity and self._activity_is_newest(latest_activity):
            entry.last_event_id = latest_activity.id
            return

        entry.is_preview_comment = self.email_thread.is_most_recent_activity_comment

    @property
    def _activity_events(self) -> list[Event]:
        # Every workspace event except silent content revisions (comment edits/deletes). The single
        # predicate behind both the activity cursor (_sync_activity_tracking) and the preview line
        # (_latest_activity_event); see _sync_activity_tracking for why revisions are excluded.
        return [event for event in self.email_thread.workspace.events if event.action not in CONTENT_REVISION_ACTIONS]

    def _latest_activity_event(self) -> Event | None:
        # The newest event that phrases as an activity line. COMMENTED is the one activity event that
        # doesn't render as one — it rides the comment path via most_recent_comment — so it's the
        # single delta from _activity_events; collaborator add/remove, assignment, sharing, and
        # decision remain.
        candidates = [event for event in self._activity_events if event.action != EventAction.COMMENTED]
        return max(candidates, key=lambda event: event.created_at, default=None)

    def _activity_is_newest(self, event: Event) -> bool:
        # Activity wins the line only when strictly newer than both the last message and the last
        # live comment — so a message or comment being the newest thing keeps its existing preview.
        last_message_at = self.email_thread.last_message_at
        if last_message_at is not None and event.created_at <= last_message_at:
            return False
        comment = self.email_thread.most_recent_comment
        if comment is not None and event.created_at <= comment.created_at:
            return False
        return True

    def _sync_deletion(self, entry: MailboxEntry) -> None:
        if self.email_thread.is_deleted and not entry.is_deleted:
            entry.deleted_at = datetime.now(UTC)
        elif not self.email_thread.is_deleted and entry.is_deleted:
            entry.deleted_at = None

    def _sync_activity_tracking(self, entry: MailboxEntry) -> tuple[datetime, bool]:
        old_last_activity_at = entry.last_activity_at if not entry.is_new else None
        last_activity_at = self.email_thread.last_message_at or self.email_thread.created_at

        # Comment edits/deletes are recorded as events so the engine can sync them, but they
        # are not thread activity: excluding them keeps a typo-fix edit from advancing the
        # activity cursor, which would otherwise float the thread to the top of every inbox and
        # re-surface a caught-up reader as unread on a later recompute (e.g. inbound mail).
        activity_events = self._activity_events
        last_event_at = max((event.created_at for event in activity_events), default=None)
        if last_event_at and last_event_at > last_activity_at:
            last_activity_at = last_event_at

        owner_email = entry.owner.email.lower()
        last_message_from_others_at = max(
            (
                message.resolved_received_at
                for message in self.email_thread.messages
                if not message.is_from(owner_email)
            ),
            default=None,
        )

        last_activity_from_others_at = None
        last_event_from_others = max(
            (event for event in activity_events if event.creator_id != entry.owner_id),
            key=lambda event: event.created_at,
            default=None,
        )
        last_event_from_others_at = last_event_from_others.created_at if last_event_from_others else None
        for timestamp in [last_message_from_others_at, last_event_from_others_at]:
            if timestamp and (not last_activity_from_others_at or timestamp > last_activity_from_others_at):
                last_activity_from_others_at = timestamp

        if entry.is_new:
            has_new_activity_from_others = False
        else:
            has_new_activity_from_others = (
                last_activity_from_others_at is not None
                and old_last_activity_at is not None
                and last_activity_from_others_at > old_last_activity_at
            )

        has_new_activity = has_new_activity_from_others or not entry.is_new and "deleted_at" in entry.changes

        return last_activity_at, has_new_activity

    def _sync_inbox_state(self, entry: MailboxEntry, has_new_activity: bool) -> None:
        # Sync only ADDS the INBOX label based on activity. Removing it is the
        # responsibility of explicit user actions (entry.archive(), entry.snooze()).
        #
        # We must NOT add INBOX when Gmail has archived the inbound mail — an archived
        # thread must never reappear in the Convictional inbox. But we cannot simply gate on
        # `thread.is_inbox`/`thread.is_archived`: those are derived from label-union math
        # over messages, so a thread composed entirely of OUTGOING messages (e.g. assignee
        # sent + creator replied, no inbound) reads as archived even though no one archived
        # it — those threads should stay in the inbox. (A prior branch that mirrored the
        # thread's archived state onto the entry stripped INBOX from exactly these.)
        #
        # The distinguishing signal is `_received_mail_is_archived`: it suppresses the
        # add ONLY when the thread actually has inbound (RECEIVED) messages and Gmail has
        # taken all of them out of the inbox. All-outgoing threads have no inbound mail, so
        # they're never suppressed; and a genuinely new inbound message that DOES carry
        # INBOX re-opens the thread normally.
        if self._received_mail_is_archived():
            return

        if entry.is_shared:
            if entry.is_new or has_new_activity:
                entry.label_as_inbox()
        else:
            if (entry.is_new and self.email_thread.is_inbox) or has_new_activity:
                entry.label_as_inbox()

    def _received_mail_is_archived(self) -> bool:
        # True when the thread has inbound (RECEIVED) mail and none of it is in the Gmail
        # inbox — i.e. Gmail archived the conversation. Returns False for all-outgoing
        # threads (no RECEIVED messages), which is what keeps them in the Convictional inbox.
        received_messages = [
            message for message in self.email_thread.messages if message.message_type == EmailMessageType.RECEIVED
        ]
        if not received_messages:
            return False
        return not any(message.is_inbox for message in received_messages)

    def _sync_read_state(self, entry: MailboxEntry, has_new_activity: bool) -> None:
        if entry.is_shared:
            if entry.is_new or has_new_activity:
                entry.label_as_unread()
        else:
            if has_new_activity:
                entry.label_as_unread()
            else:
                # If thread labels are stale but unread messages from others exist
                # (e.g. double-sync via GmailMessageStateProcessor), preserve the
                # unread state rather than overriding it.
                if self.email_thread.is_read:
                    if not self.email_thread.has_unread_from_others(entry.owner.email):
                        entry.label_as_read()
                else:
                    entry.label_as_unread()

    def _sync_email_labels(self, entry: MailboxEntry) -> None:
        # Sync sent: the actual sender sees the thread in their sent folder.
        # If we can determine the sender from the message, only that user gets SENT.
        # Otherwise (no parseable sender), fall back to owner for backward compatibility.
        if self.email_thread.is_sent:
            sender_email = self._get_sent_message_sender_email()
            if sender_email and sender_email == entry.owner.email.lower():
                if EmailMailboxLabel.SENT not in entry.labels:
                    entry.labels.append(EmailMailboxLabel.SENT)
            elif not sender_email and entry.is_owner:
                if EmailMailboxLabel.SENT not in entry.labels:
                    entry.labels.append(EmailMailboxLabel.SENT)

        if entry.is_owner:
            if self.email_thread.is_draft:
                if EmailMailboxLabel.DRAFT not in entry.labels:
                    entry.labels.append(EmailMailboxLabel.DRAFT)
            else:
                if EmailMailboxLabel.DRAFT in entry.labels:
                    entry.labels.remove(EmailMailboxLabel.DRAFT)

        if entry.is_owner and self.email_thread.is_spam:
            if EmailMailboxLabel.SPAM not in entry.labels:
                entry.labels.append(EmailMailboxLabel.SPAM)

    def _get_sent_message_sender_email(self) -> str | None:
        """Extract the sender email from a message that was sent through the app.

        Only checks messages with message_type=SENT (set by mark_as_sent), not messages
        with just the SENT label (which may be synced from Gmail with the original sender).
        Returns None if no such message exists, which triggers the is_owner fallback.
        """
        for msg in reversed(self.email_thread.messages):
            if msg.message_type == EmailMessageType.SENT and msg.sender:
                parsed = EmailAddress.parse_safe(msg.sender)
                if parsed:
                    return parsed.email.lower()
        return None

    def _sync_counts(self, entry: MailboxEntry) -> None:
        entry.workspace_attachment_count = len(self.email_thread.workspace.attachments)


async def _sync_mailbox(email_thread: EmailThread) -> None:
    await Mailbox.sync(email_thread)


# on_publish covers inbound Gmail messages and other publish() callers that have no
# workspace Event. Comment create/edit/delete each record an Event through Notifier
# (api_email_thread_comments_*), so SyncMailboxJob is their sole sync path and no comment
# hook is registered: a second no-event resync would re-read the edit/delete event as new
# activity and re-alert every collaborator, which the routing layer (InboxUpdate.for_event)
# exists to prevent.
EmailThread.on_publish(_sync_mailbox)
