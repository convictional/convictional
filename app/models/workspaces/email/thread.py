import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Annotated, Any, ClassVar, Self, cast
from urllib.parse import urljoin
from uuid import UUID

from pycrdt import Text
from tortoise import BaseDBAsyncClient, fields
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.signals import post_delete, pre_save

from app.models.accounts import Organization, User
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import Mailbox
from app.models.collaboration.workspace import (
    CollaborationPolicy,
    CommentMixin,
    NotificationPolicy,
    WorkspaceMixin,
    WorkspaceMixinFilters,
    delete_decision_for_comment,
)
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.labels import EmailLabelFilters, EmailLabelsMixin
from config import logger, settings
from config.enums import EmailDelivery, EmailDraftAction, EmailLabel, EmailMessageType, EmailReplyType, EventAction
from config.logging import LoggingContext
from infra.db import JSONField, PartialIndex, RecordModel, SoftDeleteableMixin, after_commit, transaction
from infra.email import EmailAttachment as EmailAttachmentPayload
from infra.email import EmailClient, EmailHeaders
from infra.email import EmailMessage as EmailPayload
from infra.messaging import Topic
from infra.storage import FileReference, TrustedStr, store_file_from_string

EMAIL_REPLY_PREFIXES = [r"^re:\s*", r"^re\[\d+\]:\s*"]
EMAIL_FORWARD_PREFIXES = [r"^fwd?:\s*", r"^fw:\s*"]
EMAIL_REPLY_AND_FORWARD_PREFIXES = EMAIL_REPLY_PREFIXES + EMAIL_FORWARD_PREFIXES

# A scheduled send defers via a Cloud Task, which rejects a schedule more than 30 days out.
SCHEDULED_SEND_MAX_HORIZON = timedelta(days=30)


@dataclass
class NewMessageResult:
    thread: "EmailThread"
    email: "EmailMessage"
    was_new_thread: bool = False


@dataclass
class SendSideEffectOptions:
    should_archive: bool = False
    should_snooze: bool = False
    snoozed_until: datetime | None = None
    # Whether a send that neither archives nor snoozes should force the sender's entry back into
    # the inbox. True for an immediate send (the sender is live on the thread, keep them engaged);
    # False for a deferred/scheduled fire, so an archive made between scheduling and the fire stands.
    pin_to_inbox: bool = True

    def validate(self, send_at: datetime) -> list[str]:
        """Reject an inconsistent archive/snooze combination for a send firing at send_at."""
        errors: list[str] = []
        if self.should_archive and self.should_snooze:
            errors.append("Cannot send and snooze and archive at the same time")
        if self.should_snooze and self.snoozed_until is None:
            errors.append("Snooze time is required")
        # If the compose page sat open past the chosen preset, the snooze wake is already in the past.
        # Snoozing to a past time drops the entry out of every mailbox view until the unsnooze scan
        # reaps it, so reject it here.
        if self.should_snooze and self.snoozed_until is not None and self.snoozed_until <= send_at:
            errors.append("Snooze time must be in the future")
        return errors


@dataclass
class EmailThreadCollaborationPolicy(CollaborationPolicy):
    email_thread: "EmailThread"

    async def add(self, user_to_add: User, added_by_user: User, using_db: BaseDBAsyncClient | None = None):
        async with transaction(using_db=using_db) as connection:
            result = await super().add(user_to_add, added_by_user, using_db=connection)
        await self.email_thread.publish()
        return result

    async def remove(self, user_to_remove: User, using_db: BaseDBAsyncClient | None = None):
        async with transaction(using_db=using_db) as connection:
            result = await super().remove(user_to_remove, using_db=connection)
        await self.email_thread.publish()
        return result

    async def assign_to(self, assignee: User, assigned_by: User, using_db: BaseDBAsyncClient | None = None):
        async with transaction(using_db=using_db) as connection:
            result = await super().assign_to(assignee, assigned_by, using_db=connection)
        await after_commit(lambda _: self.email_thread.broadcast_assignment_changed())
        return result

    async def unassign(self, user=None, using_db=None):
        async with transaction(using_db=using_db) as connection:
            await super().unassign(user, connection)
        await self.email_thread.publish()
        await after_commit(lambda _: self.email_thread.broadcast_assignment_changed())


@dataclass
class EmailConversation:
    messages: list["EmailMessage"]
    _messages_by_message_id_header: dict[str | None, "EmailMessage"] = field(default_factory=dict, init=False)
    _children_by_parent: dict["EmailMessage", set["EmailMessage"]] = field(default_factory=dict, init=False)
    _parent_counts: dict["EmailMessage", int] = field(default_factory=dict, init=False)

    def __post_init__(self):
        self._messages_by_message_id_header = {message.message_id: message for message in self.messages}
        self._children_by_parent = {message: set() for message in self.messages}
        self._parent_counts = {message: 0 for message in self.messages}

    def sort(self):
        """
        Sorts delivered messages into a readable thread order.

        Message parent inference priority:
        1) Use In-Reply-To if it matches a known message-id in the thread.
        2) Else, walk References from right to left and use the nearest known ancestor.
        3) Additionally, add edges between consecutive IDs in References when both exist, which helps reconstruct
           chains if some messages lack In-Reply-To.


        Last, perform a Kahn-style (https://en.wikipedia.org/wiki/Topological_sorting#Kahn's_algorithm) topological
        sort; break ties by message.sort_key.

        The result is a timeline of emails that respects both conversation threads and chronology.
        """
        # Build edges using In-Reply-To and References
        for message in self.messages:
            in_reply_to = message.headers.in_reply_to
            references = message.headers.references

            # 1) Prefer In-Reply-To if it points to a known message
            parent = None
            if in_reply_to:
                parent = self._messages_by_message_id_header.get(in_reply_to)

            # 2) Otherwise, use the nearest known ancestor from References (rightmost first)
            if parent is None and references:
                for message_id in reversed(references):
                    candidate = self._messages_by_message_id_header.get(message_id)
                    if candidate is not None and candidate is not message:
                        parent = candidate
                        break
            if parent is not None:
                self._add_edge(parent, message)

            # 3) Strengthen the graph by connecting consecutive known references. This helps when some intermediate
            # messages exist locally but lack proper headers.
            if len(references) >= 2:
                for a, b in zip(references, references[1:]):
                    parent = self._messages_by_message_id_header.get(a)
                    child = self._messages_by_message_id_header.get(b)
                    if parent is not None and child is not None and parent is not child:
                        self._add_edge(parent, child)

        # Roots: messages with no incoming edges
        root_messages = sorted(
            (message for message, count in self._parent_counts.items() if count == 0), key=lambda m: m.sort_key
        )

        # 4) Kahn's algorithm with time-ordered queue
        sorted_messages: list[EmailMessage] = []
        while root_messages:
            current = root_messages.pop(0)
            sorted_messages.append(current)

            for child in sorted(self._children_by_parent.get(current, ()), key=lambda m: m.sort_key):
                self._parent_counts[child] -= 1
                if self._parent_counts[child] == 0:
                    # Insert child into root_messages keeping time order
                    inserted = False
                    for i, other in enumerate(root_messages):
                        if child.sort_key < other.sort_key:
                            root_messages.insert(i, child)
                            inserted = True
                            break
                    if not inserted:
                        root_messages.append(child)

        # Drop any stragglers (broken/missing headers) at the end by time
        if len(sorted_messages) < len(self.messages):
            leftover = [m for m in self.messages if m not in sorted_messages]
            leftover.sort(key=lambda m: m.sort_key)
            sorted_messages.extend(leftover)

        self.messages = sorted_messages

    def _add_edge(self, parent: "EmailMessage", child: "EmailMessage"):
        if parent is child:
            return
        if child not in self._children_by_parent[parent]:
            self._children_by_parent[parent].add(child)
            self._parent_counts[child] += 1


class EmailThreadFilters(EmailLabelFilters, WorkspaceMixinFilters):
    pass


@dataclass
class EmailThreadNotificationPolicy(NotificationPolicy):
    def force_include_for_inbox(self, action: EventAction | None = None) -> bool:
        # An email thread has no per-collaborator subscription level: collaboration *is* the
        # subscription and is unconditionally ALL — there is no RELEVANT_ONLY or muted state for
        # a thread, and no Subscription rows are written for its collaborators. Force-include is
        # how the resolver expresses that invariant: every collaborator reaches the inbox on every
        # event, so `action` is ignored.
        # Honored by SubscriberResolver.resolve_for_inbox (the single home of inbox force-include).
        return True

    @property
    def notify_mention_push(self) -> bool:
        # Email threads are EmailDelivery.SKIP, so an @mention would otherwise only reach
        # the inbox. Push is the interrupt channel for in-app resources, so a thread
        # @mention pushes like a chat @mention.
        return True

    # A comment on a thread reaches its creator and assignee (the "reply on yours" audience) on
    # both push and inbox — force-surfacing the inbox re-opens a thread the owner archived. Keyed
    # to the COMMENTED action the email-thread comment endpoint fires (not POST_COMMENTED).
    creator_and_assignee_reply_actions: ClassVar[frozenset[EventAction]] = frozenset({EventAction.COMMENTED})

    async def thread_participant_ids(self, comment_id: UUID, using_db: BaseDBAsyncClient | None = None) -> set[UUID]:
        # A thread's comments are its whole conversation (reply_to is a preview pointer, not a
        # boundary), so every commenter is a participant reached by a further reply.
        comment = await EmailThreadComment.filter(id=comment_id).using_db(using_db).first()
        if comment is None:
            return set()
        rows = cast(
            list[UUID],
            await EmailThreadComment.filter(email_thread_id=comment.email_thread_id)
            .using_db(using_db)
            .values_list("user_id", flat=True),
        )
        return set(rows)


class EmailThread(EmailLabelsMixin, WorkspaceMixin, RecordModel):
    # Override WorkspaceMixin.title with column-level protection
    title: str = fields.TextField(null=False, description="protected_column")  # type: ignore[assignment]
    external_thread_id: str | None = fields.TextField(null=True)
    is_decrypted = fields.BooleanField(default=True)
    messages: fields.ReverseRelation["EmailMessage"]
    comments: fields.ReverseRelation["EmailThreadComment"]
    filters = EmailThreadFilters()
    email_delivery = EmailDelivery.SKIP

    _on_publish: ClassVar[list[Callable[["EmailThread"], Awaitable[None]]]] = []

    @classmethod
    def on_publish(cls, hook: Callable[["EmailThread"], Awaitable[None]]) -> None:
        cls._on_publish.append(hook)

    async def publish(self) -> None:
        for hook in self._on_publish:
            await hook(self)

    class Meta:
        ordering = ["-updated_at"]
        unique_together = [("external_thread_id", "creator_id")]
        indexes = (("is_decrypted",),)

    @classmethod
    async def get_or_create_for_message(
        cls, message_data: dict, using_db: BaseDBAsyncClient | None = None
    ) -> tuple["EmailThread", bool]:
        external_thread_id = message_data.get("external_thread_id")
        user_id = message_data.get("user_id") or message_data.get("creator_id")
        organization_id = message_data.get("organization_id")

        if external_thread_id:
            thread: EmailThread | None = (
                await cls.unscoped.get_queryset()
                .filter(creator_id=user_id, external_thread_id=external_thread_id)
                .using_db(using_db)
                .first()
            )
            if thread:
                if thread.is_deleted:
                    await thread.restore(using_db=using_db)
                return thread, False

        headers = EmailHeaders(message_data.get("headers_list", []))
        reference_ids: set[str] = set()
        for raw in [headers.in_reply_to, *headers.references]:
            if not raw:
                continue
            # in_reply_to/message_id keep the raw <...> brackets while references
            # strips them, and stored message_ids are bracketed — canonicalize both
            # forms so a References-only reply still matches.
            bare = raw.strip().strip("<>")
            if not bare:
                continue
            reference_ids.add(bare)
            reference_ids.add(f"<{bare}>")

        if reference_ids and user_id:
            thread = (
                await cls.unscoped.get_queryset()
                .filter(Q(messages__message_id__in=reference_ids) & cls.filters.by_collaborated_workspaces(user_id))
                .using_db(using_db)
                .first()
            )
            if thread:
                if thread.is_deleted:
                    await thread.restore(using_db=using_db)
                return thread, False

        subject = message_data.get("subject", "")
        normalized_subject = EmailMessage.normalize_subject(subject)

        try:
            thread = await cls.create(
                creator_id=user_id,
                organization_id=organization_id,
                external_thread_id=external_thread_id,
                title=normalized_subject,
                labels=[],
                has_unread=False,
                using_db=using_db,
            )
            return thread, True
        except IntegrityError:
            # A concurrent call created the same thread between our SELECT and INSERT.
            # Re-query on a fresh connection since the IntegrityError aborted any active transaction.
            thread = await (
                cls.unscoped.get_queryset().filter(creator_id=user_id, external_thread_id=external_thread_id).get()
            )
            return thread, False

    @classmethod
    async def get_or_create_for_draft(
        cls, draft_data: dict, using_db: BaseDBAsyncClient | None = None
    ) -> tuple["EmailThread", bool]:
        if draft_data.get("thread_id"):
            thread = await cls.get(id=draft_data.get("thread_id"), using_db=using_db)
            if thread.is_deleted:
                await thread.restore(using_db=using_db)
            return thread, False

        user_id = draft_data.get("user_id")
        organization_id = draft_data.get("organization_id")
        subject = draft_data.get("subject", "")
        normalized_subject = EmailMessage.normalize_subject(subject)

        thread = await cls.create(
            creator_id=user_id,
            organization_id=organization_id,
            title=normalized_subject,
            labels=[EmailLabel.DRAFT],
            has_unread=False,
            using_db=using_db,
        )

        return thread, True

    @classmethod
    async def receive_new_message(
        cls, message_data: dict, using_db: BaseDBAsyncClient | None = None
    ) -> NewMessageResult:
        async with transaction(using_db=using_db) as conn:
            thread, was_new_thread = await cls.get_or_create_for_message(message_data, using_db=conn)
            message = await thread.receive_message(message_data, using_db=conn)
            return NewMessageResult(thread=thread, email=message, was_new_thread=was_new_thread)

    @classmethod
    def notification_policy_class(cls) -> type["EmailThreadNotificationPolicy"]:
        return EmailThreadNotificationPolicy

    @staticmethod
    async def _bulk_save_message_labels(
        messages: list["EmailMessage"], using_db: BaseDBAsyncClient | None = None
    ) -> None:
        # Persist label changes for many messages in one statement instead of a
        # save() per message (the mark_read/unread N+1). bulk_update bypasses the
        # pre_save signals, so normalize each message's labels here to match what
        # sort_email_labels would have written; updated_at is intentionally left
        # untouched, matching the prior update_fields=["labels"] save.
        if not messages:
            return
        for message in messages:
            message.labels = message.normalize_labels(message.labels)
        await EmailMessage.bulk_update(messages, fields=["labels"], using_db=using_db)

    @property
    def collaboration(self):
        return EmailThreadCollaborationPolicy(self.workspace, self)

    @property
    def notification_policy(self) -> "EmailThreadNotificationPolicy":
        return EmailThreadNotificationPolicy(workspace=self.workspace)

    @property
    def sorted_conversation(self):
        delivered_messages = [message for message in self.messages if not message.is_pending]
        conversation = EmailConversation(delivered_messages)
        conversation.sort()
        return conversation.messages

    @property
    def unread_conversation(self):
        return [message for message in self.sorted_conversation if not message.is_read]

    @property
    def scheduled_send_at(self) -> datetime | None:
        """When this thread's draft is scheduled to send, if any (requires prefetched messages)."""
        for message in self.messages:
            if message.is_scheduled and not message.is_deleted:
                return message.scheduled_for
        return None

    @property
    def has_scheduled_draft(self) -> bool:
        """True if this thread's draft is scheduled to send (requires prefetched messages)."""
        return self.scheduled_send_at is not None

    def has_unread_from_others(self, owner_email: str) -> bool:
        return any(message.is_unread and not message.is_from(owner_email) for message in self.messages)

    @property
    def last_message_at(self):
        if not self.messages:
            return None
        return max(message.resolved_received_at for message in self.messages)

    # Fold the last message on top of the base event-log signal: inbound mail is ingested, not
    # recorded as a workspace event, so the base alone would miss new messages; comments and
    # decisions on the thread still count via the base.
    @property
    def indexing_activity_at(self) -> datetime:
        activity = super().indexing_activity_at
        return max(activity, self.last_message_at) if self.last_message_at else activity

    @property
    def sender_addresses_unique(self) -> list[EmailAddress]:
        unique: dict[str, EmailAddress] = {}
        messages = self.sorted_conversation if self.sorted_conversation else self.messages
        for message in messages:
            sender_key = message.sender_address.display_name
            if sender_key not in unique:
                unique[sender_key] = message.sender_address
        return list(unique.values())

    @property
    def sender_addresses_chronological(self) -> list[EmailAddress]:
        """Return all senders in chronological order (includes duplicates)."""
        messages = self.sorted_conversation if self.sorted_conversation else self.messages
        return [message.sender_address for message in messages]

    @property
    def recipient_addresses(self) -> list[EmailAddress]:
        unique: dict[str, EmailAddress] = {}
        messages = self.sorted_conversation if self.sorted_conversation else self.messages
        for message in messages:
            for recipient in message.recipient_addresses:
                recipient_key = recipient.display_name
                if recipient_key not in unique:
                    unique[recipient_key] = recipient
        return list(unique.values())

    @property
    def participant_addresses(self) -> list[EmailAddress]:
        unique: dict[str, EmailAddress] = {}
        for address in self.sender_addresses_unique + self.recipient_addresses:
            address_key = address.display_name
            if address_key not in unique:
                unique[address_key] = address
        return list(unique.values())

    @property
    def preview(self) -> str:
        if not self.messages:
            return ""

        # Prefer the oldest unread message if available
        if self.unread_conversation:
            preview_message = self.unread_conversation[0]
        elif self.sorted_conversation:
            preview_message = self.sorted_conversation[-1]
        else:
            # Fallback to any message (including drafts) if no delivered messages
            preview_message = self.messages[-1]
        if preview_message.preview:
            return preview_message.preview

        # Fallback to subject or body
        if preview_message.subject:
            return preview_message.subject
        elif preview_message.body_plain:
            return preview_message.body_plain[:100]

        return ""

    @property
    def most_recent_comment(self):
        # self.comments is the reverse relation, which bypasses EmailThreadComment's
        # NonDeletedManager — so it still contains soft-deleted comments. Skip them
        # here (ordered by created_at, newest last) so a deleted comment never becomes
        # the thread's "most recent activity".
        return next((comment for comment in reversed(self.comments) if not comment.is_deleted), None)

    @property
    def is_most_recent_activity_comment(self) -> bool:
        if not self.most_recent_comment:
            return False

        if not self.last_message_at:
            return True  # Draft threads with comments

        return self.most_recent_comment.created_at > self.last_message_at

    def is_original_recipient(self, user_id: UUID) -> bool:
        return self.creator_id == user_id

    def can_reply(self, user: User) -> bool:
        if self.is_original_recipient(user.id):
            return True
        # Assignees can send on new threads (no existing Gmail conversation)
        if self.external_thread_id is None and self.collaboration.is_assigned_to(user):
            return True
        return False

    def draft_owner_for(self, user: User) -> User:
        # Server-determined draft ownership. If `user` can send on this thread
        # (creator, or assignee on a new thread), they own their own draft.
        # Otherwise the creator owns it, because `SendEmailThroughGmailJob`
        # looks up the Gmail OAuth account from `email_draft.user_id` — only
        # the creator's account can authorize the actual send. Requires
        # `creator` to be prefetched (callers go through `get_email_thread`,
        # which already does this).
        return user if self.can_reply(user) else self.creator

    async def find_corresponding_thread(self, user_id: UUID) -> "EmailThread | None":
        """Find another user's version of this same email conversation.

        Gmail assigns different thread IDs to different recipients. This method
        finds a matching thread by comparing RFC 2822 Message-IDs, which are
        globally unique and identical across all recipients.

        Returns None if the user doesn't have their own copy of this conversation.
        """
        message_ids = [msg.message_id for msg in self.messages if msg.message_id]
        if not message_ids:
            return None

        return await EmailThread.filter(creator_id=user_id, messages__message_id__in=message_ids).first()

    async def receive_message(self, message_data: dict, using_db: BaseDBAsyncClient | None = None) -> "EmailMessage":
        async with transaction(using_db=using_db) as connection:
            user_id = message_data.get("user_id") or message_data.get("creator_id")
            message_data["user_id"] = user_id
            headers = EmailHeaders(message_data.get("headers_list", []))
            if not user_id:
                raise ValueError("User ID is required in message data")

            existing_message = cast(
                EmailMessage | None,
                await EmailMessage.unscoped.get_queryset()
                .filter(
                    EmailMessage.filters.by_message_id(headers.message_id or "", user_id)
                    | EmailMessage.filters.by_external_message_id(
                        message_data.get("external_message_id", ""), user_id
                    ),
                )
                .using_db(connection)
                .first(),
            )

            if existing_message:
                if existing_message.is_deleted:
                    await existing_message.restore(using_db=connection)

                return existing_message

            raw_data = message_data.get("raw_data")
            raw_data_file_id = None

            if raw_data:
                file_ref = await EmailMessage.store_raw_data_file(raw_data)
                raw_data_file_id = file_ref.id
                message_data["raw_data_file_id"] = raw_data_file_id

            message = await EmailMessage.create(**message_data, thread_id=self.id, using_db=connection)
            await self.update_metadata_from_messages(using_db=connection)

            async def broadcast(using_db: BaseDBAsyncClient):
                await Topic("email_thread", thread_id=self.id).broadcast(new_message_id=message.id)

            await after_commit(broadcast)
            return message

    async def remove_message(self, message: "EmailMessage", using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db=using_db) as connection:
            await message.soft_delete(connection)
            await self.update_metadata_from_messages(connection)

    async def start_draft(
        self,
        user: "User",
        subject: str | None = None,
        to: list[str] | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        body_plain: str | None = None,
        in_reply_to: "EmailMessage | None" = None,
        initial_content: str | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> "EmailDraft":
        """Create a new draft, ensuring only one draft exists per thread."""

        async with transaction(using_db=using_db) as connection:
            # Remove any existing draft first to ensure only one draft per thread
            existing_draft = await self.get_draft(using_db=connection)
            if existing_draft:
                await existing_draft.message.delete(using_db=connection)

            # If there are messages, fallback in_reply_to to the last message
            if not in_reply_to:
                await self.fetch_related("messages", using_db=connection)
                if len(self.sorted_conversation):
                    in_reply_to = self.sorted_conversation[-1]

            # Build sender from current user's email and name
            sender_address = EmailAddress.build(user.email, user.name)

            # Create the EmailMessage directly
            message_kwargs = {
                "message_type": EmailMessageType.DRAFT,
                "user_id": user.id,
                "organization_id": user.organization_id,
                "subject": subject,
                "to": to or [],
                "cc": cc or [],
                "bcc": bcc or [],
                "body_plain": body_plain,
                "sender": str(sender_address),
                "labels": [EmailLabel.DRAFT],
                "thread_id": self.id,
                "in_reply_to_id": in_reply_to.id if in_reply_to else None,
            }

            message = await EmailMessage.create(**message_kwargs, using_db=connection)
            await message.fetch_related("attachments__file", "thread__messages", using_db=connection)

            # Create EmailDraft wrapper
            draft = EmailDraft(message)
            await self.update_metadata_from_messages(using_db=connection)

        return draft

    async def get_draft(
        self, message_type: EmailMessageType = EmailMessageType.DRAFT, using_db: BaseDBAsyncClient | None = None
    ) -> "EmailDraft | None":
        """Get a draft or sending message for this thread, if it exists."""
        draft_message = (
            await EmailMessage.filter(thread_id=self.id, message_type=message_type)
            .using_db(using_db)
            .first()
            .prefetch_related("thread__messages", "attachments__file", "user", "in_reply_to")
        )
        if not draft_message:
            return None

        draft = await EmailDraft.from_message(draft_message)
        draft.thread = self
        return draft

    async def remove_draft(
        self, user: "User", draft: "EmailDraft | None" = None, using_db: BaseDBAsyncClient | None = None
    ) -> bool:
        """Remove the draft for this thread. Returns True if the thread was deleted."""
        if draft is None:
            draft = await self.get_draft(using_db=using_db)
        if not draft:
            return False

        thread_deleted = False
        async with transaction(using_db=using_db) as connection:
            await draft.message.delete(using_db=connection)
            await self.update_metadata_from_messages(using_db=connection)

            # If thread is now empty (only had this draft), delete it too
            if self.is_deleted:
                await Mailbox.delete(self, using_db=connection)
                await self.delete(using_db=connection)
                thread_deleted = True

        async def broadcast_draft_removed(using_db: BaseDBAsyncClient) -> None:
            await self._broadcast_draft_removed(user)

        await after_commit(broadcast_draft_removed)

        return thread_deleted

    async def save_draft(
        self,
        draft: "EmailDraft",
        user: User,
        using_db: BaseDBAsyncClient | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """Save changes to the draft for this thread."""

        await draft.save(using_db, update_fields)
        await self.refresh_from_db(using_db=using_db)
        await self.publish()

        async def broadcast_draft_updated(_: BaseDBAsyncClient) -> None:
            await self._broadcast_draft_updated(user)

        await after_commit(broadcast_draft_updated)

    async def create_draft(
        self,
        draft: "EmailDraft",
        using_db: BaseDBAsyncClient | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """Save a new draft - note, this does not broadcast a draft updated message."""

        await draft.save(using_db, update_fields)
        await self.refresh_from_db(using_db=using_db)
        await self.publish()

    async def mark_draft_sending(
        self, draft: "EmailDraft", user: "User", using_db: BaseDBAsyncClient | None = None
    ) -> None:
        draft.message.message_type = EmailMessageType.SENDING
        # Clear any scheduling now that the send is underway. For an immediate send both are
        # already null; for a fired scheduled draft this makes the resulting SENT message clean
        # and leaves nothing for a revert to un-set beyond the message_type.
        draft.message.scheduled_for = None
        draft.message.scheduled_send_job_id = None
        await draft.save(using_db=using_db)

        async def broadcast_draft_removed(_: BaseDBAsyncClient) -> None:
            await self._broadcast_draft_removed(user)

        await after_commit(broadcast_draft_removed)

    async def mark_draft_scheduled(
        self,
        draft: "EmailDraft",
        scheduled_for: datetime,
        job_id: UUID,
        user: "User",
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        """Commit an editable draft to send at scheduled_for. Stays message_type=DRAFT."""
        draft.message.scheduled_for = scheduled_for
        draft.message.scheduled_send_job_id = job_id
        await draft.save(using_db=using_db)

        async def broadcast_draft_scheduled(_: BaseDBAsyncClient) -> None:
            await self._broadcast_draft_scheduled(user)

        await after_commit(broadcast_draft_scheduled)

    async def mark_draft_unscheduled(
        self, draft: "EmailDraft", user: "User", using_db: BaseDBAsyncClient | None = None
    ) -> None:
        """Return a scheduled draft to an editable draft. Stays message_type=DRAFT."""
        draft.message.scheduled_for = None
        draft.message.scheduled_send_job_id = None
        await draft.save(using_db=using_db)

        async def broadcast_draft_unscheduled(_: BaseDBAsyncClient) -> None:
            await self._broadcast_draft_unscheduled(user)

        await after_commit(broadcast_draft_unscheduled)

    async def apply_send_side_effects(
        self,
        draft: "EmailDraft",
        sender: "User",
        options: SendSideEffectOptions,
        email_client: EmailClient,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        """Apply the sender-only mailbox side effects that accompany a send.

        Shared by the immediate-send endpoint and the scheduled fire job so both apply
        the sender's archive / snooze / stay-in-inbox choice identically.
        """
        # Sender-only mailbox entry mutations: not all collaborators chose this action.
        if options.should_archive:
            entry = await Mailbox(sender).entry(self).using_db(using_db).get_or_none()
            if entry:
                await entry.archive(using_db=using_db)

            if draft.external_thread_id:
                await email_client.archive_thread(
                    external_thread_id=draft.external_thread_id, user_id=sender.id, using_db=using_db
                )

        elif options.should_snooze and options.snoozed_until is not None and options.snoozed_until > datetime.now(UTC):
            # Only snooze into the future. A deferred send can fire after its chosen snooze time
            # (a stale window, or a late job run); snoozing into the past drops the entry out of
            # every mailbox view until the unsnooze scan reaps it, so fall through to inbox instead.
            entry = await Mailbox(sender).entry(self).using_db(using_db).get_or_none()
            if entry:
                await entry.snooze(options.snoozed_until, using_db=using_db)

            if draft.external_thread_id:
                await email_client.archive_thread(
                    external_thread_id=draft.external_thread_id, user_id=sender.id, using_db=using_db
                )

        elif options.pin_to_inbox:
            # An immediate send without archive/snooze keeps the sender engaged with the thread.
            # Mailbox.sync alone won't add INBOX here: the sender's own send doesn't count as
            # "activity from others", and for a draft-only shared thread, the new-entry branch
            # in _sync_inbox_state requires thread.is_inbox which is False. Pin to inbox
            # explicitly, symmetric to the archive branch.
            #
            # A deferred (scheduled) send passes pin_to_inbox=False and skips this: the fire can
            # land long after scheduling, so an archive made in the interim must stand rather than
            # resurrect the thread into the inbox. The sent message still surfaces in Sent via its
            # SENT label; only the inbox pin is suppressed.
            entry = await Mailbox(sender).entry(self).using_db(using_db).get_or_none()
            if entry and not entry.is_inbox:
                entry.label_as_inbox()
                await entry.save(update_fields=["labels"], using_db=using_db)

    async def send_draft(
        self,
        draft: "EmailDraft",
        sender: "User",
        options: SendSideEffectOptions,
        email_client: EmailClient,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        """Dispatch a locked draft: flip it to SENDING, hand delivery to the email client, and apply
        the sender's archive/inbox side effects.

        Shared by the immediate-send endpoint and the scheduled fire job so both dispatch a send
        identically. The caller owns the row lock + state guard and the post-commit ContentIndexingJob.
        """
        await self.mark_draft_sending(draft, sender, using_db=using_db)
        await email_client.send_message(email_thread_id=self.id, user_id=sender.id, using_db=using_db)
        await self.apply_send_side_effects(draft, sender, options, email_client, using_db=using_db)

    async def mark_draft_sent(
        self,
        draft: "EmailDraft",
        sender: "User",
        external_message_id: str,
        external_thread_id: str,
        external_history_id: str,
        message_id: str,
        headers: EmailHeaders,
        preview: str,
        raw_data: dict[str, Any] | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        """Mark the draft as sent after the email has been successfully delivered.

        This is called by the background email sending job after the email
        has been actually sent via the email service (Gmail API).
        """
        await draft.mark_as_sent(
            sent_from=EmailAddress.build(sender.email, sender.name),
            external_message_id=external_message_id,
            external_thread_id=external_thread_id,
            external_history_id=external_history_id,
            message_id=message_id,
            headers=headers,
            preview=preview,
            raw_data=raw_data,
            using_db=using_db,
        )

        async def broadcast(using_db: BaseDBAsyncClient):
            await Topic("email_thread", thread_id=self.id).broadcast(new_message_id=draft.message.id)

        await after_commit(broadcast)

    async def update_metadata_from_messages(self, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db=using_db) as connection:
            await self.fetch_related("messages", using_db=connection)
            delivered_messages = self.sorted_conversation

            # Compute and set timestamps from messages
            computed_created_at, computed_updated_at = self._compute_timestamps_from_messages()
            self.created_at = computed_created_at
            self.updated_at = computed_updated_at

            # Process active messages to update metadata
            all_labels = set()
            active_messages = [message for message in self.messages if not message.is_deleted]
            for message in active_messages:
                all_labels.update(message.labels)
            self.labels = list(all_labels)

            # Thread title is the subject of the first delivered message, or first draft if no delivered messages
            if delivered_messages:
                self.title = delivered_messages[0].normalized_subject or ""
            elif active_messages:
                # For draft-only threads, use the draft's subject (and allow updates when subject changes)
                self.title = active_messages[0].normalized_subject or ""

            # Handle thread soft deletion/restoration after metadata is updated
            # Don't delete threads that have active messages (including drafts)
            active_messages = [message for message in self.messages if not message.is_deleted]
            if not active_messages:
                self.deleted_at = datetime.now(UTC)
            elif self.is_deleted and active_messages:
                self.deleted_at = None

            if not self.external_thread_id:
                # If no external thread ID, set it to the first message's external thread ID if available
                first_message = delivered_messages[0] if delivered_messages else None
                if first_message and first_message.external_thread_id:
                    self.external_thread_id = first_message.external_thread_id

            if not self.changes.keys():
                return

            await self.save(update_fields=self.changes.keys(), using_db=using_db)

    async def mark_as_read(self, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db=using_db) as connection:
            changed_messages = []
            for message in self.messages:
                if message.is_unread:
                    message.label_as_read()
                    changed_messages.append(message)
            await self._bulk_save_message_labels(changed_messages, using_db=connection)

            await self.update_metadata_from_messages(using_db=connection)

    async def mark_as_unread(self, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db=using_db) as connection:
            changed_messages = []
            for message in self.messages:
                if EmailLabel.UNREAD not in message.labels:
                    message.label_as_unread()
                    changed_messages.append(message)
            await self._bulk_save_message_labels(changed_messages, using_db=connection)

            await self.update_metadata_from_messages(using_db=connection)

    async def archive(self, using_db: BaseDBAsyncClient | None = None) -> None:
        self.label_as_archived()
        await self.save(update_fields=["labels"], using_db=using_db)

    async def unarchive(self, using_db: BaseDBAsyncClient | None = None) -> None:
        self.label_as_unarchived()
        await self.save(update_fields=["labels"], using_db=using_db)

    async def broadcast_draft_started(self, user: "User") -> None:
        """Broadcast draft started event to notify collaborators."""
        topic = Topic("email_thread_draft", thread_id=self.id)
        await topic.broadcast(
            action=EmailDraftAction.DRAFT_STARTED,
            user_id=user.id,
        )

    async def broadcast_assignment_changed(self) -> None:
        topic = Topic("email_thread_draft", thread_id=self.id)
        await topic.broadcast(action=EmailDraftAction.ASSIGNMENT_CHANGED)

    async def _broadcast_draft_updated(self, user: "User") -> None:
        """Broadcast draft updated event."""
        topic = Topic("email_thread_draft", thread_id=self.id)
        await topic.broadcast(
            action=EmailDraftAction.DRAFT_UPDATED,
            user_id=user.id,
        )

    async def _broadcast_draft_removed(self, user: "User") -> None:
        """Broadcast draft removed event."""
        topic = Topic("email_thread_draft", thread_id=self.id)
        await topic.broadcast(
            action=EmailDraftAction.DRAFT_REMOVED,
            user_id=user.id,
        )

    async def _broadcast_draft_scheduled(self, user: "User") -> None:
        """Broadcast draft scheduled event."""
        topic = Topic("email_thread_draft", thread_id=self.id)
        await topic.broadcast(
            action=EmailDraftAction.DRAFT_SCHEDULED,
            user_id=user.id,
        )

    async def _broadcast_draft_unscheduled(self, user: "User") -> None:
        """Broadcast draft unscheduled event."""
        topic = Topic("email_thread_draft", thread_id=self.id)
        await topic.broadcast(
            action=EmailDraftAction.DRAFT_UNSCHEDULED,
            user_id=user.id,
        )

    def _compute_timestamps_from_messages(self) -> tuple[datetime, datetime]:
        active_messages = [m for m in self.messages if not m.is_deleted]
        if not active_messages:
            return (self.created_at or datetime.now(UTC), self.updated_at or datetime.now(UTC))

        created_at = min(m.resolved_received_at for m in active_messages)
        updated_at = max(m.resolved_received_at for m in active_messages)
        return (created_at, updated_at)


@dataclass
class EmailMessageFilters:
    @staticmethod
    def by_user(user_id: UUID) -> Q:
        return Q(user_id=user_id)

    @staticmethod
    def by_message_id(message_id: str, user_id: UUID) -> Q:
        return Q(user_id=user_id, message_id=message_id)

    @staticmethod
    def by_external_message_id(external_message_id: str, user_id: UUID) -> Q:
        return Q(user_id=user_id, external_message_id=external_message_id)

    @staticmethod
    def by_received(start: datetime | None = None, end: datetime | None = None) -> Q:
        q = Q(message_type=EmailMessageType.RECEIVED)
        if start:
            q &= Q(received_at__gte=start)
        if end:
            q &= Q(received_at__lte=end)
        return q

    @staticmethod
    def by_sent(start: datetime | None = None, end: datetime | None = None) -> Q:
        q = Q(message_type=EmailMessageType.SENT)
        if start:
            q &= Q(sent_at__gte=start)
        if end:
            q &= Q(sent_at__lte=end)
        return q


class EmailMessage(EmailLabelsMixin, SoftDeleteableMixin, RecordModel):
    external_message_id: str | None = fields.TextField(null=True)
    external_thread_id: str | None = fields.TextField(null=True)
    external_history_id: str | None = fields.TextField(null=True)
    message_id: str | None = fields.TextField(null=True)
    message_type = fields.CharEnumField(EmailMessageType, max_length=255)
    subject = fields.TextField(null=True, description="protected_column")
    sender: str | None = fields.TextField(null=True)
    to = JSONField[list[str]](default=list)
    cc = JSONField[list[str]](default=list)
    bcc = JSONField[list[str]](default=list)
    body_plain = fields.TextField(null=True, description="protected_column")
    body_html = fields.TextField(null=True, description="protected_column")
    body_markdown = fields.TextField(null=True, description="protected_column")
    headers_list = JSONField[list[dict[str, str]]](null=True, description="protected_column")
    preview = fields.TextField(null=True, description="protected_column")
    received_at: datetime | None = fields.DatetimeField(null=True)
    sent_at: datetime | None = fields.DatetimeField(null=True)
    sent_from_convictional_at: datetime | None = fields.DatetimeField(null=True)
    scheduled_for: datetime | None = fields.DatetimeField(null=True)
    scheduled_send_job_id: UUID | None = fields.UUIDField(null=True)
    raw_data_file: fields.ForeignKeyNullableRelation[FileReference] = fields.ForeignKeyField(
        "convictional.FileReference", null=True
    )
    raw_data_file_id: Annotated[UUID | None, "foreign key to raw data file"]
    thread: fields.ForeignKeyRelation[EmailThread] = fields.ForeignKeyField(
        "convictional.EmailThread", related_name="messages"
    )
    thread_id: Annotated[UUID, "foreign key to email thread"]
    in_reply_to: fields.ForeignKeyNullableRelation[Self] = fields.ForeignKeyField(
        "convictional.EmailMessage", null=True, on_delete=fields.SET_NULL
    )
    in_reply_to_id: Annotated[UUID | None, "foreign key to in reply to message"]
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="email_messages")
    user_id: Annotated[UUID, "foreign key to user"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    attachments: fields.ReverseRelation["EmailAttachment"]

    filters = EmailMessageFilters()

    class Meta:
        ordering = ["received_at", "created_at"]
        indexes = [
            ("message_id", "user_id"),
            ("external_message_id", "message_id", "deleted_at", "user_id", "received_at", "created_at"),
            ("thread_id", "message_type"),
            ("external_thread_id",),
            ("received_at", "created_at"),
            ("organization_id",),
            ("deleted_at", "user_id", "message_type", "received_at"),
            PartialIndex(fields=["user_id", "message_type", "received_at"], extra="deleted_at IS NULL"),
            ("in_reply_to_id",),
            # Keeps the overdue-scheduled-draft sweep cheap — scheduled drafts are rare, so the
            # partial index stays tiny.
            PartialIndex(fields=["scheduled_for"], extra="scheduled_for IS NOT NULL"),
        ]
        unique_together = [("external_message_id", "user_id")]

    @staticmethod
    def normalize_subject(subject: str | None) -> str:
        if not subject:
            return ""

        normalized = subject.strip()

        # Keep applying prefixes until no more are found
        changed = True
        while changed:
            old_normalized = normalized
            for prefix in EMAIL_REPLY_AND_FORWARD_PREFIXES:
                normalized = re.sub(prefix, "", normalized, flags=re.IGNORECASE).strip()
            changed = normalized != old_normalized

        return normalized

    @property
    def normalized_subject(self) -> str:
        return self.normalize_subject(self.subject)

    @property
    def is_reply(self) -> bool:
        # Check if it's a forward first - forwards are not replies but may have an In-Reply-To header
        if self.subject and any(
            re.match(prefix, self.subject, flags=re.IGNORECASE) for prefix in EMAIL_FORWARD_PREFIXES
        ):
            return False

        # Check In-Reply-To header (most reliable indicator of a reply)
        if self.headers.in_reply_to:
            return True

        # Check subject for reply prefixes as fallback
        if not self.subject:
            return False
        return any(re.match(prefix, self.subject, flags=re.IGNORECASE) for prefix in EMAIL_REPLY_PREFIXES)

    @property
    def headers(self):
        return EmailHeaders(self.headers_list)

    @property
    def sort_key(self):
        received_at = self.received_at or self.sent_at or datetime.min.replace(tzinfo=UTC)
        client_datetime = datetime.min.replace(tzinfo=UTC)
        if client_date_header := self.headers.get_one("Date"):
            try:
                client_datetime = parsedate_to_datetime(client_date_header)
                client_datetime = client_datetime.replace(tzinfo=UTC)
            except Exception:
                # Failed to parse client date, falling back to default
                pass

        return (received_at, client_datetime, self.message_id or "")

    async def get_raw_data(self) -> dict[str, Any] | None:
        if self.raw_data_file_id:
            file_ref = await FileReference.get(id=self.raw_data_file_id)
            file_content = await file_ref.download()
            return json.loads(file_content.decode())
        return None

    @staticmethod
    async def store_raw_data_file(raw_data: dict[str, Any]) -> FileReference:
        message_id = raw_data.get("id", "unknown")
        return await store_file_from_string(
            content=TrustedStr(json.dumps(raw_data)),
            filename=f"raw_data_{message_id}.json",
            content_type="application/json",
        )

    @property
    def is_pending(self) -> bool:
        """Returns True if message is a draft or currently being sent."""
        return self.message_type in [EmailMessageType.DRAFT, EmailMessageType.SENDING]

    @property
    def is_scheduled(self) -> bool:
        """A DRAFT with a send time set: read-only, awaiting its ScheduledDraftSendJob."""
        return self.scheduled_for is not None

    @property
    def was_sent(self) -> bool:
        return not self.is_pending and self.message_type == EmailMessageType.SENT and self.sent_at is not None

    @property
    def sender_address(self) -> EmailAddress:
        if not self.sender:
            return EmailAddress(name="Unknown", email="<unknown>")
        return EmailAddress.parse(self.sender)

    @property
    def recipient_addresses(self) -> list[EmailAddress]:
        addresses = []
        for recipient_list in [self.to, self.cc, self.bcc]:
            for recipient in recipient_list:
                parsed = EmailAddress.parse_safe(recipient)
                if parsed:
                    addresses.append(parsed)
        return addresses

    @property
    def resolved_received_at(self) -> datetime:
        return self.received_at or self.created_at

    def is_from(self, email: str) -> bool:
        if not self.sender:
            return False

        parsed = EmailAddress.parse_safe(email)
        return self.sender_address.email.lower() == parsed.email.lower() if parsed else False


@dataclass
class EmailDraft:
    """Facade for draft EmailMessage providing clear semantic separation."""

    message: EmailMessage

    @classmethod
    async def from_message(cls, message: EmailMessage) -> Self:
        """Wrap an existing EmailMessage as a draft (for Gmail sync)."""
        if not message.is_pending:
            raise ValueError(f"Cannot create EmailDraft from {message.message_type} message")
        await message.fetch_related("thread__messages", "attachments__file")
        return cls(message)

    async def save(
        self,
        using_db: BaseDBAsyncClient | None = None,
        update_fields: Iterable[str] | None = None,
    ) -> None:
        """Save draft changes."""
        await self.message.save(using_db=using_db, update_fields=update_fields)
        if self.message.thread_id:
            thread = await EmailThread.get(id=self.message.thread_id)
            await thread.update_metadata_from_messages(using_db)

    async def fetch_related(self, *args, **kwargs):
        """Fetch related objects."""
        await self.message.fetch_related(*args, **kwargs)
        return self

    async def refresh_from_db(self, fields: Iterable[str] | None = None, using_db: BaseDBAsyncClient | None = None):
        await self.message.refresh_from_db(fields, using_db)

    def apply_envelope(self, subject: str, to: list[str], cc: list[str], bcc: list[str]) -> None:
        """Set the addressing fields from a send/schedule request, dropping blank recipients."""
        self.message.subject = subject
        self.message.to = [addr for addr in to if addr]
        self.message.cc = [addr for addr in cc if addr]
        self.message.bcc = [addr for addr in bcc if addr]

    def set_rendered_body(self, body_content: dict) -> None:
        """Set the sanitized body columns from build_body_content output."""
        self.message.body_markdown = body_content["body_markdown"]
        self.message.body_html = body_content["body_html"]
        self.message.body_plain = body_content["body_plain"]

    def validate_for_sending(self) -> list[str]:
        validation_errors = []
        if not self.message.to:
            validation_errors.append("To field is required")

        # Validate email addresses
        for email in self.message.to:
            if not EmailAddress.is_valid_email(email):
                validation_errors.append(f"Invalid email address in To field: {email}")
        for email in self.message.cc:
            if not EmailAddress.is_valid_email(email):
                validation_errors.append(f"Invalid email address in CC field: {email}")
        for email in self.message.bcc:
            if not EmailAddress.is_valid_email(email):
                validation_errors.append(f"Invalid email address in BCC field: {email}")

        return validation_errors

    def validate_schedulable(self, scheduled_for: datetime) -> list[str]:
        now = datetime.now(UTC)
        if scheduled_for <= now:
            return ["Scheduled send time must be in the future"]
        if scheduled_for > now + SCHEDULED_SEND_MAX_HORIZON:
            return ["Scheduled send time must be within 30 days"]
        return []

    @property
    def id(self) -> UUID:
        return self.message.id

    @property
    def thread_id(self) -> UUID | None:
        return self.message.thread_id

    @property
    def user_id(self) -> UUID:
        return self.message.user_id

    @property
    def organization_id(self) -> UUID:
        return self.message.organization_id

    @property
    def thread(self) -> EmailThread:
        return self.message.thread

    @thread.setter
    def thread(self, value: EmailThread):
        self.message.thread = value
        self.message.thread_id = value.id

    @property
    def external_thread_id(self) -> str | None:
        return self.message.external_thread_id

    @external_thread_id.setter
    def external_thread_id(self, value: str | None):
        self.message.external_thread_id = value

    @property
    def external_message_id(self) -> str | None:
        return self.message.external_message_id

    @external_message_id.setter
    def external_message_id(self, value: str | None):
        self.message.external_message_id = value

    @property
    def changes(self):
        return self.message.changes

    @property
    def sender(self) -> str:
        return self.message.sender or ""

    @property
    def to(self):
        return ", ".join(self.message.to) if self.message.to else ""

    @property
    def cc(self):
        return ", ".join(self.message.cc) if self.message.cc else ""

    @property
    def bcc(self):
        return ", ".join(self.message.bcc) if self.message.bcc else ""

    @property
    def subject(self):
        return self.message.subject or ""

    @property
    def in_reply_to(self):
        if self.message.in_reply_to and self.message.in_reply_to.message_id:
            return self.message.in_reply_to.message_id

        return ""

    @property
    def references(self):
        if not self.message.in_reply_to:
            return ""

        parent = self.message.in_reply_to
        references_parts = []

        # Get parent's References field content
        parent_headers = EmailHeaders(parent.headers_list)
        if parent_headers.references:
            references_parts.extend(parent_headers.references)
        # If no References but has In-Reply-To, use that instead
        elif parent_headers.in_reply_to:
            references_parts.append(parent_headers.in_reply_to)

        # Add parent's Message-ID if it exists
        if parent.message_id:
            references_parts.append(parent.message_id)

        return " ".join(references_parts)

    @property
    def live_document_topic(self) -> "Topic":
        """Get the live document topic for collaborative editing of this draft."""
        return Topic("email_draft", message_id=self.id)

    def _get_sendable_attachments(self) -> list["EmailAttachment"]:
        """Return attachments that should be included with this email.

        Includes:
        - All non-inline attachments
        - Inline attachments that are still referenced in the HTML body

        Excludes:
        - Inline attachments that are no longer referenced in the HTML body
        """
        html_content = self.message.body_html or ""
        if not self.message.attachments:
            return []

        sendable_attachments = []
        for attachment in self.message.attachments:
            if not attachment.is_inline or attachment._is_referenced_in_html(html_content):
                sendable_attachments.append(attachment)

        return sendable_attachments

    async def as_payload(self) -> EmailPayload:
        sendable_attachments = self._get_sendable_attachments()
        attachments = list(await asyncio.gather(*(a.as_payload() for a in sendable_attachments)))

        return EmailPayload(
            id=str(self.id),
            to=self.to,
            cc=self.cc,
            bcc=self.bcc,
            display_from=self.sender,
            subject=self.message.subject or "",
            text=self.message.body_plain or "",
            html=self.message.body_html or "",
            in_reply_to=self.in_reply_to,
            references=self.references,
            sent_at=self.message.sent_at,
            attachments=attachments,
        )

    async def get_live_document_markdown(self) -> str:
        """Get the current markdown content from the live document.

        Returns:
            str: The markdown content from the live document
        """
        topic = self.live_document_topic
        live_doc = await LiveDocument.for_topic(topic)
        markdown = live_doc.markdown or ""

        if not markdown:
            with LoggingContext(
                message_id=self.id,
                thread_id=self.thread_id,
                topic_name=topic.name,
                has_markdown_field=bool(live_doc.get("markdown", type=Text)),
                has_initial_content_field=bool(live_doc.get("initial_content", type=Text)),
            ):
                logger.warning("Live document returned empty markdown for email draft")

        return markdown

    async def mark_as_sent(
        self,
        sent_from: EmailAddress,
        external_message_id: str,
        external_thread_id: str,
        external_history_id: str,
        message_id: str,
        headers: EmailHeaders,
        preview: str,
        raw_data: dict[str, Any] | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        # Content should already be stored in the model at this point
        now = datetime.now(UTC)
        self.message.sent_at = now
        self.message.sent_from_convictional_at = now
        self.message.received_at = now
        self.message.message_type = EmailMessageType.SENT
        self.message.label_as_sent()
        self.message.label_as_not_draft()

        # Check if user is sending to themselves and label as inbox if so (unless thread is archived)
        sender_email = sent_from.email.lower()
        all_recipients = self.message.to + self.message.cc + self.message.bcc
        recipient_emails = []
        for r in all_recipients:
            parsed = EmailAddress.parse_safe(r)
            if parsed:
                recipient_emails.append(parsed.email.lower())

        if sender_email in recipient_emails:
            if not self.thread.is_archived:
                self.message.label_as_inbox()
            else:
                # Remove INBOX label if thread is archived (respects send & archive intent)
                if self.message.is_inbox:
                    self.message.label_as_archived()

        self.message.sender = str(sent_from)
        self.message.message_id = message_id
        self.message.external_message_id = external_message_id
        self.message.external_thread_id = external_thread_id
        self.message.external_history_id = external_history_id
        self.message.headers_list = headers
        self.message.preview = preview

        if raw_data:
            file_ref = await EmailMessage.store_raw_data_file(raw_data)
            self.message.raw_data_file_id = file_ref.id

        # Clean up unreferenced inline attachments from the database
        sendable_attachments = self._get_sendable_attachments()
        sendable_attachment_ids = {a.id for a in sendable_attachments}

        if self.message.attachments:
            for attachment in self.message.attachments:
                if attachment.id not in sendable_attachment_ids:
                    await attachment.delete(using_db=using_db)

        self.message.has_jsonb_migrated = True
        await self.save(update_fields=self.changes.keys(), using_db=using_db)
        await self.thread.update_metadata_from_messages(using_db=using_db)


@pre_save(EmailMessage)
async def ensure_thread_before_save(
    sender: "type[EmailMessage]", instance: EmailMessage, using_db: BaseDBAsyncClient | None, update_fields: list[str]
) -> None:
    if not instance.thread_id:
        thread, _ = await EmailThread.get_or_create_for_message(
            {
                "user_id": instance.user_id,
                "organization_id": instance.organization_id,
                "external_thread_id": instance.external_thread_id,
                "subject": instance.subject,
            },
            using_db=using_db,
        )
        instance.thread_id = thread.id


class EmailAttachment(RecordModel):
    external_attachment_id: str | None = fields.TextField(null=True)
    content_id = fields.TextField(null=True)
    is_inline = fields.BooleanField(default=False)
    is_referenced_in_html = fields.BooleanField(default=False)
    file: fields.ForeignKeyRelation[FileReference] = fields.ForeignKeyField("convictional.FileReference")
    file_id: Annotated[UUID, "foreign key to file"]
    email_message: fields.ForeignKeyRelation["EmailMessage"] = fields.ForeignKeyField(
        "convictional.EmailMessage", related_name="attachments"
    )
    email_message_id: Annotated[UUID, "foreign key to email message"]
    thread: fields.ForeignKeyRelation["EmailThread"] = fields.ForeignKeyField(
        "convictional.EmailThread", related_name="attachments"
    )
    thread_id: Annotated[UUID, "thread id for faster attachment URL generation"]

    class Meta:
        unique_together = [("external_attachment_id", "email_message_id")]
        indexes = [
            ("thread_id",),
            ("email_message_id",),
            ("thread_id", "email_message_id"),
        ]

    async def as_payload(self) -> EmailAttachmentPayload:
        file_content = await self.file.download()

        payload = EmailAttachmentPayload(
            id=self.id,
            external_attachment_id=self.external_attachment_id,
            content_id=self.content_id,
            is_inline=self.is_inline,
            filename=self.file.filename,
            content_type=self.file.content_type,
            content=file_content,
            file_byte_size=self.file.byte_size,
            download_url=self._download_url(),
        )
        return payload

    def _download_url(self) -> str | None:
        """Generate a download URL for an email attachment."""
        if not self.email_message_id or not self.id:
            return None

        return urljoin(
            str(settings.base_url),
            f"email_threads/{self.thread_id}/attachments/{self.id}/download",
        )

    def _is_referenced_in_html(self, html_content: str) -> bool:
        """Check if this inline attachment is referenced in the given HTML content."""
        if not html_content:
            return False
        download_url = self._download_url()
        if download_url:
            return download_url in html_content
        # Also check by content_id for cid: references (used in received emails)
        if self.content_id:
            return f"cid:{self.content_id}" in html_content
        return False


@dataclass
class EmailReply:
    in_reply_to: EmailMessage
    replier: User
    reply_type: EmailReplyType

    @property
    def sender(self):
        return self.in_reply_to.sender

    @property
    def to(self):
        reply_address = self.in_reply_to.headers.reply_to or self.sender
        parsed_reply_address = EmailAddress.parse_safe(reply_address) if reply_address else None
        if not parsed_reply_address:
            return []
        if parsed_reply_address.email == self.replier.email:
            # When replying to your own message, reply to the original recipients
            return self.in_reply_to.to
        return [reply_address]

    @property
    def cc(self) -> list[str]:
        if not self.reply_type.is_reply_all:
            return []

        exclude_emails = {self.replier.email}
        for to_address in self.to:
            parsed = EmailAddress.parse_safe(to_address)
            if parsed:
                exclude_emails.add(parsed.email)

        cc_list = []
        for recipient in self.in_reply_to.to + self.in_reply_to.cc:
            parsed = EmailAddress.parse_safe(recipient)
            if parsed and parsed.email not in exclude_emails:
                cc_list.append(parsed)

        return [str(address) for address in cc_list]

    @property
    def subject(self) -> str:
        return f"Re: {self.in_reply_to.normalized_subject}"


class EmailThreadComment(SoftDeleteableMixin, CommentMixin, RecordModel):
    comment_topic: ClassVar[str] = "email_thread_comments"
    comment_topic_param: ClassVar[str] = "email_thread_id"

    email_thread: fields.ForeignKeyRelation[EmailThread] = fields.ForeignKeyField(
        "convictional.EmailThread", related_name="comments"
    )
    email_thread_id: Annotated[UUID, "foreign key to email thread"]
    reply_to: fields.ForeignKeyNullableRelation["EmailThreadComment"] = fields.ForeignKeyField(
        "convictional.EmailThreadComment", related_name="replies", null=True, on_delete=fields.SET_NULL
    )
    reply_to_id: Annotated[UUID | None, "foreign key to email_thread_comment"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("email_thread_id",), ("reply_to_id",))


post_delete(EmailThreadComment)(delete_decision_for_comment)
