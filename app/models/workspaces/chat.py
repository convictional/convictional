import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Annotated, ClassVar, Self, cast
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields
from tortoise.exceptions import IntegrityError
from tortoise.expressions import Q
from tortoise.functions import Count
from tortoise.signals import post_delete, post_save

from app.models.accounts import Group, GroupMember, User
from app.models.collaboration.mailbox import (
    BaseMailboxEntry,
    BaseMailboxEntryFilters,
    Mailbox,
    MailboxEntry,
    MailboxSync,
)
from app.models.collaboration.workspace import (
    Collaborator,
    CommentMixin,
    Event,
    NotificationPolicy,
    Visit,
    WorkspaceMixin,
    WorkspaceMixinFilters,
    delete_decision_for_comment,
)
from config.enums import ChatType, CollaboratorStatus, EmailDelivery, EventAction, SubscriptionLevel
from infra.db import RecordModel, SoftDeleteableMixin, transaction
from infra.messaging import Topic
from lib.markdown import markdown_to_plain_text
from lib.strings import truncate

MAX_CHAT_COLLABORATORS = 50


@dataclass
class ChatNotificationPolicy(NotificationPolicy):
    chat: "Chat"

    default_subscription_level: ClassVar[SubscriptionLevel] = SubscriptionLevel.ALL

    def force_include_for_inbox(self, action: EventAction | None = None) -> bool:
        # A DM always sits in both participants' inboxes regardless of level — a
        # 1:1 has no meaningful "relevant-only", so the level can't hide it. This holds for
        # every event on the DM (not just its creation), so `action` is ignored.
        return self.chat.type.is_dm

    @property
    def force_include_all_collaborators_for_push(self) -> bool:
        # ...and a DM always pushes, for the same reason. (A multi-person direct
        # chat instead pushes its subscribers — see notify_subscriber_push — so
        # muting it can silence push; a DM can't be muted out.)
        return self.chat.type.is_dm

    @property
    def notify_subscriber_push(self) -> bool:
        # A multi-person direct chat is a DM with more people: ordinary messages
        # push its subscribers (members at level ALL, the default), and muting it
        # drops a member below ALL and silences their push. Group chats are
        # excluded — a channel message reaches the inbox but doesn't push.
        return self.chat.type.is_multi

    @property
    def notify_mention_push(self) -> bool:
        # Chat @mentions name you specifically, so they push (unlike post/doc/goal
        # @mentions, which only reach the inbox).
        return True


class ChatFilters(WorkspaceMixinFilters):
    @classmethod
    def by_collaborator(cls, user_id: UUID) -> Q:
        return Q(workspace__collaborators__user_id=user_id)

    @classmethod
    def by_ids(cls, chat_ids: list[UUID]) -> Q:
        return Q(id__in=chat_ids)

    @classmethod
    def direct_with_collaborator(cls, user_id: UUID) -> Q:
        return Q(group_id__isnull=True, workspace__collaborators__user_id=user_id)

    @classmethod
    def active_for_user(cls, user_id: UUID) -> Q:
        return cls.by_collaborated_workspaces(user_id) & Q(last_message_id__isnull=False)


class Chat(WorkspaceMixin, RecordModel):
    # DMs have no title; resolved_title() derives one from collaborator names at render time
    title: str | None = fields.TextField(null=True)  # type: ignore[assignment]
    group: fields.ForeignKeyNullableRelation[Group] = fields.ForeignKeyField(
        "convictional.Group", related_name="chat", null=True
    )
    group_id: Annotated[UUID | None, "foreign key to group"]
    # db_constraint=False because a real FK here closes a chat <-> chatmessage cycle, and
    # Tortoise's schema generator emits FKs inline in CREATE TABLE, so it cannot order a cycle
    # at all (`Can't create schema due to cyclic fk references`) -- no migration could be
    # generated. The pointer is a denormalized cache maintained by sync_last_message, which every
    # message create/delete path calls, and messages are soft-deleted, so ON DELETE SET NULL was
    # never the mechanism keeping it consistent.
    last_message: fields.ForeignKeyNullableRelation["ChatMessage"] = fields.ForeignKeyField(
        "convictional.ChatMessage", related_name="+", null=True, on_delete=fields.SET_NULL, db_constraint=False
    )
    last_message_id: Annotated[UUID | None, "foreign key to chat_message"]
    last_message_at: datetime | None = fields.DatetimeField(null=True)
    collaborators_hash = fields.CharField(max_length=64, null=True)
    messages: fields.ReverseRelation["ChatMessage"]
    filters = ChatFilters()
    email_delivery = EmailDelivery.SKIP

    class Meta:
        ordering = ["-created_at"]
        indexes = (("organization_id",), ("organization_id", "last_message_at"))
        unique_together = (("group_id",),)

    @property
    def collaborator_users(self) -> list[User]:
        return [c.user for c in self.workspace.collaborators if c.user]

    # Fold the last message on top of the base event-log signal: not every message path records a
    # workspace event, so the base alone could miss message activity; comments/decisions still
    # count via the base.
    @property
    def indexing_activity_at(self) -> datetime:
        activity = super().indexing_activity_at
        return max(activity, self.last_message_at) if self.last_message_at else activity

    # Chat membership has its own invariants (DM size, group lock,
    # MAX_CHAT_COLLABORATORS, collaborators_hash). @mentions resolve to
    # existing members only; explicit add_collaborator is the only path
    # that mutates membership.
    mentions_can_add_collaborators = False

    @property
    def notification_policy(self) -> ChatNotificationPolicy:
        return ChatNotificationPolicy(workspace=self.workspace, chat=self)

    # DMs and group chats are expected to ping by default (see
    # ChatNotificationPolicy.default_subscription_level); every other resource
    # type inherits the base NotificationPolicy default (RELEVANT_ONLY).
    @classmethod
    def notification_policy_class(cls) -> type[ChatNotificationPolicy]:
        return ChatNotificationPolicy

    @property
    def type(self) -> ChatType:
        if self.group_id:
            return ChatType.GROUP
        if len(self.workspace.collaborators) == 1:
            return ChatType.SELF
        if len(self.workspace.collaborators) > 2:
            return ChatType.MULTI
        return ChatType.DM

    @property
    def supports_mentions(self) -> bool:
        return self.type.is_multi or self.type.is_group

    @classmethod
    async def find_by_hash(
        cls,
        user_ids: list[UUID],
        organization_id: UUID,
        *,
        exclude_id: UUID | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> "Chat | None":
        collaborators_hash = cls.compute_collaborators_hash(user_ids)
        qs = cls.filter(
            organization_id=organization_id,
            group_id__isnull=True,
            collaborators_hash=collaborators_hash,
        ).using_db(using_db)
        if exclude_id is not None:
            qs = qs.exclude(id=exclude_id)
        return await qs.first()

    @classmethod
    async def find_existing(
        cls, user_ids: list[UUID], organization_id: UUID, *, using_db: BaseDBAsyncClient | None = None
    ) -> "Chat | None":
        multi = await cls.find_by_hash(user_ids, organization_id, using_db=using_db)
        if multi:
            return multi

        group = await cls.find_matching_group(user_ids, organization_id, using_db=using_db)
        if group:
            return await cls.filter(group_id=group.id).using_db(using_db).first()

        return None

    @classmethod
    async def active_partners_for(cls, user: User) -> tuple[set[UUID], set[UUID]]:
        # Returns (other_user_ids from active DMs, group_ids from active group chats) for chats
        # `user` participates in that have at least one message. "Active" means the chat has
        # been used — empty chats with no messages don't count as a partner.
        rows = await cls.filter(
            cls.filters.by_organization(user.organization_id),
            cls.filters.nondeleted,
            cls.filters.active_for_user(user.id),
        ).values_list("workspace_id", "group_id")

        groups_with_chats: set[UUID] = set()
        candidate_workspace_ids: list[UUID] = []
        for workspace_id, group_id in cast(list[tuple[UUID, UUID | None]], rows):
            if group_id:
                groups_with_chats.add(group_id)
            else:
                candidate_workspace_ids.append(workspace_id)

        chat_user_ids: set[UUID] = set()
        if candidate_workspace_ids:
            counts = await (
                Collaborator.filter(workspace_id__in=candidate_workspace_ids)
                .annotate(collaborator_count=Count("id"))
                .group_by("workspace_id")
                .values("workspace_id", "collaborator_count")
            )
            two_collab_workspace_ids = [row["workspace_id"] for row in counts if row["collaborator_count"] == 2]
            if two_collab_workspace_ids:
                other_user_ids = await (
                    Collaborator.filter(workspace_id__in=two_collab_workspace_ids)
                    .exclude(user_id=user.id)
                    .values_list("user_id", flat=True)
                )
                chat_user_ids = set(cast(list[UUID], other_user_ids))

        return chat_user_ids, groups_with_chats

    @classmethod
    async def find_matching_group(
        cls, user_ids: list[UUID], organization_id: UUID, *, using_db: BaseDBAsyncClient | None = None
    ) -> "Group | None":
        candidate_group_ids = cast(
            list[UUID],
            await Group.filter(organization_id=organization_id)
            .annotate(member_count=Count("members"))
            .filter(member_count=len(user_ids))
            .using_db(using_db)
            .values_list("id", flat=True),
        )
        if not candidate_group_ids:
            return None

        rows = await (
            GroupMember.filter(group_id__in=candidate_group_ids, user_id__in=user_ids)
            .annotate(match_count=Count("id"))
            .group_by("group_id")
            .using_db(using_db)
            .values("group_id", "match_count")
        )
        for row in rows:
            if row["match_count"] == len(user_ids):
                return await Group.get_or_none(id=row["group_id"], organization_id=organization_id, using_db=using_db)

        return None

    @classmethod
    async def _find_or_create_by_user_ids(
        cls, current_user: User, user_ids: list[UUID], *, using_db: BaseDBAsyncClient | None = None
    ) -> tuple["Chat", bool]:
        try:
            async with transaction(using_db) as connection:
                existing = await cls.find_by_hash(user_ids, current_user.organization_id, using_db=connection)
                if existing:
                    return existing, False

                collaborators_hash = cls.compute_collaborators_hash(user_ids)
                chat = await cls.create(
                    organization_id=current_user.organization_id,
                    creator_id=current_user.id,
                    collaborators_hash=collaborators_hash,
                    using_db=connection,
                )
                await cls.upsert_collaborators(chat.workspace_id, user_ids, current_user.id, using_db=connection)
                return chat, True
        except IntegrityError:
            existing = await cls.find_by_hash(user_ids, current_user.organization_id)
            if existing is None:
                raise
            return existing, False

    @classmethod
    async def find_or_create_multi(
        cls, current_user: User, recipients: list[User], *, using_db: BaseDBAsyncClient | None = None
    ) -> tuple["Chat", bool]:
        user_ids = [current_user.id] + [r.id for r in recipients]
        return await cls._find_or_create_by_user_ids(current_user, user_ids, using_db=using_db)

    @classmethod
    async def find_or_create_direct(
        cls, current_user: User, recipient: User, *, using_db: BaseDBAsyncClient | None = None
    ) -> tuple["Chat", bool]:
        user_ids = [current_user.id, recipient.id]
        return await cls._find_or_create_by_user_ids(current_user, user_ids, using_db=using_db)

    @classmethod
    async def find_or_create_self(
        cls, current_user: User, *, using_db: BaseDBAsyncClient | None = None
    ) -> tuple["Chat", bool]:
        return await cls._find_or_create_by_user_ids(current_user, [current_user.id], using_db=using_db)

    @classmethod
    async def find_or_create_for_group(
        cls, group: Group, *, creator_user_id: UUID | None = None, using_db: BaseDBAsyncClient | None = None
    ) -> tuple["Chat", bool]:
        async with transaction(using_db) as connection:
            if creator_user_id is None:
                first_group_member = (
                    await GroupMember.filter(group_id=group.id).using_db(connection).order_by("created_at").first()
                )
                if first_group_member:
                    creator_user_id = first_group_member.user_id

            chat, created = await cls.get_or_create(
                group_id=group.id,
                defaults={
                    "organization_id": group.organization_id,
                    "creator_id": creator_user_id,
                    "title": group.name,
                },
                using_db=connection,
            )
            if not created:
                return chat, False

            group_member_user_ids = cast(
                list[UUID],
                await GroupMember.filter(group_id=group.id).using_db(connection).values_list("user_id", flat=True),
            )
            await cls.upsert_collaborators(
                chat.workspace_id, group_member_user_ids, creator_user_id, using_db=connection
            )

            return chat, True

    @staticmethod
    async def upsert_collaborators(
        workspace_id: UUID,
        user_ids: list[UUID],
        added_by_id: UUID | None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        # Atomic insert-or-skip. Status transitions are owned by explicit workspace-collab
        # flows, not dual-write.
        async with transaction(using_db) as connection:
            await Collaborator.bulk_create(
                [
                    Collaborator(
                        workspace_id=workspace_id,
                        user_id=uid,
                        added_by_id=added_by_id,
                        status=CollaboratorStatus.APPROVED,
                    )
                    for uid in user_ids
                ],
                ignore_conflicts=True,
                using_db=connection,
            )

    @staticmethod
    async def delete_collaborator(
        workspace_id: UUID, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        async with transaction(using_db) as connection:
            await (
                Collaborator.unscoped.get_queryset()
                .filter(workspace_id=workspace_id, user_id=user_id)
                .using_db(connection)
                .delete()
            )

    @staticmethod
    def compute_collaborators_hash(user_ids: list[UUID]) -> str:
        sorted_ids = sorted(str(uid) for uid in user_ids)
        return hashlib.sha256(",".join(sorted_ids).encode()).hexdigest()

    @classmethod
    async def sync_last_message(
        cls,
        chat_id: UUID,
        *,
        latest_message: "ChatMessage | None" = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        latest = latest_message or (
            await ChatMessage.filter(chat_id=chat_id).using_db(using_db).order_by("-created_at").first()
        )
        await (
            cls.filter(id=chat_id)
            .using_db(using_db)
            .update(
                last_message_id=latest.id if latest else None,
                last_message_at=latest.created_at if latest else None,
            )
        )

    def resolved_title(self, viewer_id: UUID | None) -> str:
        if self.title:
            return self.title
        if self.type.is_self:
            return "Note to self"
        users = [c.user for c in self.workspace.collaborators if c.user and c.user_id != viewer_id]
        names = sorted(u.display_name for u in users)
        if len(names) == 1:
            return names[0]
        if self.type.is_dm and len(names) == 2:
            return f"{names[0]} and {names[1]}"
        return ", ".join(names) or "Chat"

    def last_message_preview(self, max_length: int | None = None) -> str | None:
        # Requires last_message__user to be prefetched.
        if not isinstance(self.last_message, ChatMessage):
            return None
        plain = markdown_to_plain_text(self.last_message.content)
        body = plain or "Sent an attachment"
        preview = f"{self.last_message.user.display_name}: {body}"
        return truncate(preview, max_length) if max_length is not None else preview

    async def rename(self, name: str | None, current_user: User) -> None:
        if not self.type.is_multi:
            raise ValueError("Only multi chats can be renamed.")

        # None or "" clears the title. Whitespace-only is rejected so users don't
        # silently lose their title on a fat-fingered spacebar press.
        if name is None or name == "":
            normalized: str | None = None
        else:
            normalized = name.strip()
            if not normalized:
                raise ValueError("Name cannot be blank.")

        # A no-op rename must not record a CHAT_RENAMED event — otherwise it flips every
        # collaborator's inbox preview to an activity line for a change that didn't happen.
        if normalized == self.title:
            return

        if normalized and await self._title_conflicts(normalized, current_user):
            raise ValueError("A group or chat with that name already exists.")

        # Save before recording so recordable.changes is clean and the explicit title survives
        # (Workspace.record folds recordable.changes into details on exit) — mirrors add_collaborator.
        async with transaction() as connection:
            self.title = normalized
            await self.save(update_fields=["title"], using_db=connection)
            async with self.workspace.record(
                EventAction.CHAT_RENAMED,
                recordable=self,
                creator_id=current_user.id,
                using_db=connection,
            ) as recording:
                recording.event.details.update({"title": normalized})

    async def _title_conflicts(self, title: str, current_user: User) -> bool:
        group_exists = await Group.filter(
            organization_id=self.organization_id,
            name__iexact=title,
            deleted_at__isnull=True,
        ).exists()
        if group_exists:
            return True

        # Scope to the current user's own chats so the 422 can't be used as an
        # oracle to confirm existence of named chats they aren't a collaborator on.
        # group_id is null for multi/DM chats — group-chat names live on Group.
        return await (
            Chat.filter(
                ChatFilters.by_organization(self.organization_id),
                ChatFilters.by_collaborator(current_user.id),
                group_id__isnull=True,
                title__iexact=title,
            )
            .exclude(id=self.id)
            .exists()
        )

    def validate_add_collaborator(self, user_id: UUID) -> None:
        if self.group_id:
            raise ValueError("Cannot modify collaborators of a group chat.")
        if len(self.workspace.collaborators) >= MAX_CHAT_COLLABORATORS:
            raise ValueError(f"Chat cannot have more than {MAX_CHAT_COLLABORATORS} collaborators.")
        if user_id in self.collaboration.accessor_ids:
            raise ValueError("User is already a collaborator on this chat.")

    def validate_remove_collaborator(self, user_id: UUID) -> None:
        if self.group_id:
            raise ValueError("Cannot modify collaborators of a group chat.")
        if len(self.workspace.collaborators) <= 2:
            raise ValueError("Cannot remove collaborators from a DM.")
        if user_id not in self.collaboration.accessor_ids:
            raise ValueError("User is not a collaborator on this chat.")

    async def add_collaborator(self, user: User, *, added_by: User, using_db: BaseDBAsyncClient) -> None:
        await self.fetch_related("workspace__collaborators")
        self.validate_add_collaborator(user.id)
        async with transaction(using_db) as connection:
            await Chat.select_for_update().filter(id=self.id).using_db(connection).get()
            await self.collaboration.add(user_to_add=user, added_by_user=added_by, using_db=connection)
            collaborator_user_ids = cast(
                list[UUID],
                await Collaborator.filter(workspace_id=self.workspace_id)
                .using_db(connection)
                .values_list("user_id", flat=True),
            )
            self.collaborators_hash = self.compute_collaborators_hash(collaborator_user_ids)
            await self.save(update_fields=["collaborators_hash"], using_db=connection)
            async with self.workspace.record(
                EventAction.CHAT_COLLABORATOR_ADDED,
                recordable=self,
                creator_id=added_by.id,
                using_db=connection,
            ) as recording:
                recording.event.details.update({"user_id": str(user.id)})

    async def remove_collaborator(
        self, user_id: UUID, *, removed_by_id: UUID | None = None, using_db: BaseDBAsyncClient | None = None
    ) -> "CollaboratorRemovalResult":
        await self.fetch_related("workspace__collaborators")
        self.validate_remove_collaborator(user_id)
        async with transaction(using_db) as connection:
            await Chat.select_for_update().filter(id=self.id).using_db(connection).get()
            await self.delete_collaborator(self.workspace_id, user_id, using_db=connection)
            async with self.workspace.record(
                EventAction.CHAT_COLLABORATOR_REMOVED,
                recordable=self,
                creator_id=removed_by_id,
                using_db=connection,
            ) as recording:
                recording.event.details.update({"user_id": str(user_id)})

            remaining_ids = cast(
                list[UUID],
                await Collaborator.filter(workspace_id=self.workspace_id)
                .using_db(connection)
                .values_list("user_id", flat=True),
            )

            if len(remaining_ids) <= 1:
                await self.soft_delete(using_db=connection)
                return CollaboratorRemovalResult(archived=True)

            if len(remaining_ids) == 2 and not self.group_id:
                existing_dm = await Chat.find_by_hash(
                    remaining_ids,
                    self.organization_id,
                    exclude_id=self.id,
                    using_db=connection,
                )
                if existing_dm:
                    await self.soft_delete(using_db=connection)
                    return CollaboratorRemovalResult(archived=True, conflicting_dm_id=existing_dm.id)

            self.collaborators_hash = self.compute_collaborators_hash(remaining_ids)
            await self.save(update_fields=["collaborators_hash"], using_db=connection)
            return CollaboratorRemovalResult(archived=False)


@dataclass
class CollaboratorRemovalResult:
    archived: bool
    conflicting_dm_id: UUID | None = None


class ChatMessage(SoftDeleteableMixin, CommentMixin, RecordModel):
    comment_topic: ClassVar[str] = "chat"
    comment_topic_param: ClassVar[str] = "chat_id"

    chat: fields.ForeignKeyRelation[Chat] = fields.ForeignKeyField("convictional.Chat", related_name="messages")
    chat_id: Annotated[UUID, "foreign key to chat"]
    reply_to: fields.ForeignKeyNullableRelation["ChatMessage"] = fields.ForeignKeyField(
        "convictional.ChatMessage", related_name="replies", null=True, on_delete=fields.SET_NULL
    )
    reply_to_id: Annotated[UUID | None, "foreign key to chat_message"]

    class Meta:
        ordering = ["-created_at"]
        indexes = (("chat_id", "created_at"),)

    async def _chat_topic(self) -> Topic:
        # ChatMessage extends CommentMixin which builds Topic only from chat_id, but the chat
        # channel's auth (is_workspace_authorized) requires workspace_id in the topic params.
        if not isinstance(self.chat, Chat):
            await self.fetch_related("chat")
        return Topic("chat", chat_id=str(self.chat_id), workspace_id=str(self.chat.workspace_id))

    async def broadcast_created(self) -> None:
        topic = await self._chat_topic()
        await topic.broadcast(new_message_id=self.id, author_id=self.user_id)

    async def broadcast_updated(self) -> None:
        topic = await self._chat_topic()
        await topic.broadcast(updated_message_id=self.id)

    async def broadcast_deleted(self) -> None:
        topic = await self._chat_topic()
        await topic.broadcast(deleted_message_id=self.id)


async def _fetch_group_chat(group_id: UUID, using_db: BaseDBAsyncClient | None = None) -> Chat | None:
    return await Chat.filter(group_id=group_id).using_db(using_db).prefetch_related("workspace").first()


post_delete(ChatMessage)(delete_decision_for_comment)


@post_save(GroupMember)
async def sync_new_group_member_to_chat(
    sender: "type[GroupMember]",
    instance: GroupMember,
    created: bool,
    update_fields: list[str],
    using_db: BaseDBAsyncClient | None = None,
) -> None:
    if not created:
        return

    chat = await _fetch_group_chat(instance.group_id, using_db)
    if not chat:
        return

    existing = (
        await Collaborator.unscoped.get_queryset()
        .using_db(using_db)
        .get_or_none(workspace_id=chat.workspace_id, user_id=instance.user_id)
    )
    if existing:
        return

    await Chat.upsert_collaborators(chat.workspace_id, [instance.user_id], None, using_db=using_db)
    async with chat.workspace.record(
        EventAction.CHAT_COLLABORATOR_ADDED,
        recordable=chat,
        creator_id=None,
        using_db=using_db,
    ) as recording:
        recording.event.details.update({"user_id": str(instance.user_id), "via": "group_sync"})


@post_delete(GroupMember)
async def sync_removed_group_member_from_chat(
    sender: "type[GroupMember]",
    instance: GroupMember,
    using_db: BaseDBAsyncClient | None = None,
) -> None:
    chat = await _fetch_group_chat(instance.group_id, using_db)
    if not chat:
        return

    existing = (
        await Collaborator.unscoped.get_queryset()
        .filter(workspace_id=chat.workspace_id, user_id=instance.user_id)
        .using_db(using_db)
        .exists()
    )
    if not existing:
        return

    await Chat.delete_collaborator(chat.workspace_id, instance.user_id, using_db=using_db)
    async with chat.workspace.record(
        EventAction.CHAT_COLLABORATOR_REMOVED,
        recordable=chat,
        creator_id=None,
        using_db=using_db,
    ) as recording:
        recording.event.details.update({"user_id": str(instance.user_id), "via": "group_sync"})
    await Mailbox.sync(chat)


class ChatMailboxEntryFilters(BaseMailboxEntryFilters):
    pass


# Chat-level events that drive the inbox "activity" preview line when newer than the last message.
# Message create/edit/delete are excluded: the message preview reads the message live, and edits/
# deletes must refresh the row silently rather than flip it to an activity line. DECIDED is included
# — recording a decision on a message creates no message, so the message-based path is blind to it
# (the row already force-unreads on DECIDED via InboxUpdate.for_event; this makes the line match).
CHAT_ACTIVITY_ACTIONS = frozenset(
    {
        EventAction.CHAT_COLLABORATOR_ADDED,
        EventAction.CHAT_COLLABORATOR_REMOVED,
        EventAction.CHAT_RENAMED,
        EventAction.DECIDED,
    }
)


@dataclass
class ChatMailboxEntry(BaseMailboxEntry):
    resource_model: ClassVar[type] = Chat
    entry_filters: ClassVar[type[BaseMailboxEntryFilters]] = ChatMailboxEntryFilters
    chat: Chat

    prefetch_for_sync: ClassVar[tuple[str, ...]] = (
        "workspace__collaborators__user",
        "last_message__user",
    )
    _latest_activity_event: "Event | None" = field(default=None, init=False, repr=False)

    async def _prefetch_for_sync(self, using_db: BaseDBAsyncClient | None = None) -> None:
        await super()._prefetch_for_sync(using_db)
        # Unlike goals/posts, chats emit an event per message (CHAT_MESSAGE_CREATED), so the full
        # workspace event log is unbounded. `_apply_preview` only needs the newest activity event,
        # so read that with one targeted query rather than prefetching every message event.
        self._latest_activity_event = (
            await Event.filter(workspace_id=self.chat.workspace_id, action__in=CHAT_ACTIVITY_ACTIONS)
            .using_db(using_db)
            .order_by("-created_at")
            .first()
        )

    @classmethod
    def from_resource(cls, resource: RecordModel) -> Self:
        assert isinstance(resource, Chat)
        return cls(chat=resource)

    @property
    def resource(self) -> Chat:
        return self.chat

    async def touch(self, user: User, *, using_db: BaseDBAsyncClient | None = None) -> None:
        await self._prefetch_for_sync(using_db)

        if sync := await self.refresh_row_and_mark_unread(user, using_db=using_db):
            await sync.broadcast()

    async def mark_as_read(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            await self._prefetch_for_sync(connection)
            if user.id not in self.chat.collaboration.accessor_ids:
                return

            # This is the deliberate bridge between the two read-state systems: the shared
            # sync-forward-and-mark-read pattern (mailbox unread, with its row lock) lives
            # on the base; chats layer the workspace Visit read-cursor on top so the in-chat
            # unread divider tracks the mailbox read state. Keep both in sync when touching either.
            await super().mark_as_read(user, using_db=connection)

            latest_event = (
                await Event.filter(workspace_id=self.chat.workspace_id)
                .using_db(connection)
                .order_by("-created_at")
                .first()
            )
            await Visit.record(
                user.id,
                self.chat.workspace_id,
                last_event_id=latest_event.id if latest_event else None,
                using_db=connection,
            )

    async def mark_as_unread(self, user: User, using_db: BaseDBAsyncClient | None = None) -> None:
        async with transaction(using_db) as connection:
            entry = await self.entry(user).using_db(connection).get()
            await entry.mark_as_unread(using_db=connection)
            # Rewind Visit so api_chat_detail's unread_message_count picks up the
            # latest message(s) from others. Anchor to the workspace event just
            # before that message; the in-chat divider then renders correctly.
            latest_other_message = (
                await ChatMessage.filter(chat_id=self.chat.id, deleted_at__isnull=True)
                .using_db(connection)
                .exclude(user_id=user.id)
                .order_by("-created_at")
                .first()
            )
            if not latest_other_message:
                return
            previous_event = (
                await Event.filter(
                    workspace_id=self.chat.workspace_id,
                    created_at__lt=latest_other_message.created_at,
                )
                .using_db(connection)
                .order_by("-created_at")
                .first()
            )
            await Visit.rewind_cursor(
                user.id,
                self.chat.workspace_id,
                previous_event.id if previous_event else None,
                using_db=connection,
            )

    async def _save_for(
        self,
        user: User,
        apply_to_entry: Callable[[MailboxEntry], object],
        *,
        using_db: BaseDBAsyncClient | None,
    ) -> MailboxSync | None:
        collaborator_user_ids = self.chat.collaboration.accessor_ids
        was_saved = False

        async with transaction(using_db) as connection:
            entry, _is_new = await self.find_or_create_entry(user, self.chat.organization_id, using_db=connection)

            if user.id not in collaborator_user_ids:
                if not entry.is_new:
                    await entry.soft_delete(using_db=connection)
                return None

            entry.owner = user
            apply_to_entry(entry)
            if entry.is_new or entry.is_changed:
                if entry.is_new:
                    await entry.save(using_db=connection)
                else:
                    await entry.save(update_fields=list(entry.changes.keys()), using_db=connection)
                was_saved = True

        if was_saved:
            return MailboxSync(entry_id=entry.id, user_id=user.id)
        return None

    def _refresh_content(self, entry: MailboxEntry) -> bool:
        entry.title = self._resolve_title(entry.owner_id)
        entry.preview = ""
        entry.is_shared = True
        entry.assignee_id = None
        entry.is_preview_comment = False

        last_message = self.chat.last_message if self.chat.last_message_id else None
        self._apply_preview(entry, last_message)

        if self.chat.is_deleted and not entry.is_deleted:
            entry.deleted_at = datetime.now(UTC)
        elif not self.chat.is_deleted and entry.is_deleted:
            entry.deleted_at = None

        old_last_activity_at = entry.last_activity_at if not entry.is_new else None
        new_last_activity_at = last_message.created_at if last_message else self.chat.created_at
        # Monotonic: never regress on message deletion. A deleted last message
        # can move sync_last_message backward; without max() the cursor would
        # rewind and falsely re-trigger _has_new_activity_from_others later.
        if entry.last_activity_at is None or new_last_activity_at > entry.last_activity_at:
            entry.last_activity_at = new_last_activity_at

        has_new_activity = self._has_new_activity_from_others(entry, last_message, old_last_activity_at)

        # When the unread-trigger message is deleted, last_message moves back
        # to something older than read_at (or to None) and the label should
        # follow. Without this clear, a delete-while-unread leaves the inbox
        # badge stuck even though there's nothing left to read.
        if entry.is_unread and not self._has_unread_content(entry, last_message):
            entry.label_as_read()

        # A brand-new entry whose latest message is from someone else surfaces even
        # though there's no prior activity to diff against; existing entries surface
        # on genuinely new activity from others (the retry-idempotent signal).
        has_messages_from_others = last_message is not None and last_message.user_id != entry.owner_id
        return (entry.is_new and has_messages_from_others) or has_new_activity

    def _apply_preview(self, entry: MailboxEntry, last_message: "ChatMessage | None") -> None:
        # Second inbox line: the last message (author + text) unless a chat-level activity event
        # (member added/removed, rename, decided) is newer, in which case pin that event for the
        # client to phrase (see ChatEntryBody). last_activity_at stays message-based, so a newer
        # activity event never re-sorts the row or bumps unread.
        latest_activity = self._latest_activity_event
        message_at = last_message.created_at if last_message else None
        if latest_activity and (message_at is None or latest_activity.created_at > message_at):
            entry.last_event_id = latest_activity.id
            entry.last_comment = None
            entry.last_comment_author_id = None
            return

        entry.last_event_id = None
        if last_message:
            entry.last_comment = last_message.content
            entry.last_comment_author_id = last_message.user_id
        else:
            entry.last_comment = ""
            entry.last_comment_author_id = None

    def _resolve_title(self, owner_id: UUID) -> str:
        return self.chat.resolved_title(owner_id)

    def _has_unread_content(self, entry: MailboxEntry, last_message: "ChatMessage | None") -> bool:
        if last_message is None:
            return False
        if last_message.user_id == entry.owner_id:
            return False
        return entry.read_at is None or last_message.created_at > entry.read_at

    def _has_new_activity_from_others(
        self, entry: MailboxEntry, last_message: ChatMessage | None, old_last_activity_at: datetime | None
    ) -> bool:
        if entry.is_new:
            return False
        if not last_message or not old_last_activity_at:
            return "deleted_at" in entry.changes
        is_from_others = last_message.user_id != entry.owner_id
        is_newer = last_message.created_at > old_last_activity_at
        return (is_from_others and is_newer) or "deleted_at" in entry.changes

    async def _clear_non_collaborators(self, using_db: BaseDBAsyncClient | None = None) -> list[MailboxSync]:
        collaborator_user_ids = self.chat.collaboration.accessor_ids
        results: list[MailboxSync] = []

        async with transaction(using_db) as connection:
            entries = (
                await MailboxEntry.filter(MailboxEntry.filters.by_resource(self.resource_gid))
                .prefetch_related("owner")
                .using_db(connection)
            )
            for entry in entries:
                if entry.owner_id not in collaborator_user_ids:
                    await entry.soft_delete(using_db=connection)
                    results.append(MailboxSync(entry_id=entry.id, user_id=entry.owner_id))

        return results
