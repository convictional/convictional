import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum, auto
from typing import Annotated, Any, ClassVar, NamedTuple, Self, assert_never, cast
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields
from tortoise.expressions import Q
from tortoise.queryset import QuerySet

from app.models.accounts import Organization, User
from app.models.collaboration.workspace import Event, SubscriberResolver, WorkspaceMixin
from config import logger, settings
from config.enums import EventAction, MailboxLabel, MailboxViewLayout, MailboxViewName
from config.logging import LoggingContext
from infra.cache import cache
from infra.db import (
    GinIndex,
    GlobalID,
    GlobalIDField,
    JSONField,
    RecordModel,
    SoftDeleteableFilters,
    SoftDeleteableMixin,
    transaction,
)
from infra.messaging import Topic
from infra.server import run_in_background
from lib.uuid import parse_uuid

# Actions that revise existing content (message/comment edits & deletes, or a minor goal field
# edit like title/description/date) rather than adding new conversation activity. That property
# drives two behaviors: routing must not re-alert caught-up readers (only a newly-@mentioned user
# is surfaced — see InboxUpdate.for_event), and the email content layer excludes them from the
# activity cursor (a typo-fix must not float the thread). Chat and email share this because they
# share one engine; goals join it for GOAL_UPDATED so a title/description tweak refreshes the row
# silently instead of re-alerting (a posted update / comment / lifecycle change is a distinct
# action and still alerts).
CONTENT_REVISION_ACTIONS = frozenset(
    {
        EventAction.CHAT_MESSAGE_EDITED,
        EventAction.CHAT_MESSAGE_DELETED,
        EventAction.EMAIL_THREAD_COMMENT_EDITED,
        EventAction.EMAIL_THREAD_COMMENT_DELETED,
        EventAction.GOAL_UPDATED,
    }
)


class InboxUpdate(Enum):
    IGNORE = auto()
    REFRESH_CONTENT = auto()
    # Surface the row (inbox + unread) only if the resource's content gate (`_refresh_content`)
    # agrees there is genuinely new activity — the idempotency guard for ordinary new messages
    # (a retry that finds nothing new must not re-mark a read row).
    MARK_UNREAD = auto()
    # Surface the row regardless of the content gate. Used for a direct ask the gate can't see:
    # an @mention or an assignment (a direct ask must reach the inbox even when the resource's
    # gate would hide it — e.g. an email thread Gmail archived), an edit's newly-added @mention,
    # or a DECIDED mark (which creates no message, so chat's message-based gate is blind to it).
    # This routing decision is authoritative — the apply step does not second-guess it.
    MARK_UNREAD_FORCED = auto()

    @classmethod
    def for_event(
        cls,
        *,
        action: EventAction,
        event_reaches_user: bool,
        user_is_sender: bool,
        user_has_existing_row: bool,
        user_is_direct_recipient: bool,
    ) -> "InboxUpdate":
        """How one event should update one person's inbox row — the whole rule, in one place.

        Inputs (all per-(event, user)):
        - `action`: the event's action. Content-revision actions (message/comment edits &
          deletes, `CONTENT_REVISION_ACTIONS`) must not re-alert; `DECIDED` always alerts whom
          it reaches.
        - `event_reaches_user`: the event reaches them (ALL-level, @mentioned, or DM
          force-include) — see `SubscriberResolver.resolve_for_inbox`.
        - `user_is_sender`: they authored it, so ordinary activity never marks their own row
          unread — but directly targeting yourself does (see `user_is_direct_recipient`).
        - `user_has_existing_row`: they already have a row (archived/snoozed/muted included)
          — see `MailboxEntry.existing_owner_ids_for_resource`.
        - `user_is_direct_recipient`: this event personally targets them — an @mention, or the
          assignee of an assignment. A direct ask must reach the inbox regardless of the
          resource's content gate (e.g. an email thread Gmail archived), so on a fresh event it
          surfaces them (forced) even when they sent it (targeting yourself notifies you like a
          teammate targeting you); on an edit only a *new* target (no prior row) surfaces, so
          re-mentioning a caught-up reader stays quiet.

        The whole decision as a table (first matching row wins):

          action      reached  sender  direct  has-row  → outcome
          revision      -        no      yes      no     → MARK_UNREAD_FORCED  (edit adds a new mention)
          revision      -        -        -        -      → REFRESH_CONTENT if reached or has-row, else IGNORE
          any           yes      yes     yes       -      → MARK_UNREAD_FORCED  (self-target — gate can't see it)
          any           yes      yes     no        -      → REFRESH_CONTENT     (never alert the sender)
          any           yes      no      yes       -      → MARK_UNREAD_FORCED  (direct ask bypasses the gate)
          DECIDED       yes      no       -        -      → MARK_UNREAD_FORCED
          other         yes      no      no        -      → MARK_UNREAD         (content gate decides)
          any           no       -        -        yes    → REFRESH_CONTENT     (keep an existing row current)
          any           no       -        -        no     → IGNORE

        FORCED vs plain MARK_UNREAD is the only nuance the apply step acts on: FORCED bypasses
        the resource content gate, plain MARK_UNREAD defers to it.
        """
        if action in CONTENT_REVISION_ACTIONS:
            # An edit only alerts a genuinely new direct target (someone with no prior row),
            # never the editor themselves — a typo-fix must not re-surface caught-up readers.
            if user_is_direct_recipient and not user_has_existing_row and not user_is_sender:
                return cls.MARK_UNREAD_FORCED
            if event_reaches_user or user_has_existing_row:
                return cls.REFRESH_CONTENT
            return cls.IGNORE
        if event_reaches_user:
            if user_is_sender:
                # Ordinary own activity never self-alerts; directly targeting yourself does —
                # and the content gate can't see it (it keys on activity from others), so force
                # it so a self-mention/self-assign notifies you exactly like a teammate would.
                return cls.MARK_UNREAD_FORCED if user_is_direct_recipient else cls.REFRESH_CONTENT
            # A direct ask (@mention or assignment) must surface past the resource content gate
            # — for an email thread that gate includes Gmail archive state, which would
            # otherwise swallow a mention/assignment on an archived thread. This is per-user, so
            # collaborators merely reached by force-include stay on the gated path below.
            if user_is_direct_recipient or action == EventAction.DECIDED:
                return cls.MARK_UNREAD_FORCED
            return cls.MARK_UNREAD
        if user_has_existing_row:
            return cls.REFRESH_CONTENT
        return cls.IGNORE


class MailboxEntryFilters(SoftDeleteableFilters):
    inbox: ClassVar[Q] = Q(labels__contains=[MailboxLabel.INBOX])
    archived: ClassVar[Q] = ~Q(labels__contains=[MailboxLabel.INBOX]) & Q(snoozed_until__isnull=True)
    unread: ClassVar[Q] = Q(labels__contains=[MailboxLabel.UNREAD])

    @classmethod
    def ai_included(cls) -> Q:
        return Q(is_ai_excluded=False)

    @classmethod
    def is_snooze_expiring(cls) -> Q:
        return Q(snoozed_until__isnull=False, snoozed_until__lte=datetime.now(UTC))

    @classmethod
    def is_snoozed(cls) -> Q:
        return Q(snoozed_until__isnull=False, snoozed_until__gt=datetime.now(UTC))

    @classmethod
    def by_owner(cls, owner_id: UUID) -> Q:
        return Q(owner_id=owner_id)

    @classmethod
    def by_resource(cls, resource_gid: GlobalID) -> Q:
        return Q(resource_gid=str(resource_gid))

    @classmethod
    def by_assignee(cls, assignee_id: UUID) -> Q:
        return Q(assignee_id=assignee_id)

    @classmethod
    def by_label(cls, label: str) -> Q:
        return Q(labels__contains=[label])


class MailboxEntry(SoftDeleteableMixin, RecordModel):
    title = fields.TextField(null=False, description="protected_column")
    preview = fields.TextField(null=False, description="protected_column")
    last_comment: str | None = fields.TextField(null=True, description="protected_column")
    is_shared = fields.BooleanField(default=False)
    last_activity_at = fields.DatetimeField(auto_now_add=True)
    last_comment_author: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="mailbox_entry_last_comment_author", null=True
    )
    last_comment_author_id: Annotated[UUID | None, "foreign key to last comment author"]
    owner: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="mailbox_entries"
    )
    owner_id: Annotated[UUID, "foreign key to user"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    assignee: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="mailbox_entry_assignee", null=True
    )
    assignee_id: Annotated[UUID | None, "foreign key to assignee user"]
    # The latest workspace event behind a non-authored ("activity") preview line. The client
    # phrases it from the event's action + details, so no display string is denormalized here.
    # Authored previews (chat messages, email replies) still ride last_comment above.
    last_event: fields.ForeignKeyNullableRelation[Event] = fields.ForeignKeyField(
        "convictional.Event", related_name="mailbox_entries", null=True, on_delete=fields.SET_NULL
    )
    last_event_id: Annotated[UUID | None, "foreign key to latest activity event"]
    labels = JSONField[list[str]](default=list)
    resource_gid = GlobalIDField(null=False)
    snoozed_until: datetime | None = fields.DatetimeField(null=True)
    workspace_attachment_count: int = fields.IntField(default=0)
    is_preview_comment = fields.BooleanField(default=False)
    is_ai_excluded = fields.BooleanField(default=False)
    read_at: datetime | None = fields.DatetimeField(null=True)
    filters = MailboxEntryFilters()

    class Meta:
        ordering = ["-last_activity_at"]
        unique_together = (("resource_gid", "owner_id"),)
        indexes = [
            ("owner_id", "last_activity_at"),
            GinIndex(fields=("labels",)),
        ]

    @property
    def is_owner(self) -> bool:
        return not self.is_shared

    @property
    def is_inbox(self) -> bool:
        return MailboxLabel.INBOX in self.labels

    @property
    def is_read(self) -> bool:
        return MailboxLabel.UNREAD not in self.labels

    @property
    def is_unread(self) -> bool:
        return MailboxLabel.UNREAD in self.labels

    @property
    def is_archived(self) -> bool:
        return MailboxLabel.INBOX not in self.labels

    @property
    def is_snoozed(self) -> bool:
        return self.snoozed_until is not None

    @property
    def has_resource(self) -> bool:
        return self.resource_gid is not None

    @property
    def resource_type(self) -> str | None:
        return self.resource_gid.record_type if self.resource_gid else None

    @property
    def is_unsnoozing_now(self) -> bool:
        return self.snoozed_until is not None and self.snoozed_until <= datetime.now(UTC)

    @property
    def is_snoozed_now(self) -> bool:
        # Time-aware to match MailboxEntryFilters.is_snoozed() (the queryset Q). The plain
        # `is_snoozed` property only checks for non-null snoozed_until, so it stays True
        # between expiry and the next CheckSnoozedMailboxEntriesJob tick — and that
        # property is load-bearing for the unsnooze job's idempotency guard, so callers
        # who need the request-time view use this property instead.
        return self.snoozed_until is not None and self.snoozed_until > datetime.now(UTC)

    def is_assigned_to(self, user: User) -> bool:
        return self.assignee_id == user.id

    # Reassign labels rather than mutating in place: change tracking keys off
    # __setattr__ (see infra/db.py), so an in-place .append()/.remove() is
    # invisible to entry.changes and gets dropped by dynamic update_fields saves.
    def label_as_inbox(self) -> None:
        if not self.is_inbox:
            self.labels = [*self.labels, MailboxLabel.INBOX]

    def label_as_read(self) -> None:
        if self.is_unread:
            self.labels = [label for label in self.labels if label != MailboxLabel.UNREAD]

    def label_as_unread(self) -> None:
        if not self.is_unread:
            self.labels = [*self.labels, MailboxLabel.UNREAD]

    def label_as_archived(self) -> None:
        if MailboxLabel.INBOX in self.labels:
            self.labels = [label for label in self.labels if label != MailboxLabel.INBOX]

    def label_as_unarchived(self) -> None:
        if self.is_archived:
            self.labels = [*self.labels, MailboxLabel.INBOX]

    async def mark_as_read(self, using_db: BaseDBAsyncClient | None = None) -> None:
        if self.is_unread:
            self.label_as_read()
            self.read_at = datetime.now(UTC)
            await self.save(update_fields=["labels", "read_at"], using_db=using_db)

    async def mark_as_unread(self, using_db: BaseDBAsyncClient | None = None) -> None:
        # Clearing read_at re-expands the whole email thread (collapsedMessageIdsFor). The
        # new-message unread path uses label_as_unread, not this, so it keeps read_at.
        if not self.is_unread or self.read_at is not None:
            self.label_as_unread()
            self.read_at = None
            await self.save(update_fields=["labels", "read_at"], using_db=using_db)

    async def archive(self, using_db: BaseDBAsyncClient | None = None) -> None:
        if not self.is_archived:
            self.label_as_archived()
            await self.save(update_fields=["labels"], using_db=using_db)

    async def unarchive(self, using_db: BaseDBAsyncClient | None = None) -> None:
        if self.is_archived:
            self.label_as_unarchived()
            await self.save(update_fields=["labels"], using_db=using_db)

    async def snooze(self, snoozed_until: datetime, using_db: BaseDBAsyncClient | None = None) -> None:
        if not self.is_snoozed:
            self.snoozed_until = snoozed_until
            self.label_as_archived()
            await self.save(update_fields=["labels", "snoozed_until"], using_db=using_db)

    async def unsnooze(self, using_db: BaseDBAsyncClient | None = None) -> None:
        if self.is_snoozed:
            self.snoozed_until = None
            self.last_activity_at = datetime.now(UTC)
            self.label_as_unarchived()
            self.label_as_unread()
            await self.save(update_fields=self.changes.keys(), using_db=using_db)

    @classmethod
    async def existing_owner_ids_for_resource(
        cls,
        resource_gid: GlobalID,
        *,
        using_db: BaseDBAsyncClient | None = None,
    ) -> set[UUID]:
        """Owners who have a row for this resource — archived, snoozed, and muted
        included. Their row's content stays current with the conversation; whether
        it's unread or in their inbox is a separate decision (mute and archive
        affect that, not the preview). See `InboxUpdate.for_event`.

        Lives here rather than on `SubscriberResolver` because importing
        `MailboxEntry` into `workspace.py` would close a circular import
        (`workspace.py` <- `mailbox.py`).
        """
        owner_ids = cast(
            list[UUID],
            await cls.filter(MailboxEntryFilters.by_resource(resource_gid))
            .using_db(using_db)
            .values_list("owner_id", flat=True),
        )
        return set(owner_ids)


@dataclass
class MailboxSync:
    entry_id: UUID
    user_id: UUID

    @property
    def lock_key(self) -> str:
        return f"mailbox_sync:{self.user_id}"

    @property
    def pending_key(self) -> str:
        return f"mailbox_sync_pending:{self.user_id}"

    async def broadcast(self) -> None:
        run_in_background(self._debounced_broadcast)

    async def _debounced_broadcast(self, shutdown_signal: asyncio.Event) -> None:
        if settings.mailbox_sync_debounce_seconds == 0:
            await Topic("mailbox_sync", user_id=self.user_id).broadcast(entry_ids=[str(self.entry_id)])
            return

        try:
            cache_ttl = timedelta(seconds=settings.mailbox_sync_debounce_seconds + 1)

            # Every caller accumulates its entry into a shared set so the broadcast at
            # the end of the window reports *all* changes, not just the one that opened
            # it. Without this, downstream skip logic in the `mailbox_sync` stream
            # handlers would discard broadcasts whose first trigger happened to be
            # off-page even when later, on-page changes were coalesced behind it.
            await cache.set_add(self.pending_key, str(self.entry_id))
            await cache.expire(self.pending_key, cache_ttl)

            # Only the first caller in the window schedules the broadcast; everyone
            # else has already added themselves to the pending set above.
            if await cache.exists(self.lock_key):
                return
            await cache.write(self.lock_key, "pending", expires_in=cache_ttl)

            try:
                await asyncio.wait_for(shutdown_signal.wait(), timeout=settings.mailbox_sync_debounce_seconds)
                return
            except TimeoutError:
                pass

            entry_ids = await cache.set_read(self.pending_key)
            # Pop only the ids we're about to broadcast. If another change races in
            # between `set_read` and here it stays in the set for the next window,
            # so we don't silently drop it.
            for eid in entry_ids:
                await cache.set_remove(self.pending_key, eid)

            # Release the scheduler lock the moment the window closes. If we let it
            # die via TTL there's a ~1s gap where a new caller adds to `pending_key`,
            # sees the dying lock, and returns without scheduling — leaving its
            # entry orphaned until something else triggers a fresh window. In a
            # quiet tail (a self-sent email after a backfill burst) that orphan
            # never gets delivered.
            await cache.delete(self.lock_key)

            # A benign TOCTOU between `exists(lock_key)` and `write(lock_key)` can
            # leave a second scheduler running on the same window with an empty
            # `pending_key` (the first drained it). An empty broadcast trips the
            # downstream skip path into a full re-render, which is exactly what
            # this PR is trying to avoid — drop it silently.
            if entry_ids:
                await Topic("mailbox_sync", user_id=self.user_id).broadcast(entry_ids=sorted(entry_ids))

            # A caller that landed in `pending_key` between `set_read` and
            # `cache.delete` above saw the lock still held and exited without
            # scheduling. Kick off one more cycle so their entry isn't orphaned.
            # The cycle drains the whole set, so one re-trigger is sufficient even
            # if multiple callers raced in. We scan until we find a parseable id
            # so a single malformed entry doesn't strand the rest behind it.
            leftover = await cache.set_read(self.pending_key)
            for raw_id in leftover:
                leftover_id = parse_uuid(raw_id)
                if leftover_id is None:
                    continue
                await MailboxSync(entry_id=leftover_id, user_id=self.user_id).broadcast()
                break

        except Exception:
            with LoggingContext(user_id=self.user_id, entry_id=self.entry_id):
                logger.exception("Debounced mailbox broadcast failed")


class BaseMailboxEntryFilters:
    resource_model: ClassVar[type[RecordModel]]

    @classmethod
    def _type_scope(cls) -> Q:
        return Q(resource_gid__startswith=f"gid://convictional/{cls.resource_model.__name__}/")

    @classmethod
    def inbox(cls) -> Q:
        return cls._type_scope() & MailboxEntryFilters.inbox

    @classmethod
    def archived(cls) -> Q:
        return cls._type_scope() & MailboxEntryFilters.archived

    @classmethod
    def snoozed(cls) -> Q:
        return cls._type_scope() & MailboxEntryFilters.is_snoozed()

    @classmethod
    def sent(cls) -> Q | None:
        return None

    @classmethod
    def draft(cls) -> Q | None:
        return None


class AuthoredPreview(NamedTuple):
    """An event whose second inbox line is authored text (a comment, or a goal's posted update):
    its `content` and `author_id` fill the preview, and `is_comment` renders it as a chip bubble."""

    content: str
    author_id: UUID
    is_comment: bool


class BaseMailboxEntry(ABC):
    resource_model: ClassVar[type[RecordModel]]
    entry_filters: ClassVar[type[BaseMailboxEntryFilters]]
    # Relations the shared `sync` prefetches before recomputing rows. Each resource
    # declares exactly what its `_refresh_content` reads.
    prefetch_for_sync: ClassVar[tuple[str, ...]]

    async def _prefetch_for_sync(self, using_db: BaseDBAsyncClient | None = None) -> None:
        # Async hook so a resource can load more than fetch_related can express (a filtered or
        # ordered read) before the synchronous `_refresh_content` pass — see ChatMailboxEntry.
        await self.resource.fetch_related(*self.prefetch_for_sync, using_db=using_db)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if "resource_model" not in cls.__dict__:
            return
        mailbox_entry_registry[cls.resource_model.record_type] = cls
        cls.entry_filters.resource_model = cls.resource_model

    @property
    @abstractmethod
    def resource(self) -> WorkspaceMixin: ...

    @classmethod
    @abstractmethod
    def from_resource(cls, resource: RecordModel) -> Self: ...

    def _refresh_content(self, entry: MailboxEntry) -> bool:
        """Refresh the row's content to mirror the resource (title, preview,
        last_comment, activity cursor, deletion); never touches inbox/unread/snooze.
        Returns whether this is new activity worth surfacing —
        `_refresh_content_and_mark_unread` uses it to gate the unread bump.

        This is the shared skeleton for workspace-event-driven entries (posts, goals): the
        deletion sync, activity cursor, and attachment count are identical, so subclasses only
        supply the resource-specific fields via `_refresh_resource_fields`. Entries whose row
        isn't event-driven (chats, email threads) override this wholesale."""
        resource = self.resource
        entry.preview = ""
        entry.assignee_id = resource.workspace.assignee_id
        self._refresh_resource_fields(entry)

        if resource.is_deleted and not entry.is_deleted:
            entry.deleted_at = datetime.now(UTC)
        elif not resource.is_deleted and entry.is_deleted:
            entry.deleted_at = None

        last_activity_at = self._compute_last_activity_at()
        old_last_activity_at = entry.last_activity_at if not entry.is_new else None
        entry.last_activity_at = last_activity_at

        has_new_activity = self._has_new_activity(entry, old_last_activity_at)
        has_activity_from_others = resource.workspace.last_event_by_others(entry.owner_id) is not None

        entry.workspace_attachment_count = len(resource.workspace.attachments)
        # A new shared row (or one with activity from others) surfaces immediately;
        # existing rows surface on genuinely new activity from others.
        return (entry.is_new and (entry.is_shared or has_activity_from_others)) or has_new_activity

    def _refresh_resource_fields(self, entry: MailboxEntry) -> None:
        """Set the fields that genuinely differ between event-driven resources — title,
        `is_shared`, and the preview slot. The `_refresh_content` skeleton owns everything
        around it. Only reached by resources that use that skeleton.

        Not @abstractmethod: subclasses that override `_refresh_content` wholesale (chat,
        email) never call this, so making it abstract would force a dead stub on them."""
        raise NotImplementedError

    def _apply_event_preview(self, entry: MailboxEntry) -> None:
        """Summarize the resource's newest workspace event on the second inbox line. An authored
        event (a comment, or a goal's posted update) fills `last_comment` with its text + author —
        a comment also sets `is_preview_comment` so the client renders a chip. Every other event is
        pinned in `last_event` for the client to phrase as an activity line from its action/details.
        Subclasses declare only their authored vocabulary via `_authored_preview`; the reset, the
        newest-event pick, and the activity fallback live here so no subclass repeats them."""
        entry.last_comment = None
        entry.last_comment_author_id = None
        entry.is_preview_comment = False
        entry.last_event_id = None

        latest_event = max(self.resource.workspace.events, key=lambda event: event.created_at, default=None)
        if latest_event is None:
            return

        if (authored := self._authored_preview(latest_event)) is not None:
            entry.last_comment = authored.content
            entry.last_comment_author_id = authored.author_id
            entry.is_preview_comment = authored.is_comment
        else:
            entry.last_event_id = latest_event.id

    def _authored_preview(self, event: Event) -> AuthoredPreview | None:
        """The authored comment/update this event surfaces, or None to render it as an activity
        line. Default None (no authored events); only event-driven subclasses (goals, posts)
        override, matching the event's action against their own comment/update vocabulary."""
        return None

    def _compute_last_activity_at(self) -> datetime:
        resource = self.resource
        last_activity_at = resource.created_at
        if resource.workspace.last_event_at and resource.workspace.last_event_at > last_activity_at:
            last_activity_at = resource.workspace.last_event_at
        return last_activity_at

    def _has_new_activity(self, entry: MailboxEntry, old_last_activity_at: datetime | None) -> bool:
        if entry.is_new:
            return False

        resource = self.resource
        last_event_from_others = resource.workspace.last_event_by_others(entry.owner_id)
        if not last_event_from_others or not old_last_activity_at:
            return "deleted_at" in entry.changes

        has_new_activity_from_others = last_event_from_others.created_at > old_last_activity_at
        return has_new_activity_from_others or "deleted_at" in entry.changes

    def _refresh_content_and_mark_unread(self, entry: MailboxEntry) -> None:
        """The GATED surface (InboxUpdate.MARK_UNREAD): refresh content and raise the row to
        attention — inbox + unread, cancelling any snooze — only when `_refresh_content` reports
        genuinely new activity. The content gate is the idempotency guard for ordinary new
        messages. Resources whose attention isn't a simple unread flag (email) override this."""
        if self._refresh_content(entry):
            self._surface(entry)

    def _refresh_content_and_force_unread(self, entry: MailboxEntry) -> None:
        """The FORCED surface (InboxUpdate.MARK_UNREAD_FORCED): refresh content and raise the row
        unconditionally, bypassing the content gate — for a direct ask the gate can't see (an
        @mention, an assignment, or a DECIDED mark). Forcing is the same label operation for every
        resource, so this is NOT overridden: email's Gmail gating applies only to the gated path
        above."""
        self._refresh_content(entry)
        self._surface(entry)

    @staticmethod
    def _surface(entry: MailboxEntry) -> None:
        entry.label_as_inbox()
        entry.label_as_unread()
        if entry.is_snoozed:
            entry.snoozed_until = None

    async def sync(
        self,
        *,
        event: "Event | None" = None,
        direct_recipients: list[User] | None = None,
    ) -> None:
        """Recompute mailbox rows for this resource — the one engine for all resources.

        With `event`: event-driven sync. `_update_inbox_rows_for_event` combines resolver
        reach (`resolve_for_inbox`, folding in `direct_recipients` and force-include) with
        existing-row continuity via `InboxUpdate.for_event`.

        Without `event`: state-driven content recompute (collaborator-add, membership/title
        changes, inbound email). Inbox reach comes from `resolve_for_inbox` — the inbox-reach
        method, not the bare `resolve()` primitive — so policy force-include applies here too;
        reached users get a content refresh + new-activity-gated unread bump via the resource's
        `_refresh_content_and_mark_unread`, and existing rows below reach are content-refreshed.
        """
        async with transaction() as connection:
            await self._prefetch_for_sync(connection)
            if event is not None:
                # None propagates to _update_inbox_rows_for_event, which derives direct recipients
                # from the event; an explicit list (test override) is used as-is.
                syncs = await self._update_inbox_rows_for_event(event, direct_recipients, using_db=connection)
            else:
                syncs = await self._update_inbox_rows_from_state(using_db=connection)
            syncs += await self._clear_non_collaborators(using_db=connection)

        for sync in syncs:
            await sync.broadcast()

    @abstractmethod
    async def touch(self, user: User, *, using_db: BaseDBAsyncClient | None = None) -> None: ...

    @property
    def resource_gid(self) -> GlobalID:
        return self.resource.global_id

    def entry(self, user: User) -> QuerySet[MailboxEntry]:
        return MailboxEntry.filter(
            MailboxEntry.filters.by_resource(self.resource_gid),
            MailboxEntry.filters.by_owner(user.id),
        )

    async def find_or_create_entry(
        self,
        user: User,
        organization_id: UUID,
        using_db: BaseDBAsyncClient | None = None,
    ) -> tuple[MailboxEntry, bool]:
        queryset = (
            MailboxEntry.unscoped.get_queryset()
            .filter(MailboxEntry.filters.by_resource(self.resource_gid))
            .filter(MailboxEntry.filters.by_owner(user.id))
        )
        if using_db:
            # Lock the row so concurrent row-refresh / mark_as_read paths
            # against the same (resource, user) serialize. Without this, a sync job and
            # an interleaved markRead each compute their own label changes; whichever
            # commits second wins on `labels`, even though its `update_fields` doesn't
            # include `read_at` set by the other. The result was an entry with
            # `read_at` past the latest message but `labels=[inbox, unread]`.
            #
            # NOTE: SELECT FOR UPDATE only applies inside a transaction (requires using_db).
            # All callers that need the serialization guarantee must pass a connection.
            queryset = queryset.using_db(using_db).select_for_update()
        entry = await queryset.first()
        if entry:
            return entry, False
        return MailboxEntry(
            resource_gid=self.resource_gid,
            owner_id=user.id,
            organization_id=organization_id,
            title="",
            preview="",
        ), True

    async def refresh_row_and_mark_unread(
        self, collaborating_user: User, *, using_db: BaseDBAsyncClient | None = None
    ) -> MailboxSync | None:
        """Refresh content and surface the row (inbox + unread), gated on new activity — the
        apply side of InboxUpdate.MARK_UNREAD."""
        return await self._save_for(collaborating_user, self._refresh_content_and_mark_unread, using_db=using_db)

    async def refresh_row_and_force_unread(
        self, collaborating_user: User, *, using_db: BaseDBAsyncClient | None = None
    ) -> MailboxSync | None:
        """Refresh content and surface the row unconditionally — the apply side of
        InboxUpdate.MARK_UNREAD_FORCED, where the routing layer is authoritative."""
        return await self._save_for(collaborating_user, self._refresh_content_and_force_unread, using_db=using_db)

    async def refresh_row_content(
        self, collaborating_user: User, *, using_db: BaseDBAsyncClient | None = None
    ) -> MailboxSync | None:
        """Refresh content only — never touches inbox/unread/snooze. Used for the sender's
        own message, existing-row holders below ALL, and after explicit mark read/unread."""
        return await self._save_for(collaborating_user, self._refresh_content, using_db=using_db)

    async def _save_for(
        self,
        collaborating_user: User,
        apply_to_entry: Callable[[MailboxEntry], object],
        *,
        using_db: BaseDBAsyncClient | None,
    ) -> MailboxSync | None:
        was_saved = False

        async with transaction(using_db) as connection:
            entry, _is_new = await self.find_or_create_entry(
                collaborating_user,
                self.resource.organization_id,
                using_db=connection,
            )

            if not self.resource.collaboration.can_be_accessed_by(collaborating_user):
                if not entry.is_new:
                    await entry.soft_delete(using_db=connection)
                return None

            entry.owner = collaborating_user
            apply_to_entry(entry)
            if entry.is_new or entry.is_changed:
                if entry.is_new:
                    await entry.save(using_db=connection)
                else:
                    await entry.save(update_fields=list(entry.changes.keys()), using_db=connection)

                was_saved = True

        if was_saved:
            return MailboxSync(entry_id=entry.id, user_id=collaborating_user.id)
        return None

    async def mark_as_read(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            await self._prefetch_for_sync(connection)

            # Deliberately does NOT touch the workspace Visit read-cursor: for goals/posts the
            # "new activity" / "what's new" boundary is a visit-on-open cursor, so triaging an
            # entry read/unread from the inbox does not silently move what a later open shows as
            # new. Only ChatMailboxEntry overrides this to bridge into Visit (its in-chat unread
            # divider must track the mailbox read state). Keep that split intentional.

            # Advance last_activity_at (via _refresh_content) and mark read in one save,
            # holding the find_or_create_entry row lock to serialize against a concurrent
            # SyncMailboxJob for the same message. Without both the lock and the cursor
            # advance, a mark_read that commits before the job leaves the entry unread: the
            # job's _has_new_activity still sees the message as newer than the stale
            # last_activity_at and re-applies the label (#8816).
            entry, _ = await self.find_or_create_entry(user, self.resource.organization_id, using_db=connection)
            entry.owner = user
            self._refresh_content(entry)
            entry.label_as_read()
            entry.read_at = datetime.now(UTC)
            # save(update_fields=...) on an unsaved entry is a 0-row UPDATE, not an INSERT.
            if entry.is_new:
                await entry.save(using_db=connection)
            elif entry.is_changed:
                await entry.save(update_fields=list(entry.changes.keys()), using_db=connection)

    async def mark_as_unread(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.mark_as_unread(using_db=connection)

    async def archive(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.archive(using_db=connection)

    async def unarchive(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.unarchive(using_db=connection)

    async def snooze(self, user: User, snoozed_until: datetime, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.snooze(snoozed_until, using_db=connection)

    async def unsnooze(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.unsnooze(using_db=connection)

    async def _update_inbox_rows_for_event(
        self, event: Event, direct_recipients: list[User] | None = None, *, using_db: BaseDBAsyncClient | None = None
    ) -> list[MailboxSync]:
        """Apply one event to every affected inbox row for this resource.

        Reach (who the event reaches) comes from the resolver; row continuity
        (who already has a row) comes from `existing_owner_ids_for_resource`;
        `InboxUpdate.for_event` combines them into one decision per person. Non-collaborators
        with stale rows are left to `_clear_non_collaborators`.

        Caller contract: `self.resource.workspace.collaborators` (with `.user`) must be
        prefetched before this runs — it's read to fold below-ALL collaborators into the
        candidate set. Both callers (chat/post `sync`) prefetch `workspace__collaborators__user`.
        """
        workspace = self.resource.workspace
        resolver = SubscriberResolver(workspace=workspace, using_db=using_db)
        # Reach and direct-recipient derivation both live on the resolver. Production passes no
        # direct_recipients so the engine derives them here; tests inject an explicit list (or [])
        # to exercise reach scenarios without building Mention/assignment fixtures.
        if direct_recipients is None:
            direct_recipients = await resolver.direct_recipients_for(event)
        reached = await resolver.resolve_for_inbox(event, direct_recipients=direct_recipients)
        reached_ids = {user.id for user in reached}
        row_owner_ids = await MailboxEntry.existing_owner_ids_for_resource(self.resource_gid, using_db=using_db)
        # Who this event personally targets (@mentions + the assignee of an assignment).
        # InboxUpdate.for_event combines this with the row/sender facts: a new target surfaces
        # on an edit, and a self-target or a direct ask surfaces past the content gate.
        direct_recipient_ids = {user.id for user in direct_recipients}

        # Everyone the event could touch. `reached` is authoritative for who the event
        # surfaces to, so it leads — it already folds in direct recipients and org
        # accessors who aren't collaborators (org-wide posts reaching Broadcasts/ALL
        # members). Collaborators below ALL are added on top so their existing rows
        # still get a content refresh. InboxUpdate.for_event decides each one's fate — including
        # IGNORE for those it neither reaches nor who already has a row.
        candidates = {user.id: user for user in reached}
        for collaborator in workspace.collaborators:
            if collaborator.user:
                candidates.setdefault(collaborator.user.id, collaborator.user)

        syncs: list[MailboxSync] = []
        for user in candidates.values():
            update = InboxUpdate.for_event(
                action=event.action,
                event_reaches_user=user.id in reached_ids,
                user_is_sender=user.id == event.creator_id,
                user_has_existing_row=user.id in row_owner_ids,
                user_is_direct_recipient=user.id in direct_recipient_ids,
            )
            match update:
                case InboxUpdate.MARK_UNREAD:
                    result = await self.refresh_row_and_mark_unread(user, using_db=using_db)
                case InboxUpdate.MARK_UNREAD_FORCED:
                    result = await self.refresh_row_and_force_unread(user, using_db=using_db)
                case InboxUpdate.REFRESH_CONTENT:
                    result = await self.refresh_row_content(user, using_db=using_db)
                case InboxUpdate.IGNORE:
                    result = None
                case _:
                    assert_never(update)  # exhaustive over InboxUpdate; a new variant fails type-check
            if result:
                syncs.append(result)
        return syncs

    async def _update_inbox_rows_from_state(self, *, using_db: BaseDBAsyncClient | None = None) -> list[MailboxSync]:
        """Recompute rows from the resource's current state, with no triggering event.

        Reached subscribers (`resolve_for_inbox` with no event — ALL-level plus policy
        force-include, not the bare `resolve()` primitive) get a content refresh and a
        new-activity-gated unread bump; existing rows below reach are content-refreshed for
        continuity. Used by collaborator-add, membership/title changes, and inbound email."""
        resolver = SubscriberResolver(workspace=self.resource.workspace, using_db=using_db)
        reached_ids: set[UUID] = set()
        syncs: list[MailboxSync] = []
        for user in await resolver.resolve_for_inbox(direct_recipients=[]):
            reached_ids.add(user.id)
            if result := await self.refresh_row_and_mark_unread(user, using_db=using_db):
                syncs.append(result)
        syncs.extend(await self._refresh_existing_rows(exclude_user_ids=reached_ids, using_db=using_db))
        return syncs

    async def _refresh_existing_rows(
        self, *, exclude_user_ids: set[UUID], using_db: BaseDBAsyncClient | None = None
    ) -> list[MailboxSync]:
        """Content-only refresh for collaborators who already have a row but aren't in
        `exclude_user_ids`. Keeps the Slack model on state-driven recomputes: an existing
        row tracks the resource's content even for users below ALL (mute/archive only
        gate unread and inbox presence). Non-collaborators are left to
        `_clear_non_collaborators`."""
        row_owner_ids = await MailboxEntry.existing_owner_ids_for_resource(self.resource_gid, using_db=using_db)
        collaborators_by_id = {c.user.id: c.user for c in self.resource.workspace.collaborators if c.user}
        results: list[MailboxSync] = []
        for owner_id in row_owner_ids - exclude_user_ids:
            user = collaborators_by_id.get(owner_id)
            if user and (result := await self.refresh_row_content(user, using_db=using_db)):
                results.append(result)
        return results

    async def _clear_non_collaborators(self, using_db: BaseDBAsyncClient | None = None) -> list[MailboxSync]:
        results: list[MailboxSync] = []

        async with transaction(using_db) as connection:
            entries = (
                await MailboxEntry.filter(MailboxEntry.filters.by_resource(self.resource_gid))
                .prefetch_related("owner")
                .using_db(connection)
            )

            for entry in entries:
                if not self.resource.collaboration.can_be_accessed_by(entry.owner):
                    await entry.soft_delete(using_db=connection)
                    results.append(MailboxSync(entry_id=entry.id, user_id=entry.owner_id))

        return results


mailbox_entry_registry: dict[str, type[BaseMailboxEntry]] = {}


class MailboxFilters:
    def __init__(self, user: User):
        self.user = user

    @staticmethod
    def _combine(filters: list[Q | None]) -> Q:
        combined = Q()
        has_filter = False
        for q in filters:
            if q is not None:
                combined |= q
                has_filter = True
        if not has_filter:
            return Q(pk__in=[])
        return combined

    @property
    def inbox(self) -> QuerySet[MailboxEntry]:
        return self._query(self._combine([cls.entry_filters.inbox() for cls in mailbox_entry_registry.values()]))

    @property
    def archived(self) -> QuerySet[MailboxEntry]:
        return self._query(self._combine([cls.entry_filters.archived() for cls in mailbox_entry_registry.values()]))

    @property
    def sent(self) -> QuerySet[MailboxEntry]:
        return self._query(self._combine([cls.entry_filters.sent() for cls in mailbox_entry_registry.values()]))

    @property
    def drafts(self) -> QuerySet[MailboxEntry]:
        return self._query(self._combine([cls.entry_filters.draft() for cls in mailbox_entry_registry.values()]))

    @property
    def assigned_to_me(self) -> QuerySet[MailboxEntry]:
        return self._query(
            self._combine([cls.entry_filters.inbox() for cls in mailbox_entry_registry.values()]),
            MailboxEntry.filters.by_assignee(self.user.id),
        )

    @property
    def snoozed(self) -> QuerySet[MailboxEntry]:
        return self._query(self._combine([cls.entry_filters.snoozed() for cls in mailbox_entry_registry.values()]))

    @property
    def unread(self) -> QuerySet[MailboxEntry]:
        return self._query(
            self._combine([cls.entry_filters.inbox() for cls in mailbox_entry_registry.values()]),
            MailboxEntry.filters.unread,
        )

    def for_view(self, view: MailboxViewName) -> QuerySet[MailboxEntry]:
        match view:
            case MailboxViewName.INBOX:
                return self.inbox
            case MailboxViewName.UNREAD:
                return self.unread
            case MailboxViewName.ARCHIVED:
                return self.archived
            case MailboxViewName.SENT:
                return self.sent
            case MailboxViewName.DRAFTS:
                return self.drafts
            case MailboxViewName.ASSIGNED_TO_ME:
                return self.assigned_to_me
            case MailboxViewName.SNOOZED:
                return self.snoozed
            case _:
                raise ValueError(f"Unknown mailbox view: {view!r}")

    def _query(self, *filters: Q) -> QuerySet[MailboxEntry]:
        # last_event is NULL on every row until the follow-up PRs in this stack start writing it;
        # the prefetch ships with the column so the reader lands atomically (no-op while unwritten).
        return MailboxEntry.filter(
            *filters,
            MailboxEntry.filters.by_owner(self.user.id),
        ).prefetch_related("owner", "last_comment_author__avatar_file", "last_event__creator__avatar_file")


@dataclass
class Mailbox:
    user: User

    @classmethod
    async def sync(
        cls,
        resource: RecordModel,
        *,
        event: "Event | None" = None,
        direct_recipients: list[User] | None = None,
    ) -> None:
        """Recompute mailbox rows for `resource`.

        Without `event`: state-driven recompute. Iterates the resource's
        current effective subscribers (Chat/Post) or all collaborators
        (EmailThread). Used by collaborator-add hooks, chat router
        membership changes, and the email client when a thread mutates.

        With `event`: event-driven sync. The per-resource implementation calls
        `_update_inbox_rows_for_event`, which combines resolver reach (`resolve_for_inbox`,
        folding in `direct_recipients` and DM force-include) with existing-row
        continuity via `InboxUpdate.for_event`. Used by `SyncMailboxJob`.
        """
        if entry := mailbox_entry_for(resource):
            await entry.sync(event=event, direct_recipients=direct_recipients)

    @property
    def filters(self) -> MailboxFilters:
        return MailboxFilters(self.user)

    def entry(self, resource: RecordModel) -> QuerySet[MailboxEntry]:
        mbe = mailbox_entry_for(resource)
        if not mbe:
            return MailboxEntry.filter(pk__in=[])
        return mbe.entry(self.user)

    async def touch(self, resource: RecordModel, *, using_db: BaseDBAsyncClient | None = None) -> None:
        if entry := mailbox_entry_for(resource):
            await entry.touch(self.user, using_db=using_db)

    async def mark_as_read(self, resource: RecordModel, using_db: BaseDBAsyncClient | None = None) -> None:
        if entry := mailbox_entry_for(resource):
            await entry.mark_as_read(self.user, using_db=using_db)

    async def mark_as_unread(self, resource: RecordModel, using_db: BaseDBAsyncClient | None = None) -> None:
        if entry := mailbox_entry_for(resource):
            await entry.mark_as_unread(self.user, using_db=using_db)

    async def archive(self, resource: RecordModel, using_db: BaseDBAsyncClient | None = None) -> None:
        if entry := mailbox_entry_for(resource):
            await entry.archive(self.user, using_db=using_db)

    async def unarchive(self, resource: RecordModel, using_db: BaseDBAsyncClient | None = None) -> None:
        if entry := mailbox_entry_for(resource):
            await entry.unarchive(self.user, using_db=using_db)

    async def snooze(
        self, resource: RecordModel, snoozed_until: datetime, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        if entry := mailbox_entry_for(resource):
            await entry.snooze(self.user, snoozed_until, using_db=using_db)

    async def unsnooze(self, resource: RecordModel, using_db: BaseDBAsyncClient | None = None) -> None:
        if entry := mailbox_entry_for(resource):
            await entry.unsnooze(self.user, using_db=using_db)

    @classmethod
    async def delete(cls, resource: RecordModel, using_db: BaseDBAsyncClient | None = None) -> None:
        """Soft-delete all MailboxEntries for a resource and broadcast to affected users."""
        async with transaction(using_db) as connection:
            entries = await (
                MailboxEntry.filter(MailboxEntry.filters.by_resource(resource.global_id)).using_db(connection).all()
            )
            syncs: list[MailboxSync] = []
            for entry in entries:
                await entry.soft_delete(using_db=connection)
                syncs.append(MailboxSync(entry_id=entry.id, user_id=entry.owner_id))

        for sync in syncs:
            await sync.broadcast()


def mailbox_entry_for(resource: RecordModel) -> BaseMailboxEntry | None:
    cls = mailbox_entry_registry.get(type(resource).record_type)
    if not cls:
        logger.warning("No mailbox entry type registered for %s", type(resource).__name__)
        return None
    return cls.from_resource(resource)


MAILBOX_VIEW_EXPIRY = timedelta(hours=1)

MAILBOX_VIEW_TEMPLATES: dict[str, dict[str, Any]] = {
    "urgent_important": {
        "title": "Urgent/Important",
        "view_request": (
            "Organize my inbox by importance and urgency. Create sections like: "
            "urgent and important (need immediate action), important but not urgent "
            "(schedule time for these), urgent but not important (delegate or quick response), "
            "and neither (archive candidates)."
        ),
    },
    "by_goals": {"title": "By Goals", "requires_goals": True},
    # Free-text custom sort: one flat, score-ordered list rather than grouped sections.
    "priority": {
        "title": "Priority",
        "view_request": "Rank my inbox so the items needing my attention soonest come first.",
        "layout": MailboxViewLayout.RANKED,
    },
    # Singular "by_goal" ranks the inbox against ONE chosen goal (goal_id carried on the
    # identifier). Distinct from the plural grouped "by_goals" template above.
    "by_goal": {
        "title": "By goal",
        "requires_goals": True,
        "layout": MailboxViewLayout.RANKED,
    },
}


def _template_targets_single_goal(template_name: str) -> bool:
    # Only a ranked goal sort (by_goal) carries a goal_id; the plural grouped "by_goals" view ranges
    # over all of a user's goals and never uses one. Keying off metadata rather than the literal
    # name keeps the goal_id round-trip honest if more goal-targeted templates appear.
    template = MAILBOX_VIEW_TEMPLATES.get(template_name)
    if not template:
        return False
    return bool(template.get("requires_goals")) and template.get("layout") == MailboxViewLayout.RANKED


@dataclass
class MailboxViewCacheData:
    sections: list[dict]
    cached_at: datetime
    # True while generation is still streaming and only a partial ordering has been written. The
    # index endpoint surfaces this so a refresh mid-sort renders the partial like a cache hit but
    # keeps the spinner + channel subscription, instead of blanking until generation finishes.
    generating: bool = False

    @property
    def entry_ids(self) -> list[str]:
        ids = []
        for section in self.sections:
            ids.extend(section.get("mailbox_entry_ids", []))
        return ids

    def to_dict(self) -> dict:
        return {"sections": self.sections, "cached_at": self.cached_at.isoformat(), "generating": self.generating}

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            sections=data.get("sections", []),
            cached_at=datetime.fromisoformat(data["cached_at"]),
            generating=bool(data.get("generating", False)),
        )


class MailboxViewFilters:
    @classmethod
    def by_user(cls, user_id: UUID) -> Q:
        return Q(user_id=user_id)

    @classmethod
    def by_organization(cls, organization_id: UUID) -> Q:
        return Q(organization_id=organization_id)


class MailboxView(RecordModel):
    view_request = fields.TextField()
    title = fields.TextField()
    # GROUPED views render LLM sections; RANKED views (custom sorts) render a single
    # score-ordered flat list. Defaults to GROUPED so existing rows migrate forward unchanged.
    layout = fields.CharEnumField(MailboxViewLayout, default=MailboxViewLayout.GROUPED, max_length=16)
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    user_id: Annotated[UUID, "foreign key to user"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    filters = MailboxViewFilters()

    class Meta:
        ordering = ["-created_at"]
        indexes = (("user_id",), ("organization_id",))

    @property
    def cache_key(self) -> str:
        return f"mailbox_view_{self.user_id}_{self.id}"


@dataclass
class MailboxViewCache:
    view: MailboxView

    @property
    def key(self) -> str:
        return self.view.cache_key

    @property
    def expiry(self) -> timedelta:
        return MAILBOX_VIEW_EXPIRY

    async def read(self) -> MailboxViewCacheData | None:
        data = await cache.read_json(self.key)
        if not data or "sections" not in data or "cached_at" not in data:
            return None
        try:
            return MailboxViewCacheData.from_dict(data)
        except (KeyError, ValueError):
            return None

    async def write(
        self, sections: list[dict], *, generating: bool = False, cached_at: datetime | None = None
    ) -> MailboxViewCacheData:
        # Partial writes pass a stable `cached_at` (generation start) so the "new messages since"
        # baseline doesn't drift on every throttled write; the final write stamps fresh now.
        cache_data = MailboxViewCacheData(
            sections=sections,
            cached_at=cached_at or datetime.now(UTC),
            generating=generating,
        )
        await cache.write_json(self.key, cache_data.to_dict(), self.expiry)
        return cache_data

    async def delete(self) -> None:
        await cache.delete(self.key)

    async def exists(self) -> bool:
        return await cache.exists(self.key)

    @staticmethod
    async def count_new_entries(user: User, since: datetime, exclude_entry_ids: set[str] | None = None) -> int:
        mailbox = Mailbox(user=user)
        queryset = mailbox.filters.inbox.filter(last_activity_at__gt=since)

        if exclude_entry_ids:
            uuid_ids = [uid for eid in exclude_entry_ids if (uid := parse_uuid(eid))]
            if uuid_ids:
                queryset = queryset.exclude(id__in=uuid_ids)

        return await queryset.count()


@dataclass
class MailboxViewIdentifier:
    template_name: str | None = None
    view_id: UUID | None = None
    # The single goal a "by_goal" ranked sort targets. It MUST round-trip through the opaque
    # wire string (see `to_channel_id`/`from_string`/`cache_key_for_user`), not just live on the
    # dataclass — two goals on the same template would otherwise collide on one channel + cache.
    goal_id: UUID | None = None

    @classmethod
    def from_string(cls, value: str) -> Self | None:
        if value.startswith("template:"):
            # Wire format is "template:<name>" or, for goal-targeted sorts, "template:<name>:<uuid>".
            remainder = value[len("template:") :]
            template_name, _, goal_part = remainder.partition(":")
            if template_name not in MAILBOX_VIEW_TEMPLATES:
                return None
            goal_id = parse_uuid(goal_part) if goal_part else None
            if goal_part and goal_id is None:
                return None
            # A goal_id only belongs to a goal-targeted template; drop a stray suffix on any other
            # so it can't fragment that template's channel + cache with a meaningless parameter.
            if not _template_targets_single_goal(template_name):
                goal_id = None
            return cls(template_name=template_name, goal_id=goal_id)
        view_id = parse_uuid(value)
        return cls(view_id=view_id) if view_id else None

    @classmethod
    def for_template(cls, name: str, goal_id: UUID | None = None) -> Self | None:
        if name not in MAILBOX_VIEW_TEMPLATES:
            return None
        if not _template_targets_single_goal(name):
            goal_id = None
        return cls(template_name=name, goal_id=goal_id)

    @classmethod
    def for_view(cls, view_id: UUID) -> Self:
        return cls(view_id=view_id)

    def is_template(self) -> bool:
        return self.template_name is not None

    def is_view(self) -> bool:
        return self.view_id is not None

    def to_channel_id(self) -> str:
        if self.template_name:
            if self.goal_id:
                return f"template:{self.template_name}:{self.goal_id}"
            return f"template:{self.template_name}"
        if self.view_id:
            return str(self.view_id)
        raise ValueError("Invalid identifier: neither template nor view_id set")

    @property
    def title(self) -> str | None:
        if self.template_name:
            return MAILBOX_VIEW_TEMPLATES[self.template_name]["title"]
        return None

    @property
    def view_request(self) -> str | None:
        if self.template_name:
            return MAILBOX_VIEW_TEMPLATES[self.template_name].get("view_request")
        return None

    @property
    def requires_goals(self) -> bool:
        if self.template_name:
            return MAILBOX_VIEW_TEMPLATES[self.template_name].get("requires_goals", False)
        return False

    @property
    def targets_single_goal(self) -> bool:
        return self.template_name is not None and _template_targets_single_goal(self.template_name)

    @property
    def layout(self) -> MailboxViewLayout:
        if self.template_name:
            return MAILBOX_VIEW_TEMPLATES[self.template_name].get("layout", MailboxViewLayout.GROUPED)
        return MailboxViewLayout.GROUPED

    def cache_key_for_user(self, user_id: UUID) -> str:
        if self.template_name:
            if self.goal_id:
                return f"mailbox_view_template_{user_id}_{self.template_name}_{self.goal_id}"
            return f"mailbox_view_template_{user_id}_{self.template_name}"
        raise ValueError("Use MailboxViewCache for saved views")

    async def read_cache(self, user_id: UUID) -> MailboxViewCacheData | None:
        if not self.template_name:
            raise ValueError("Use MailboxViewCache for saved views")

        cache_key = self.cache_key_for_user(user_id)
        cached = await cache.read_json(cache_key)
        if cached and "sections" in cached and "cached_at" in cached:
            try:
                return MailboxViewCacheData.from_dict(cached)
            except (KeyError, ValueError):
                pass
        return None

    async def write_cache(
        self, user_id: UUID, sections: list[dict], *, generating: bool = False, cached_at: datetime | None = None
    ) -> None:
        if not self.template_name:
            raise ValueError("Use MailboxViewCache for saved views")

        cache_key = self.cache_key_for_user(user_id)
        cache_data = MailboxViewCacheData(
            sections=sections, cached_at=cached_at or datetime.now(UTC), generating=generating
        )
        await cache.write_json(cache_key, cache_data.to_dict(), MAILBOX_VIEW_EXPIRY)

    async def delete_cache(self, user_id: UUID) -> None:
        if not self.template_name:
            raise ValueError("Use MailboxViewCache for saved views")
        await cache.delete(self.cache_key_for_user(user_id))


@dataclass
class MailboxViewSource:
    """Unified handle for either a saved MailboxView or a template identifier.

    Resolves the identifier to its backing row (or template metadata) once, then
    exposes a uniform `view_request` / `requires_goals` / `write_cache` interface
    so callers don't have to fork on `MailboxViewIdentifier.is_template()`.
    """

    user: User
    identifier: MailboxViewIdentifier
    view: MailboxView | None

    @classmethod
    async def resolve(cls, identifier: MailboxViewIdentifier, user: User) -> Self | None:
        if identifier.is_template():
            return cls(user=user, identifier=identifier, view=None)
        if identifier.is_view():
            view = await MailboxView.get_or_none(
                id=identifier.view_id,
                user_id=user.id,
                organization_id=user.organization_id,
            )
            if not view:
                return None
            return cls(user=user, identifier=identifier, view=view)
        return None

    @property
    def view_request(self) -> str | None:
        if self.view:
            return self.view.view_request
        return self.identifier.view_request

    @property
    def requires_goals(self) -> bool:
        return self.identifier.requires_goals

    @property
    def layout(self) -> MailboxViewLayout:
        if self.view:
            return self.view.layout
        return self.identifier.layout

    async def write_cache(
        self, sections: list[dict], *, generating: bool = False, cached_at: datetime | None = None
    ) -> None:
        if self.view:
            await MailboxViewCache(self.view).write(sections, generating=generating, cached_at=cached_at)
        else:
            await self.identifier.write_cache(self.user.id, sections, generating=generating, cached_at=cached_at)

    async def read_cache(self) -> MailboxViewCacheData | None:
        if self.view:
            return await MailboxViewCache(self.view).read()
        return await self.identifier.read_cache(self.user.id)

    async def clear_cache(self) -> None:
        if self.view:
            await MailboxViewCache(self.view).delete()
        else:
            await self.identifier.delete_cache(self.user.id)
