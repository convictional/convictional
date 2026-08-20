import asyncio
import builtins
import hashlib
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, ClassVar, cast
from urllib.parse import urljoin, urlparse
from uuid import UUID
from uuid import uuid4 as generate_uuid

from tortoise import BaseDBAsyncClient, fields, signals
from tortoise.exceptions import DoesNotExist, IntegrityError
from tortoise.expressions import Subquery
from tortoise.manager import Manager
from tortoise.queryset import Q, QuerySet
from tortoise.signals import post_save

from app.models.accounts import GroupMember, Organization, PushSubscription, User
from config import logger, settings
from config.enums import (
    ChannelEventAction,
    CollaboratorStatus,
    DeliveryChannel,
    EmailDelivery,
    EventAction,
    LinkPreviewStatus,
    LinkPreviewType,
    ReactionType,
    Sharing,
    SubscriptionLevel,
    SubscriptionSource,
)
from infra.db import (
    GlobalID,
    GlobalIDField,
    JSONField,
    RecordModel,
    SoftDeleteableFilters,
    SoftDeleteableMixin,
    after_commit,
    transaction,
)
from infra.messaging import Topic
from infra.storage import FileReference
from lib.markdown import preview_excerpt

workspace_registry: dict[str, type["WorkspaceMixin"]] = {}


class WorkspaceMixinFilters(SoftDeleteableFilters):
    @classmethod
    def by_organization(cls, organization_id: UUID):
        return Q(organization_id=organization_id)

    @classmethod
    def by_creator(cls, user_id: UUID):
        return Q(creator_id=user_id)

    @classmethod
    def by_collaborated_workspaces(cls, user_id: UUID) -> Q:
        return Q(workspace_id__in=Subquery(Collaborator.filter(user_id=user_id).values_list("workspace_id")))


class WorkspaceMixin(SoftDeleteableMixin, RecordModel):
    title = fields.TextField(null=False)
    sharing = fields.CharEnumField(Sharing, default=Sharing.PRIVATE, max_length=255)
    creator: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    creator_id: Annotated[UUID, "foreign key to creating user"]
    workspace: fields.OneToOneRelation["Workspace"] = fields.OneToOneField(
        "convictional.Workspace", on_delete=fields.NO_ACTION
    )
    workspace_id: Annotated[UUID, "foreign key to the workspace"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    email_delivery = EmailDelivery.SEND

    class Meta:
        abstract = True

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        signals.pre_save(cls)(save_workspace)
        workspace_registry[cls.record_type] = cls

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        if not self.workspace_id and not self.workspace and self.organization_id:
            self.workspace = Workspace(organization_id=self.organization_id)
            self.workspace.resource = self
            self.workspace.sharing = self.sharing

    def after_fetch(self):
        super().after_fetch()
        # This ensures the workspace's resource is the same instance as this fetched resource
        if isinstance(self.workspace, Workspace):
            self.workspace.resource = self

    async def fetch_related(self, *args, using_db=None):
        await super().fetch_related(*args, using_db=using_db)
        # This ensures the workspace's resource is the same instance as this fetched resource
        if isinstance(self.workspace, Workspace):
            self.workspace.resource = self

    @property
    def collaboration(self):
        return CollaborationPolicy(self.workspace)

    @property
    def indexing_activity_at(self) -> datetime:
        """The resource's last meaningful activity, used as the Content row's recency signal.

        Search ranks on Content.updated_at, but a resource's own updated_at only advances when
        its row is re-saved — a comment or decision records a workspace event without touching
        the parent. Folding the event log in keeps a freshly active resource from decaying in
        search as if untouched. Requires workspace.events to be prefetched.
        """
        last_event_at = self.workspace.last_event_at
        return max(self.updated_at, last_event_at) if last_event_at else self.updated_at

    @property
    def notification_policy(self) -> "NotificationPolicy":
        return NotificationPolicy(workspace=self.workspace)

    @classmethod
    def notification_policy_class(cls) -> type["NotificationPolicy"]:
        # Used by callers that need policy-level constants (e.g.
        # default_subscription_level) without constructing an instance.
        # Subclasses override alongside notification_policy.
        return NotificationPolicy

    @property
    def mentions_can_add_collaborators(self) -> bool:
        return True

    async def copy(self, data: dict[str, Any] = {}, using_db: BaseDBAsyncClient | None = None):
        # This is overridden to create a new workspace for the copied resource and update the resource's workspace_id
        # to point to the new workspace. This should always happen in a transaction to avoid inconsistencies.
        new_workspace = Workspace(organization_id=self.organization_id)
        new_workspace.set_temporary()
        await new_workspace.save(using_db=using_db)

        result = await super().copy({"workspace": new_workspace, **data}, using_db=using_db)
        new_workspace.resource = result
        await new_workspace.save(using_db=using_db)
        await new_workspace.add_creator(using_db=using_db)

        return result


async def save_workspace(
    sender: "type[WorkspaceMixin]",
    instance: WorkspaceMixin,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    needs_workspace_save = False

    if "sharing" in instance.changes:
        if not isinstance(instance.workspace, Workspace):
            await instance.fetch_related("workspace", using_db=using_db)
        needs_workspace_save = True

    if isinstance(instance.workspace, Workspace):
        instance.workspace.resource = instance
        if instance.workspace.is_unsaved:
            needs_workspace_save = True

    if needs_workspace_save:
        instance.workspace.sharing = instance.sharing
        await instance.workspace.save(using_db=using_db)


class Workspace(RecordModel):
    resource_gid = GlobalIDField(unique=True)
    sharing = fields.CharEnumField(Sharing, default=Sharing.PRIVATE)  # Mirrors the resource's sharing for querying
    assignee: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="assigned_workspaces", null=True
    )
    assignee_id: Annotated[UUID | None, "foreign key to assignee user"]
    attachments: fields.ReverseRelation["Attachment"]
    collaborators: fields.ReverseRelation["Collaborator"]
    events: fields.ReverseRelation["Event"]
    subscriptions: fields.ReverseRelation["Subscription"]
    mentions: fields.ReverseRelation["Mention"]
    visits: fields.ReverseRelation["Visit"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField("convictional.Organization")
    organization_id: Annotated[UUID, "foreign key to organization"]
    _resource: WorkspaceMixin | None = None

    @classmethod
    def by_ids(cls, workspace_ids: list[UUID]):
        return cls.filter(id__in=workspace_ids)

    @property
    def is_resource_fetched(self):
        return self._resource is not None

    async def fetch_resource(
        self, prefetch_related: list[str] = [], using_db: BaseDBAsyncClient | None = None
    ) -> WorkspaceMixin:
        self._resource = await self.resource_gid.get_or_none(using_db)  # type: ignore
        if not self._resource:
            raise DoesNotExist("Workspace resource not found")
        if not isinstance(self._resource, WorkspaceMixin):
            raise RuntimeError("Invalid resource set for the workspace resource_gid")
        if self._resource.is_deleted:
            raise DoesNotExist("Workspace resource is soft deleted")
        if prefetch_related:
            await self._resource.fetch_related(*prefetch_related, using_db=using_db)

        self._resource.workspace = self  # Skips an extra query if it needs workspace access later
        return self._resource

    async def fetch_resource_or_none(
        self, prefetch_related: list[str] = [], using_db: BaseDBAsyncClient | None = None
    ) -> WorkspaceMixin | None:
        try:
            return await self.fetch_resource(prefetch_related=prefetch_related, using_db=using_db)
        except DoesNotExist:
            return None

    @property
    def resource(self) -> WorkspaceMixin:
        if not self._resource:
            raise RuntimeError("Resource not found, use fetch_resource() or check if resource was soft deleted")
        if not isinstance(self._resource, WorkspaceMixin):
            raise RuntimeError("Invalid resource set for the workspace resource_gid")

        return self._resource

    @resource.setter
    def resource(self, value: WorkspaceMixin):
        self._resource = value
        self._resource.workspace_id = self.id
        self._resource.workspace = self  # Skips an extra query if it needs workspace access later
        self.resource_gid = value.global_id

    @property
    def resource_type(self):
        return self.resource_gid.record_type

    @property
    def resource_id(self):
        return self.resource_gid.record_id

    @property
    def is_temporary(self):
        return self.resource_gid.record_type == self.record_type

    def set_temporary(self):
        self.resource_gid = GlobalID.parse(f"gid://convictional/{self.record_type}/{generate_uuid()}")

    @asynccontextmanager
    async def record(
        self,
        action: EventAction,
        recordable: RecordModel | None = None,
        creator_id: UUID | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ):
        if not recordable:
            if not self.is_resource_fetched:
                await self.fetch_resource(using_db=using_db)
            recordable = self.resource

        async with transaction(using_db=using_db) as connection:
            if self.is_new:
                await self.save(using_db=connection)

            event = Event(
                workspace=self,
                workspace_id=self.id,
                recordable_id=recordable.id,
                recordable_type=recordable.record_type,
                creator_id=creator_id,
                action=action,
                details=recordable.changes,
            )

            recording = Recording(event, recordable=recordable, using_db=connection)
            await recording.event.save(using_db=connection)
            yield recording
            recording.event.details.update(recordable.changes)
            await recording.save(using_db=connection)

            async def broadcast(using_db: BaseDBAsyncClient):
                await Topic("workspace_events", workspace_id=self.id).broadcast(event_id=event.id)

            await after_commit(broadcast)

    @property
    def last_event_at(self):
        return max((event.created_at for event in self.events), default=None)

    def last_event_by_others(self, user_id: UUID):
        other_events = [event for event in self.events if event.creator_id != user_id]
        return max(other_events, key=lambda x: x.created_at, default=None)

    async def subscription_for(self, subscriber_id: UUID, using_db: BaseDBAsyncClient | None = None):
        subscription = await Subscription.get_or_init(
            subscriber_id=subscriber_id, workspace_id=self.id, using_db=using_db
        )
        # Ensure workspace relation is loaded for future access
        subscription.workspace = self

        if subscription.is_new:
            preference = await SubscriptionPreference.for_global(subscriber_id, self.resource_type, using_db=using_db)
            if preference:
                subscription.level = preference.default_level

        return subscription

    async def subscribe(self, subscriber_id: UUID, using_db: BaseDBAsyncClient | None = None):
        subscription = await self.subscription_for(subscriber_id, using_db)
        subscription.level = SubscriptionLevel.ALL
        await subscription.save(using_db=using_db)
        return subscription

    async def unsubscribe(self, subscriber_id: UUID, using_db: BaseDBAsyncClient | None = None):
        subscription = await self.subscription_for(subscriber_id, using_db)
        subscription.level = SubscriptionLevel.RELEVANT_ONLY
        await subscription.save(using_db=using_db)
        return subscription

    @staticmethod
    async def ensure_collaborator(workspace_id: UUID, user_id: UUID, using_db: BaseDBAsyncClient | None = None):
        await Collaborator.get_or_create(
            defaults={"added_by_id": user_id},
            workspace_id=workspace_id,
            user_id=user_id,
            using_db=using_db,
        )

    async def add_creator(self, using_db: BaseDBAsyncClient | None = None):
        await Collaborator.get_or_create(
            workspace_id=self.id,
            user_id=self.resource.creator_id,
            added_by_id=self.resource.creator_id,
            using_db=using_db,
        )

    async def add_mentioned_collaborators(
        self, resolver: "MentionResolver", creator_id: UUID, using_db: BaseDBAsyncClient | None = None
    ):
        if not self.resource.mentions_can_add_collaborators:
            return

        added_by = await User.get(id=creator_id)

        collaborator_user_ids = {c.user_id for c in self.collaborators}
        possible_users = await User.active.filter(User.filters.by_organization(self.organization_id)).all()

        for mentioned_name in resolver.possible_mentions:
            matching_users = [u for u in possible_users if u.display_name == mentioned_name]

            if len(matching_users) > 1:
                logger.warning(
                    f"Multiple users with display name '{mentioned_name}' in workspace {self.id}. "
                    f"Using first match: {matching_users[0].id}"
                )

            matching_user = matching_users[0] if matching_users else None
            if matching_user and matching_user.id not in collaborator_user_ids:
                _, was_added = await self.resource.collaboration.add(
                    user_to_add=matching_user, added_by_user=added_by, using_db=using_db
                )
                if was_added:
                    collaborator_user_ids.add(matching_user.id)

                    async with self.record(
                        EventAction.ADDED_COLLABORATOR, creator_id=creator_id, using_db=using_db
                    ) as recording:
                        recording.event.details.update(
                            {"collaborator": matching_user.field_values, "reason": "via @mention"}
                        )

    async def resolve_mentions(
        self,
        content: str,
        creator_id: UUID,
        recordable: RecordModel | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> list["Mention"]:
        resolver = MentionResolver(
            recordable=recordable or self.resource, workspace=self, content=content, creator_id=creator_id
        )

        await self.add_mentioned_collaborators(resolver, creator_id, using_db=using_db)

        await resolver.resolve(using_db=using_db)

        for mention in resolver.mentions:
            await mention.save(using_db=using_db)

        return resolver.mentions


@post_save(Workspace)
async def ensure_creator_collaborator(
    sender: "type[Workspace]",
    instance: Workspace,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
):
    if created and not instance.is_temporary:
        await instance.add_creator(using_db=using_db)


@dataclass
class WorkspaceResourceFetcher:
    workspaces: list[Workspace]
    prefetch_map: dict[type[WorkspaceMixin], list[str]] = field(default_factory=dict)

    async def fetch(self, using_db: BaseDBAsyncClient | None = None):
        for workspace in self.workspaces:
            record_type = workspace.resource_gid.record_type
            if not workspace_registry.get(record_type):
                raise ValueError(f"Invalid workspace type: {record_type}")

        gids = [w.resource_gid for w in self.workspaces]
        prefetch = (
            {cls.record_type: prefetch_fields for cls, prefetch_fields in self.prefetch_map.items()}
            if self.prefetch_map
            else None
        )
        records = cast(
            dict[tuple[str, UUID], WorkspaceMixin],
            await GlobalID.bulk_fetch(gids, using_db=using_db, prefetch_map=prefetch),
        )

        for workspace in self.workspaces:
            gid = workspace.resource_gid
            resource = records.get((gid.record_type, gid.record_id))
            if resource:
                workspace.resource = resource

        self._filter_deleted_resources()
        return self.workspaces

    def _filter_deleted_resources(self):
        results = [
            workspace for workspace in self.workspaces if workspace._resource and not workspace._resource.is_deleted
        ]

        self.workspaces = results


#
# Events
#
#


@dataclass
class EventFilters:
    @classmethod
    def by_workspace(cls, workspace_id: UUID):
        return Q(workspace_id=workspace_id)

    @classmethod
    def by_recordable(cls, recordable_id: UUID):
        return Q(recordable_id=recordable_id)

    @classmethod
    def by_action(cls, action: EventAction):
        return Q(action=action)

    @classmethod
    def by_actions(cls, event_actions: list[EventAction]):
        return Q(action__in=event_actions)


class Event(RecordModel):
    recordable_id = fields.UUIDField()
    recordable_type = fields.CharField(max_length=500)
    action = fields.CharEnumField(EventAction, max_length=255)
    details: dict[str, Any] = JSONField(default={})
    creator: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User", on_delete=fields.SET_NULL, null=True
    )
    creator_id: Annotated[UUID | None, "foreign key to creator user"]
    workspace: fields.ForeignKeyRelation[Workspace] = fields.ForeignKeyField("convictional.Workspace")
    workspace_id: Annotated[UUID, "foreign key to workspace"]
    mentions: fields.ReverseRelation["Mention"]

    filters = EventFilters()

    class Meta:
        ordering = ["created_at"]
        indexes = (("recordable_type", "recordable_id"), ("workspace_id", "created_at"))

    @property
    def is_system(self):
        return not self.creator_id


class Notification(RecordModel):
    event: fields.ForeignKeyRelation[Event] = fields.ForeignKeyField("convictional.Event")
    event_id: Annotated[UUID, "foreign key to event"]
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    user_id: Annotated[UUID, "foreign key to recipient user"]
    channel = fields.CharEnumField(DeliveryChannel, default=DeliveryChannel.EMAIL)
    device: fields.ForeignKeyNullableRelation[PushSubscription] = fields.ForeignKeyField(
        "convictional.PushSubscription", null=True, on_delete=fields.SET_NULL, db_index=True
    )
    # NULL for email rows. Also NULL for push rows whose subscription was later
    # hard-deleted: we use ON DELETE SET NULL (not CASCADE) so cleanup of stale
    # push subscriptions doesn't wipe historical delivery rows from the ledger.
    device_id: Annotated[UUID | None, "foreign key to push subscription"]
    # Snapshot of PushSubscription.platform at delivery time so "which device got
    # pushed?" remains answerable after device_id goes NULL via the cleanup above.
    # Typed TextField to match PushSubscription.platform (the source) so the type
    # contract never truncates derived labels.
    device_label_snapshot: str | None = fields.TextField(null=True)
    delivered_at: datetime | None = fields.DatetimeField(null=True)

    class Meta:
        indexes = (("user_id",), ("delivered_at",))
        # Postgres treats NULL as distinct in unique indexes (NULLS DISTINCT, the
        # default) — intentional. The constraint enforces one-row-per-device for
        # push rows (device_id is non-null) and doesn't restrict email rows at all
        # (device_id is NULL there). Email idempotency lives at the job layer via
        # Job.create_or_get_by_unique, not at the DB constraint.
        unique_together = (("event_id", "user_id", "channel", "device_id"),)

    @classmethod
    async def push_record_for(cls, *, event_id: UUID, user_id: UUID, subscription: PushSubscription) -> "Notification":
        # Two concurrent workers can race here; the unique constraint forces one to
        # retry the SELECT and both see the same row. Both may still send — that's the
        # at-least-once contract; the OS `tag` collapses the visible duplicate.
        record, _ = await cls.get_or_create(
            event_id=event_id,
            user_id=user_id,
            channel=DeliveryChannel.PUSH,
            device_id=subscription.id,
        )
        return record

    async def mark_delivered_to(self, subscription: PushSubscription) -> None:
        self.delivered_at = datetime.now(UTC)
        self.device_label_snapshot = subscription.platform
        await self.save(update_fields=["delivered_at", "device_label_snapshot"])


@dataclass
class Recording:
    event: Event
    recordable: RecordModel | None = None
    mentions: list["Mention"] = field(default_factory=list)
    using_db: BaseDBAsyncClient | None = None

    async def resolve_mentions(self, content: str, recordable: RecordModel | None = None):
        if not self.event.creator_id:
            raise ValueError("Cannot resolve mentions for system events")
        if not recordable:
            recordable = self.recordable or self.event.workspace.resource

        mentions = await self.event.workspace.resolve_mentions(
            content, self.event.creator_id, recordable, self.using_db
        )
        for mention in mentions:
            mention.event_id = mention.event_id or self.event.id

        self.mentions.extend(mentions)

    async def save(self, using_db: BaseDBAsyncClient | None = None):
        await self.event.save(using_db=using_db)
        for mention in self.mentions:
            if mention.is_unsaved:
                await mention.save(using_db=using_db)


#
# Collaborators
#
#


@dataclass
class NotificationPolicy:
    """Per-resource notification behavior. Sibling to CollaborationPolicy.

    The resolver reads notification-relevant properties through this seam so
    that resource-specific behavior (DM force-include, broadcasts-to-org,
    per-group mute) lives on a per-resource subclass instead of scattered
    across `WorkspaceMixin` defaults and resource model overrides. Subclasses
    live in `workspaces/<resource>.py`.
    """

    workspace: Workspace

    default_subscription_level: ClassVar[SubscriptionLevel] = SubscriptionLevel.RELEVANT_ONLY

    @property
    def notification_group_id(self) -> UUID | None:
        return None

    @property
    def broadcasts_to_organization(self) -> bool:
        return False

    def force_include_for_inbox(self, action: EventAction | None = None) -> bool:
        # When True for this event, every reachable member gets an inbox entry regardless of
        # their subscription level (the level can't hide it). `action` is the event being synced,
        # or None on a state-driven recompute; policies that force-include only a specific
        # transition (e.g. an announcement) gate on it. Default False.
        return False

    def reaches_only_direct_recipients(self, action: EventAction | None = None) -> bool:
        # When True for this event, the inbox reaches only its direct recipients
        # (`relevant_to_user_ids` — a direct ask), suppressing the level-based fan-out to
        # ALL-level subscribers. E.g. a targeted request that should not be broadcaset to
        # ALL-level subscribers.
        return False

    @property
    def force_include_all_collaborators_for_push(self) -> bool:
        # When True, every collaborator is pushed regardless of their
        # subscription level. Default False.
        return False

    @property
    def notify_subscriber_push(self) -> bool:
        # When True, an ordinary event push-notifies every effective subscriber
        # (a member whose subscription level resolves to ALL); a level below ALL
        # silences it. Default False: ordinary events don't push.
        return False

    @property
    def notify_mention_push(self) -> bool:
        # When True, an @mention of a user on this resource also push-notifies
        # them. Default False: the @mention reaches inbox/email but doesn't push.
        return False

    # Event actions where a comment/mark is a "reply on yours (resource)": it targets the
    # resource's creator and assignee, reaching both their push and their inbox (force-surfaced
    # past the content gate, so an archived email thread re-surfaces). Empty by default. A
    # ClassVar (not a property) because it's a fixed per-resource-type value, like
    # default_subscription_level.
    creator_and_assignee_reply_actions: ClassVar[frozenset[EventAction]] = frozenset()

    def relevant_to_user_ids(self, event: "Event") -> set[UUID]:
        """User ids this event's action directly targets by a resource-specific rule — a direct
        ask, force-surfaced past the level gate like a mention, beyond the generic
        mention/assignee/reply audiences the mailbox job already derives from the event. Reads
        resource-specific fields the job can't see generically."""
        return set()

    async def muted_user_ids(self, using_db: BaseDBAsyncClient | None = None) -> set[UUID]:
        return set()

    async def thread_participant_ids(self, comment_id: UUID, using_db: BaseDBAsyncClient | None = None) -> set[UUID]:
        # Every user who has authored a comment in the same thread as `comment_id` — the
        # "reply on yours (thread)" audience. A reply in a thread you've commented in always
        # reaches you, like a mention, regardless of your subscription level. Resource
        # subclasses that have threaded comments override this to query their comment model
        # and thread key; the default is empty for resources without threaded comments.
        return set()


@dataclass(frozen=True)
class CollaboratorViewState:
    """One collaborator's view state on a resource, derived from their Visit.

    The single shape every "seen-by" / "last viewed" / "caught up" / "what's new" / "unread"
    reader consumes — resolve it through ViewStateResolver, never by querying Visit directly.

    - `last_viewed_at` is when they last viewed (Visit.updated_at).
    - `last_viewed_event_id` is their event cursor, for deriving caught-up-ness against the
      resource's latest event. None when unviewed or the visit recorded no event.
    - `last_viewed_event_at` is that cursor event's created_at — the pivot chat uses to count
      messages since last read. None whenever last_viewed_event_id is.
    """

    viewed: bool
    last_viewed_at: datetime | None
    last_viewed_event_id: UUID | None
    last_viewed_event_at: datetime | None = None

    @classmethod
    def unviewed(cls) -> "CollaboratorViewState":
        return cls(viewed=False, last_viewed_at=None, last_viewed_event_id=None, last_viewed_event_at=None)

    @classmethod
    def from_visit(cls, visit: "Visit") -> "CollaboratorViewState":
        # last_viewed_event_at needs the visit's `last_event` prefetched (ViewStateResolver does this).
        return cls(
            viewed=True,
            last_viewed_at=visit.updated_at,
            last_viewed_event_id=visit.last_event_id,
            last_viewed_event_at=visit.last_event.created_at if visit.last_event else None,
        )


@dataclass
class CollaborationPolicy:
    workspace: Workspace

    @property
    def accessor_ids(self):
        return {collaborator.user_id for collaborator in self.workspace.collaborators}

    @property
    def accessors(self):
        queryset = User.filter(organization_id=self.workspace.organization_id)

        if self.workspace.sharing.is_organization:
            return queryset

        return queryset.filter(id__in=self.accessor_ids)

    @property
    def is_assigned(self):
        return self.workspace.assignee_id is not None

    def is_collaborator(self, user: User):
        return user.id in self.accessor_ids

    def can_be_accessed_by(self, user: User):
        if self.workspace.sharing.is_organization and user.organization_id == self.workspace.organization_id:
            return True

        return self.is_collaborator(user)

    def is_removable(self, user_id: UUID):
        if user_id == self.workspace.resource.creator_id:
            return False

        return self.workspace.assignee_id != user_id

    async def add(self, user_to_add: User, added_by_user: User, using_db: BaseDBAsyncClient | None = None):
        async with transaction(using_db) as connection:
            existing = cast(
                Collaborator | None,
                await Collaborator.unscoped.get_queryset()
                .using_db(connection)
                .get_or_none(workspace_id=self.workspace.id, user_id=user_to_add.id),
            )
            if existing and existing.status.is_approved:
                return existing, False

            if existing:
                existing.mark_approved(added_by_user_id=added_by_user.id)
                await existing.save(using_db=connection)
                result = existing
            else:
                result = Collaborator(
                    workspace_id=self.workspace.id, user_id=user_to_add.id, added_by_id=added_by_user.id
                )
                await result.save(using_db=connection)

            async def broadcast(using_db: BaseDBAsyncClient):
                await Topic("workspace_collaborators", workspace_id=self.workspace.id).broadcast(
                    created_collaborator_id=result.id
                )

            await after_commit(broadcast)
            return result, True

    async def remove(self, user_to_remove: User, using_db: BaseDBAsyncClient | None = None):
        async with transaction(using_db) as connection:
            collaborator = await Collaborator.get(
                workspace_id=self.workspace.id, user_id=user_to_remove.id, using_db=connection
            )

            if not self.is_removable(user_to_remove.id):
                return collaborator, False

            await collaborator.delete(using_db=connection)

            async def broadcast(using_db: BaseDBAsyncClient):
                await Topic("workspace_collaborators", workspace_id=self.workspace.id).broadcast(
                    deleted_collaborator_id=collaborator.id
                )

            await after_commit(broadcast)
            return collaborator, True

    async def assign_to(self, assignee: User, assigned_by: User, using_db: BaseDBAsyncClient | None = None):
        self.workspace.assignee_id = assignee.id
        await self.workspace.save(using_db=using_db)
        await self.add(assignee, assigned_by, using_db=using_db)
        return assignee

    async def unassign(self, user: User | None = None, using_db: BaseDBAsyncClient | None = None) -> None:
        if user and self.workspace.assignee_id != user.id:
            return
        self.workspace.assignee_id = None
        await self.workspace.save(using_db=using_db)

    async def get_assignee(self, using_db: BaseDBAsyncClient | None = None) -> User | None:
        if not self.workspace.assignee_id:
            return None
        if isinstance(self.workspace.assignee, User):
            return self.workspace.assignee
        return await User.get_or_none(id=self.workspace.assignee_id, using_db=using_db).select_related("avatar_file")

    def is_assigned_to(self, user: User) -> bool:
        return self.workspace.assignee_id == user.id


class StatusApprovedCollaboratorManager(Manager):
    def get_queryset(self) -> QuerySet:
        return super().get_queryset().filter(status=CollaboratorStatus.APPROVED)


class Collaborator(RecordModel):
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="collaborations")
    user_id: Annotated[UUID, "foreign key to user"]
    added_by: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="collaborations_added", null=True
    )
    added_by_id: Annotated[UUID | None, "foreign key to adding user"]
    status = fields.CharEnumField(CollaboratorStatus, default=CollaboratorStatus.APPROVED, max_length=255)
    workspace: fields.ForeignKeyRelation[Workspace] = fields.ForeignKeyField(
        "convictional.Workspace", related_name="collaborators"
    )
    workspace_id: Annotated[UUID, "foreign key to workspace"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("workspace_id", "user_id"), ("user_id", "workspace_id"))
        unique_together = ("workspace_id", "user_id")
        manager = StatusApprovedCollaboratorManager()

    @classmethod
    def by_workspace(cls, workspace_id: UUID):
        return cls.filter(workspace_id=workspace_id)

    @classmethod
    def by_user(cls, user_id: UUID):
        return cls.filter(user_id=user_id)

    def mark_approved(self, added_by_user_id: UUID | None = None):
        if added_by_user_id:
            self.added_by_id = added_by_user_id
        self.status = CollaboratorStatus.APPROVED


#
# Subscriptions
#
#


class SubscriptionFilters:
    @classmethod
    def by_workspace(cls, workspace_id: UUID) -> Q:
        return Q(workspace_id=workspace_id)

    @classmethod
    def by_subscribers(cls, subscriber_ids: list[UUID]) -> Q:
        return Q(subscriber_id__in=subscriber_ids)


class Subscription(RecordModel):
    level = fields.CharEnumField(SubscriptionLevel, default=SubscriptionLevel.RELEVANT_ONLY)
    subscriber: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField("convictional.User")
    subscriber_id: Annotated[UUID, "foreign key to subscribing user"]
    workspace: fields.ForeignKeyRelation[Workspace] = fields.ForeignKeyField("convictional.Workspace")
    workspace_id: Annotated[UUID, "foreign key to workspace"]
    filters = SubscriptionFilters()

    class Meta:
        # The unique_together constraint already covers (subscriber_id, workspace_id);
        # this index leads with workspace_id for the dominant resolver query
        # (WHERE workspace_id = X AND subscriber_id IN (...)).
        indexes = (("workspace_id", "subscriber_id"),)
        unique_together = ("subscriber_id", "workspace_id")

    @property
    def wants_all(self):
        return self.level == SubscriptionLevel.ALL


class SubscriptionPreferenceFilters:
    @classmethod
    def by_subscribers(cls, subscriber_ids: list[UUID]) -> Q:
        return Q(subscriber_id__in=subscriber_ids)

    @classmethod
    def for_resource_type(cls, resource_type: str) -> Q:
        return Q(resource_type=resource_type)


class SubscriptionPreference(RecordModel):
    # Per-user, per-resource-type default that drives Notifier dispatch when a
    # user has no explicit Subscription for a given workspace. Surfaced to users
    # on /notifications as "notification preferences" — the model name predates
    # that surface and was kept to avoid a churning rename.
    default_level = fields.CharEnumField(SubscriptionLevel, default=SubscriptionLevel.RELEVANT_ONLY)
    resource_type = fields.CharField(max_length=255)
    subscriber: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField("convictional.User")
    subscriber_id: Annotated[UUID, "foreign key to subscribing user"]
    filters = SubscriptionPreferenceFilters()

    class Meta:
        indexes = (("subscriber_id", "resource_type"),)
        unique_together = ("subscriber_id", "resource_type")

    @classmethod
    async def for_global(cls, subscriber_id: UUID, resource_type: str, using_db: BaseDBAsyncClient | None = None):
        return (
            await cls.filter(
                cls.filters.for_resource_type(resource_type),
                subscriber_id=subscriber_id,
            )
            .using_db(using_db)
            .first()
        )

    @classmethod
    async def ensure_defaults(cls, user_id: UUID, using_db: BaseDBAsyncClient | None = None):
        for preference in await cls.defaults_for(user_id, using_db=using_db):
            await preference.save(using_db=using_db)

    @classmethod
    async def defaults_for(cls, user_id: UUID, using_db: BaseDBAsyncClient | None = None):
        existing = {
            preference.resource_type: preference
            for preference in await cls.filter(subscriber_id=user_id).using_db(using_db)
        }

        results: list[SubscriptionPreference] = []
        for resource_type, workspace_class in workspace_registry.items():
            if resource_type in existing:
                results.append(existing[resource_type])
            else:
                results.append(
                    cls(
                        subscriber_id=user_id,
                        resource_type=resource_type,
                        default_level=workspace_class.notification_policy_class().default_subscription_level,
                    )
                )

        return results

    @classmethod
    async def update_for(
        cls, user_id: UUID, preferences: dict[str, SubscriptionLevel], using_db: BaseDBAsyncClient | None = None
    ):
        for resource_type, level in preferences.items():
            preference = await cls.get_or_init(subscriber_id=user_id, resource_type=resource_type, using_db=using_db)
            preference.default_level = level
            await preference.save(using_db=using_db)


@dataclass(frozen=True)
class SubscriptionState:
    """Effective subscription for a single user, plus which fallback tier resolved it."""

    level: SubscriptionLevel
    source: SubscriptionSource

    @property
    def wants_all(self) -> bool:
        return self.level == SubscriptionLevel.ALL

    @property
    def is_explicit(self) -> bool:
        return self.source == SubscriptionSource.RESOURCE


@dataclass
class SubscriberResolver:
    """Resolve effective subscription per user via a fixed cascade:
    explicit Subscription → creator → group membership (PostGroupMute opts out) → global.

    Group membership is decisive — members never fall through to global — so a
    per-group mute can override a global ALL preference, and membership can
    override a global RELEVANT_ONLY. The creator tier sits above membership so
    muting a group you posted to doesn't drop you out of your own thread.

    Candidates are workspace collaborators + notification-group members, plus
    organization accessors when notification_policy.broadcasts_to_organization
    is true (Post). For non-broadcasting resources, passive viewing access
    stays distinct from subscription, so a global ALL doesn't fan every
    comment out to every org member.

    Runs in Python at current scale; move to a SQL-side resolution (LEFT JOIN
    + COALESCE) if per-event iteration ever becomes a bottleneck.
    """

    workspace: Workspace
    using_db: BaseDBAsyncClient | None = None

    _resource: WorkspaceMixin | None = field(default=None, init=False, repr=False)
    _policy: "NotificationPolicy | None" = field(default=None, init=False, repr=False)
    _candidates: dict[UUID, User] = field(default_factory=dict, init=False, repr=False)
    _subscription_levels: dict[UUID, SubscriptionLevel] = field(default_factory=dict, init=False, repr=False)
    _group_member_ids: set[UUID] = field(default_factory=set, init=False, repr=False)
    _group_muted_ids: set[UUID] = field(default_factory=set, init=False, repr=False)
    _global_pref_levels: dict[UUID, SubscriptionLevel] = field(default_factory=dict, init=False, repr=False)
    _is_org_wide_broadcast: bool = field(default=False, init=False, repr=False)
    _loaded: bool = field(default=False, init=False, repr=False)

    @property
    def _resolved_resource(self) -> WorkspaceMixin:
        if self._resource is None:
            raise RuntimeError("SubscriberResolver._load must be called before accessing the resource")
        return self._resource

    @property
    def _resolved_policy(self) -> "NotificationPolicy":
        if self._policy is None:
            raise RuntimeError("SubscriberResolver._load must be called before accessing the policy")
        return self._policy

    async def _ensure_resource(self) -> None:
        if self._resource is not None:
            return
        self._resource = (
            self.workspace.resource
            if self.workspace.is_resource_fetched
            else await self.workspace.fetch_resource(using_db=self.using_db)
        )
        self._policy = self._resource.notification_policy

    async def resolve(self, exclude_user_id: UUID | None = None) -> list[User]:
        return [user for user, _source in await self.resolve_with_sources(exclude_user_id)]

    async def resolve_with_sources(self, exclude_user_id: UUID | None = None) -> list[tuple[User, SubscriptionSource]]:
        await self._load(exclude_user_id)
        collaboration = self._resolved_resource.collaboration
        return [
            (user, self._source_for(user_id))
            for user_id, user in self._candidates.items()
            if self._level_for(user_id) == SubscriptionLevel.ALL and collaboration.can_be_accessed_by(user)
        ]

    async def resolve_for_push(
        self,
        event: Event,
        *,
        mention_user_ids: set[UUID],
        exclude_user_id: UUID | None = None,
    ) -> list[User]:
        """Users who should receive a SendEventPushJob for this event.

        Push is narrower than the subscription cascade that drives inbox/email.
        It doesn't fan out to every subscriber by default; the recipient set is
        the union of whichever push opt-ins the resource's policy sets:
          - `force_include_all_collaborators_for_push`: every participant, ignoring level.
          - `notify_subscriber_push`: every effective subscriber (members at ALL).
          - `creator_and_assignee_reply_actions`: the creator and assignee, when
            `event.action` is in the set.
        Which of these a policy sets, and why, lives on the policy subclass.
        Mention recipients are excluded — they receive a separate
        SendMentionPushJob, so including them here would double-fire.

        Callers pass `mention_user_ids` explicitly because the only safe
        in-process source depends on lifecycle: the Notifier reads
        `recording.mentions` mid-recording (Mention rows exist but their
        event_id link isn't flushed yet); post-commit callers query Mention
        by event_id themselves.
        """
        await self._ensure_resource()
        policy = self._resolved_policy
        # Load collaborators before reading the policy's push flags: a policy may
        # derive a flag from the collaborator set, so the fetch must come first.
        await self.workspace.fetch_related("collaborators__user", using_db=self.using_db)
        collaboration = self._resolved_resource.collaboration
        force_include = policy.force_include_all_collaborators_for_push
        pushes_reply_audience = event.action in policy.creator_and_assignee_reply_actions
        creator_and_assignee_ids = self._creator_and_assignee_ids() if pushes_reply_audience else set()
        # A reply also pushes everyone who has commented in the same thread — the "reply on
        # yours (thread)" audience — on the same actions where it pushes the creator/assignee.
        # The actor is excluded: replying in your own thread doesn't push you.
        reply_thread_ids = (
            await policy.thread_participant_ids(event.recordable_id, self.using_db) if pushes_reply_audience else set()
        )
        reply_thread_ids.discard(exclude_user_id)
        # An assignment is a direct ask, so it pushes the assignee like an @mention — regardless
        # of subscription level (a mute doesn't silence being assigned). Only the assignee (not
        # the creator). A self-assignment is a direct ask to yourself, so the assignee bypasses
        # the actor exclusion below (like a self-mention on its own path) — self-assigning
        # pushes you. Systemic across resource types. Reads the live workspace.assignee_id (not
        # the event details the async inbox job uses) because push resolves synchronously inside
        # record_and_notify, right after assign_to set it — there's no reassignment drift here.
        assignee_id = self.workspace.assignee_id if event.action == EventAction.ASSIGNED else None

        recipients: dict[UUID, User] = {}
        for collaborator in self.workspace.collaborators:
            user = collaborator.user
            if user is None:
                continue
            is_assignee = user.id == assignee_id
            if user.id == exclude_user_id and not is_assignee:
                continue
            if not (
                force_include
                or collaborator.user_id in creator_and_assignee_ids
                or collaborator.user_id in reply_thread_ids
                or is_assignee
            ):
                continue
            if not collaboration.can_be_accessed_by(user):
                continue
            recipients.setdefault(user.id, user)

        # Thread participants aren't guaranteed to be workspace collaborators on every
        # resource, so add any not caught by the collaborator loop directly (having authored
        # a comment, they can access the resource).
        for user in await self._load_missing_users(reply_thread_ids - recipients.keys()):
            if collaboration.can_be_accessed_by(user):
                recipients.setdefault(user.id, user)

        # The one push opt-in that reads the subscription cascade: include every
        # effective subscriber (members at ALL), so muting silences push. The
        # checks above are membership- or action-based and ignore the level.
        if policy.notify_subscriber_push:
            for user in await self.resolve(exclude_user_id=exclude_user_id):
                recipients.setdefault(user.id, user)

        return [user for user_id, user in recipients.items() if user_id not in mention_user_ids]

    def _creator_and_assignee_ids(self) -> set[UUID]:
        # Creator and assignee are always workspace collaborators (add_creator /
        # CollaborationPolicy.assign_to), so resolve_for_push reads them off the
        # already-loaded collaborator set rather than issuing extra queries.
        ids = {self._resolved_resource.creator_id}
        if self.workspace.assignee_id:
            ids.add(self.workspace.assignee_id)
        return ids

    async def _load_missing_users(self, user_ids: set[UUID]) -> list[User]:
        # `User.active` (NonDeletedManager) rather than the default manager, which includes
        # soft-deleted users — a deactivated account that once commented must not be pushed or
        # emailed a thread reply.
        if not user_ids:
            return []
        return await User.active.filter(id__in=user_ids).using_db(self.using_db)

    async def _add_active_recipients(self, recipients: dict[UUID, User], candidate_ids: set[UUID]) -> None:
        """Fold every not-yet-present active user in `candidate_ids` into `recipients` (in place)."""
        for user in await self._load_missing_users(candidate_ids - recipients.keys()):
            recipients.setdefault(user.id, user)

    async def resolve_for_email(
        self,
        event: Event,
        *,
        mention_user_ids: set[UUID],
        exclude_user_id: UUID | None = None,
    ) -> list[User]:
        """Users who should receive a Notification (and SendEventEmailJob) for this event.

        Empty for `email_delivery.SKIP` resources (Chat, Post, EmailThread, Goal) —
        chat-mention emails are intentionally skipped (no MentionMailer path
        for SKIP resources), and post/chat updates surface via the mailbox.
        For SEND-mode resources, mirrors the inbox cascade (ALL-level
        subscribers) with sender excluded and mention recipients dropped — a
        mentioned user gets a SendMentionJob via Notifier.notify_mentions.

        `mention_user_ids` semantics match `resolve_for_push`.
        """
        await self._ensure_resource()
        if not self._resolved_resource.email_delivery.is_send:
            return []
        recipients = {user.id: user for user in await self.resolve(exclude_user_id=exclude_user_id)}
        # A reply reaches everyone who commented in the same thread — the "reply on yours
        # (thread)" audience — even below ALL, mirroring the inbox/push surfaces. The actor is
        # excluded; a mentioned participant gets a SendMentionJob instead (dropped below).
        reply_thread_ids = await self._resolved_policy.thread_participant_ids(event.recordable_id, self.using_db)
        reply_thread_ids.discard(exclude_user_id)
        collaboration = self._resolved_resource.collaboration
        for user in await self._load_missing_users(reply_thread_ids - recipients.keys()):
            if collaboration.can_be_accessed_by(user):
                recipients.setdefault(user.id, user)
        return [user for user_id, user in recipients.items() if user_id not in mention_user_ids]

    async def direct_recipients_for(self, event: Event) -> list[User]:
        """Users this event personally targets: @mention recipients, a resource-specific action
        target (e.g. the goal owner an update is requested from, via
        `NotificationPolicy.relevant_to_user_ids`), the assignee of an assignment, the resource's
        creator/assignee when a reply lands on their resource, and everyone who has commented in
        the same thread as the event's comment (the "reply on yours" audience — resource and
        thread). Direct recipients are force-surfaced past the resource content gate by
        `InboxUpdate.for_event`, so a reply on your thread reaches the inbox exactly like an
        @mention (and re-opens an email thread the owner archived).

        The inbox counterpart to `resolve_for_push`'s reply/assignee reach, resolved async from
        persisted `Mention` rows (their `event_id` link is flushed by the time the mailbox sync
        runs). Deleted users are dropped but access is not checked here — `resolve_for_inbox`
        applies the access filter when it folds these into reach."""
        await self._ensure_resource()
        policy = self._resolved_policy

        mentions = await Mention.filter(event_id=event.id).using_db(self.using_db).prefetch_related("mentioned")
        recipients = {m.mentioned.id: m.mentioned for m in mentions if m.mentioned and not m.mentioned.is_deleted}

        # Resource-specific action target derived from the event (a goal update request is a direct
        # ask to the owner). The actor is never a direct recipient of their own action, so
        # requesting an update from yourself doesn't force-alert you.
        target_ids = policy.relevant_to_user_ids(event)
        target_ids.discard(event.creator_id)
        await self._add_active_recipients(recipients, target_ids)

        # Reply on yours (resource): a comment/mark on a resource directly targets its creator and
        # assignee, the same audience the push side reaches. This is what re-surfaces a row the
        # owner archived — plain force-include/level reach stays on the gated path and would not.
        if event.action in policy.creator_and_assignee_reply_actions:
            owner_ids = self._creator_and_assignee_ids()
            owner_ids.discard(event.creator_id)  # the actor's own reply never force-alerts them
            await self._add_active_recipients(recipients, owner_ids)

        if event.action == EventAction.ASSIGNED:
            # The point-in-time assignee from the event, not workspace.assignee_id (which can
            # drift if the resource is reassigned before this async job runs). The router stores
            # the assignee's field_values, so the id is JSON-serialized to a string. `or {}` (not
            # a get-default) guards an explicit {"assignee": None}, which would break `.get`.
            assignee_id = ((event.details or {}).get("assignee") or {}).get("id")
            # The assignee is a direct recipient even when they assigned themselves: a
            # self-assignment is a direct ask to yourself, so InboxUpdate.for_event (a
            # self-target: sender + direct recipient) forces the row unread, exactly like a
            # self-mention.
            if (
                assignee_id
                and (assignee := await User.get_or_none(id=assignee_id, using_db=self.using_db))
                and not assignee.is_deleted
            ):
                recipients.setdefault(assignee.id, assignee)

        # The actor is excluded — replying in your own thread doesn't force your own row unread
        # (that's the sender's normal REFRESH_CONTENT). Access is enforced by resolve_for_inbox,
        # so this only needs to load the participants.
        participant_ids = await policy.thread_participant_ids(event.recordable_id, self.using_db)
        participant_ids.discard(event.creator_id)
        await self._add_active_recipients(recipients, participant_ids)

        return list(recipients.values())

    def _all_level_users(self) -> dict[UUID, User]:
        """Candidates reached by subscription level — those whose effective level is ALL and who
        can access the resource. The level-based fan-out a direct-ask-only event suppresses."""
        collaboration = self._resolved_resource.collaboration
        return {
            user_id: user
            for user_id, user in self._candidates.items()
            if self._level_for(user_id) == SubscriptionLevel.ALL and collaboration.can_be_accessed_by(user)
        }

    async def resolve_for_inbox(
        self,
        event: Event | None = None,
        *,
        direct_recipients: list[User],
    ) -> list[User]:
        """Users this event reaches in the inbox.

        ALL-level subscribers + direct recipients + everyone the resource reaches
        force-included by policy (via `notification_policy.force_include_for_inbox`
        — collaborators for a DM/email thread, every org accessor for an announcement).
        Reach only — the sender is included here; whether their row alerts or just
        refreshes is decided by `InboxUpdate.for_event` at the mailbox layer, not here.
        Existing-row continuity is likewise layered on there (it needs MailboxEntry,
        which the resolver can't import).

        `direct_recipients` (the users an event personally targets — @mention recipients
        plus the assignee of an assignment) carries User objects rather than UUIDs because
        they may not be collaborators of the workspace (org-wide mentions, or a stale mention
        after collaborator removal). The production caller (`_update_inbox_rows_for_event`)
        derives them via `direct_recipients_for`; passing an explicit list is the test/override
        path.
        """
        await self._load(None)
        collaboration = self._resolved_resource.collaboration
        action = event.action if event else None
        direct_only = self._resolved_policy.reaches_only_direct_recipients(action)
        reached: dict[UUID, User] = {} if direct_only else self._all_level_users()
        for user in direct_recipients:
            if user.is_deleted or not collaboration.can_be_accessed_by(user):
                continue
            reached.setdefault(user.id, user)
        if self._resolved_policy.force_include_for_inbox(action):
            # Reach everyone regardless of tier by iterating the full candidate set (org accessors
            # for a broadcast, collaborators for a DM/email thread) rather than only collaborators.
            # For a broadcast, `_candidates` is drawn from org accessors, which — unlike the tiered
            # path above — aren't filtered for logged-in/soft-delete state, so exclude those here:
            # an announcement shouldn't newly surface to an account that can't receive it. For a
            # DM/email thread `broadcast` is False and `_candidates` is exactly the collaborators,
            # so this stays a no-op for them.
            broadcast = self._resolved_policy.broadcasts_to_organization
            for user in self._candidates.values():
                if not collaboration.can_be_accessed_by(user):
                    continue
                if broadcast and (user.is_deleted or user.last_logged_in_at is None):
                    continue
                reached.setdefault(user.id, user)
        return list(reached.values())

    async def state_for(self, user_id: UUID) -> "SubscriptionState":
        """Resolve the effective subscription state for a single user.

        Targeted queries on the cold path; reads from cached state when
        the resolver has already loaded the full candidate set.
        """
        if self._loaded:
            return SubscriptionState(level=self._level_for(user_id), source=self._source_for(user_id))

        await self._ensure_resource()
        resource_type = self.workspace.resource_type
        policy = self._resolved_policy
        group_id = policy.notification_group_id
        pref_filters = SubscriptionPreference.filters

        subscription_q = (
            Subscription.filter(workspace_id=self.workspace.id, subscriber_id=user_id).using_db(self.using_db).first()
        )
        global_pref_q = (
            SubscriptionPreference.filter(
                pref_filters.for_resource_type(resource_type),
                subscriber_id=user_id,
            )
            .using_db(self.using_db)
            .first()
        )

        if group_id:
            membership_q = GroupMember.filter(group_id=group_id, user_id=user_id).using_db(self.using_db).exists()
            mute_q = policy.muted_user_ids(using_db=self.using_db)
            subscription, is_member, muted_user_ids, global_pref = await asyncio.gather(
                subscription_q, membership_q, mute_q, global_pref_q
            )
            is_muted = user_id in muted_user_ids
        else:
            subscription, global_pref = await asyncio.gather(subscription_q, global_pref_q)
            is_member = is_muted = False

        if subscription:
            return SubscriptionState(level=subscription.level, source=SubscriptionSource.RESOURCE)
        if self._resolved_resource.creator_id == user_id:
            return SubscriptionState(level=SubscriptionLevel.ALL, source=SubscriptionSource.CREATOR)
        is_org_wide = policy.broadcasts_to_organization and policy.notification_group_id is None

        def resolve_global_level(pref: "SubscriptionPreference") -> SubscriptionLevel:
            if pref.default_level == SubscriptionLevel.BROADCASTS:
                return SubscriptionLevel.ALL if is_org_wide else SubscriptionLevel.RELEVANT_ONLY
            return pref.default_level

        if is_member:
            if is_muted:
                return SubscriptionState(
                    level=SubscriptionLevel.RELEVANT_ONLY, source=SubscriptionSource.GROUP_MEMBERSHIP
                )
            return SubscriptionState(level=SubscriptionLevel.ALL, source=SubscriptionSource.GROUP_MEMBERSHIP)
        if global_pref:
            return SubscriptionState(level=resolve_global_level(global_pref), source=SubscriptionSource.GLOBAL)
        return SubscriptionState(level=SubscriptionLevel.RELEVANT_ONLY, source=SubscriptionSource.NONE)

    def _source_for(self, user_id: UUID) -> "SubscriptionSource":
        """Source attribution when resolved to ALL — most explicit opt-in wins.

        GLOBAL fires only when the user's global preference is what put them at ALL:
        either an explicit ALL pref, or BROADCASTS on an org-wide post. A non-ALL
        global pref (e.g. RELEVANT_ONLY on a member of the post's group) shouldn't
        steal attribution from GROUP_MEMBERSHIP — membership is what resolved them.
        """
        if self._subscription_levels.get(user_id) == SubscriptionLevel.ALL:
            return SubscriptionSource.RESOURCE
        global_level = self._global_pref_levels.get(user_id)
        if global_level == SubscriptionLevel.ALL or (
            global_level == SubscriptionLevel.BROADCASTS and self._is_org_wide_broadcast
        ):
            return SubscriptionSource.GLOBAL
        if self._resolved_resource.creator_id == user_id:
            return SubscriptionSource.CREATOR
        if user_id in self._group_member_ids:
            return SubscriptionSource.GROUP_MEMBERSHIP
        return SubscriptionSource.NONE

    async def _load(self, exclude_user_id: UUID | None) -> None:
        if self._loaded:
            return
        await self._ensure_resource()
        await self.workspace.fetch_related("collaborators__user", using_db=self.using_db)
        self._candidates = {
            collaborator.user_id: collaborator.user
            for collaborator in self.workspace.collaborators
            if collaborator.user is not None
        }
        await self._add_group_members()
        self._is_org_wide_broadcast = (
            self._resolved_policy.broadcasts_to_organization and self._resolved_policy.notification_group_id is None
        )
        if self._resolved_policy.broadcasts_to_organization:
            await self._add_organization_accessors()
        if exclude_user_id:
            self._candidates.pop(exclude_user_id, None)
            self._group_member_ids.discard(exclude_user_id)
        if self._candidates:
            await self._fetch_levels()
        self._loaded = True

    async def _add_organization_accessors(self) -> None:
        accessors = await self._resolved_resource.collaboration.accessors.using_db(self.using_db)
        self._candidates.update({user.id: user for user in accessors})

    async def _add_group_members(self) -> None:
        group_id = self._resolved_policy.notification_group_id
        if not group_id:
            return
        member_ids = cast(
            list[UUID],
            await GroupMember.filter(group_id=group_id, user__deleted_at__isnull=True)
            .using_db(self.using_db)
            .values_list("user_id", flat=True),
        )
        self._group_member_ids = set(member_ids)
        missing = [uid for uid in member_ids if uid not in self._candidates]
        if missing:
            for user in await User.filter(id__in=missing).using_db(self.using_db):
                self._candidates[user.id] = user

    async def _fetch_levels(self) -> None:
        candidate_ids = list(self._candidates.keys())
        resource_type = self.workspace.resource_type

        sub_filters = Subscription.filters
        pref_filters = SubscriptionPreference.filters

        subscriptions_q = Subscription.filter(
            sub_filters.by_workspace(self.workspace.id),
            sub_filters.by_subscribers(candidate_ids),
        ).using_db(self.using_db)
        global_prefs_q = SubscriptionPreference.filter(
            pref_filters.for_resource_type(resource_type),
            pref_filters.by_subscribers(candidate_ids),
        ).using_db(self.using_db)
        muted_user_ids_q = self._resolved_policy.muted_user_ids(using_db=self.using_db)

        subscriptions, global_prefs, muted_user_ids = await asyncio.gather(
            subscriptions_q, global_prefs_q, muted_user_ids_q
        )

        self._subscription_levels = {s.subscriber_id: s.level for s in subscriptions}
        self._global_pref_levels = {p.subscriber_id: p.default_level for p in global_prefs}
        self._group_muted_ids = muted_user_ids & self._group_member_ids

    def _level_for(self, user_id: UUID) -> SubscriptionLevel:
        if user_id in self._subscription_levels:
            return self._subscription_levels[user_id]
        if self._resolved_resource.creator_id == user_id:
            return SubscriptionLevel.ALL
        if user_id in self._group_member_ids:
            if user_id in self._group_muted_ids:
                return SubscriptionLevel.RELEVANT_ONLY
            return SubscriptionLevel.ALL
        return self._effective_global_level(user_id)

    def _effective_global_level(self, user_id: UUID) -> SubscriptionLevel:
        level = self._global_pref_levels.get(user_id, SubscriptionLevel.RELEVANT_ONLY)
        if level == SubscriptionLevel.BROADCASTS:
            return SubscriptionLevel.ALL if self._is_org_wide_broadcast else SubscriptionLevel.RELEVANT_ONLY
        return level


#
# Mentions
#
#

MENTION_PATTERN = r"@\[([^\]]+)\]"
# A mention's stored content becomes the notification body (email + push preview).
# Cap it to a window around the mention marker so a mention buried in a long
# document body doesn't email the entire document. Comfortably larger than any
# ordinary comment, so short-content mentions are stored whole.
MENTION_EXCERPT_LENGTH = 500


class Mention(RecordModel):
    recordable_gid = GlobalIDField()
    content = fields.TextField()
    delivered_at: datetime | None = fields.DatetimeField(null=True)
    mentioned: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    mentioned_id: Annotated[UUID, "foreign key to who was mentioned"]
    creator: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="mentions_created"
    )
    creator_id: Annotated[UUID, "foreign key to who mentioned"]
    event: fields.ForeignKeyNullableRelation["Event"] = fields.ForeignKeyField(
        "convictional.Event", on_delete=fields.SET_NULL, null=True
    )
    event_id: Annotated[UUID | None, "foreign key to event"]
    workspace: fields.ForeignKeyRelation[Workspace] = fields.ForeignKeyField("convictional.Workspace")
    workspace_id: Annotated[UUID, "foreign key to workspace"]

    class Meta:
        ordering = ["-created_at"]
        indexes = (("workspace_id"),)

    @property
    def is_delivered(self):
        return self.delivered_at is not None

    async def mark_delivered(self, using_db: BaseDBAsyncClient | None = None):
        self.delivered_at = datetime.now(UTC)
        await self.save(using_db=using_db)


@dataclass
class MentionResolver:
    recordable: RecordModel
    workspace: Workspace
    content: str
    creator_id: UUID
    mentions: list[Mention] = field(default_factory=list)

    async def resolve(self, using_db: BaseDBAsyncClient | None = None):
        if not self.possible_mentions:
            return

        for user in await self.possible_users(using_db=using_db):
            if user.display_name in self.possible_mentions:
                mention = await Mention.get_or_init(
                    recordable_gid=self.recordable.global_id,
                    mentioned=user,
                    mentioned_id=user.id,
                    creator_id=self.creator_id,
                    workspace_id=self.workspace.id,
                    using_db=using_db,
                )

                if mention.is_new:
                    # Store a channel-agnostic excerpt with raw @[Name] markers intact;
                    # each channel renders the markers itself at send time.
                    mention.content = preview_excerpt(self.content, f"@[{user.display_name}]", MENTION_EXCERPT_LENGTH)

                self.mentions.append(mention)

    @property
    def possible_mentions(self):
        return re.findall(MENTION_PATTERN, self.content)

    async def possible_users(self, using_db: BaseDBAsyncClient | None = None):
        await self.workspace.fetch_related("collaborators", using_db=using_db)
        return await self.workspace.resource.collaboration.accessors.using_db(using_db)


#
# Comments
#
#


@dataclass(frozen=True)
class CommentReaction:
    type: ReactionType
    label: str
    emoji: str

    @classmethod
    def by_type(cls, reaction_type: ReactionType):
        return next(reaction for reaction in COMMENT_REACTIONS if reaction.type == reaction_type)


COMMENT_REACTIONS = [
    CommentReaction(ReactionType.THUMBS_UP, "thumbs up", "👍"),
    CommentReaction(ReactionType.THUMBS_DOWN, "thumbs down", "👎"),
    CommentReaction(ReactionType.TEARS_OF_JOY, "face with tears of joy", "😂"),
    CommentReaction(ReactionType.PARTY_POPPER, "party popper", "🎉"),
    CommentReaction(ReactionType.FROWNING_FACE, "slightly frowning face", "🙁"),
    CommentReaction(ReactionType.HEART, "red heart", "❤️"),
    CommentReaction(ReactionType.ROCKET, "rocket", "🚀"),
    CommentReaction(ReactionType.EYES, "eyes", "👀"),
]


class CommentMixin(RecordModel):
    comment_topic: ClassVar[str]
    comment_topic_param: ClassVar[str]

    content = fields.TextField(default="", description="protected_column")
    reactions: dict[ReactionType, list[UUID]] = JSONField(default={})
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    user_id: Annotated[UUID, "foreign key to user"]
    link_preview: fields.ForeignKeyNullableRelation["LinkPreview"] = fields.ForeignKeyField(
        "convictional.LinkPreview", null=True, on_delete=fields.SET_NULL
    )
    link_preview_id: Annotated[UUID | None, "foreign key to link_preview"]

    class Meta:
        abstract = True
        indexes = (("link_preview_id",),)

    def topic(self) -> Topic:
        parent_id = getattr(self, self.comment_topic_param)
        return Topic(self.comment_topic, **{self.comment_topic_param: str(parent_id)})

    async def broadcast_reaction_update(self) -> None:
        await self.topic().broadcast(updated_comment_id=str(self.id))

    async def broadcast_created(self) -> None:
        await self.topic().broadcast(new_comment_id=str(self.id), author_id=str(self.user_id))

    async def broadcast_edited(self) -> None:
        await self.topic().broadcast(edited_comment_id=str(self.id), author_id=str(self.user_id))

    async def broadcast_deleted(self) -> None:
        await self.topic().broadcast(deleted_comment_id=str(self.id), author_id=str(self.user_id))

    @property
    def was_edited(self):
        return (self.updated_at - self.created_at) > timedelta(seconds=10)

    def toggle_reaction(self, user_id: UUID, reaction_type: ReactionType):
        if reaction_type not in self.reactions:
            self.reactions[reaction_type] = []

        if user_id in self.reactions[reaction_type]:
            self.reactions[reaction_type].remove(user_id)
        else:
            self.reactions[reaction_type].append(user_id)

    @property
    def attachments(self):
        return Attachment.filter(comment_gid=self.global_id)

    async def cleanup_unreferenced_attachments(
        self, using_db: BaseDBAsyncClient | None = None, *, include_non_images: bool = False
    ):
        attachments = await Attachment.filter(comment_gid=self.global_id).prefetch_related("file").using_db(using_db)

        if not attachments:
            return

        html_content = self.content or ""

        # Inline images embed their download URL in the content everywhere, so an image absent
        # from it was removed by the author and is always eligible for cleanup. Non-image files
        # only embed a [name](url) link on surfaces that drive removal off the content (chat file
        # cards, via claim_for_comment); elsewhere they render from a separate attachment list
        # decoupled from content, where the URL-substring check would wrongly delete a file the
        # author never removed — so those callers stay images-only.
        for attachment in attachments:
            if not include_non_images and not attachment.is_image:
                continue
            if not attachment._is_referenced_in_html(html_content):
                await attachment.delete(using_db=using_db)


#
# Decisions
#
#


class Decision(RecordModel):
    workspace: fields.ForeignKeyRelation[Workspace] = fields.ForeignKeyField(
        "convictional.Workspace", related_name="decisions"
    )
    workspace_id: Annotated[UUID, "foreign key to workspace"]
    # The anchor comment, referenced polymorphically — the comment types live in
    # separate tables, so a real FK can't span them. No FK cascade: orphan cleanup
    # is explicit (see delete_decision_for_comment and Post.publish).
    comment_gid = GlobalIDField(unique=True)
    decided_by: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User",
        null=True,
        on_delete=fields.SET_NULL,
        related_name="decisions",
    )
    decided_by_id: Annotated[UUID | None, "foreign key to user who recorded the decision"]
    decided_at = fields.DatetimeField()

    class Meta:
        ordering = ["decided_at"]
        indexes = (("workspace_id", "decided_at"),)

    @classmethod
    async def broadcast_change(cls, workspace_id: UUID, actor_id: UUID) -> None:
        # Workspace-scoped signal: "the set of decisions changed" (deliberately
        # plural — the workspace's decision set, not one comment). Clients refetch
        # the decisions list rather than diffing payloads. actor_id is
        # informational only — no sender-skip: the recording tab's other windows
        # must update too.
        await Topic("workspace_events", workspace_id=workspace_id).broadcast(
            action=ChannelEventAction.DECISIONS_CHANGED.value,
            actor_id=str(actor_id),
        )

    def clearable_by(self, user: User) -> bool:
        # Only the decider or an org admin may undecide. decided_by_id is null once
        # the decider's account is deleted (SET_NULL above), leaving only admins to
        # clear — `None != user.id` keeps non-admins out.
        return self.decided_by_id == user.id or user.is_admin


# Registered for each comment type that can anchor a decision (the concrete models
# live in the workspaces layer, which imports this handler). Tortoise post_delete
# fires only on instance .delete(), not queryset/bulk deletes — bulk hard-delete
# paths (Post.publish) must clean up explicitly.
async def delete_decision_for_comment(
    sender: type[CommentMixin],
    instance: CommentMixin,
    using_db: BaseDBAsyncClient | None,
) -> None:
    # Registered on post_delete for every comment type. For soft-deletable senders
    # (ChatMessage, PostComment, GoalComment, EmailThreadComment) a normal user delete is
    # a save(), so this only fires on a true hard delete/cascade — the soft-delete path
    # instead keeps the decision alive as a tombstone (IndexDecisionJob drops its stale
    # searchable body once the anchor is soft-deleted). This stays as the hard-delete safety net.
    # Delete each decision as an instance (not a queryset) so its DELETE fires the
    # post_delete signal, which the Decision DELETE observer turns into index cleanup.
    decisions = await Decision.filter(comment_gid=instance.global_id).using_db(using_db)
    for decision in decisions:
        await decision.delete(using_db=using_db)


#
# Attachments
#
#


class AttachmentFilters:
    @classmethod
    def by_organization(cls, organization_id: UUID) -> Q:
        return Q(user__organization_id=organization_id)

    @classmethod
    def unclaimed(cls, cutoff_time: datetime) -> Q:
        return Q(claim_id__isnull=False, comment_gid__isnull=True, created_at__lt=cutoff_time)


class Attachment(RecordModel):
    title = fields.TextField()
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User")
    user_id: Annotated[UUID, "foreign key to user"]
    file: fields.ForeignKeyRelation[FileReference] = fields.ForeignKeyField(
        "convictional.FileReference", related_name="attachments"
    )
    file_id: Annotated[UUID, "foreign key to file"]
    workspace: fields.ForeignKeyNullableRelation[Workspace] = fields.ForeignKeyField(
        "convictional.Workspace", related_name="attachments", null=True
    )
    workspace_id: Annotated[UUID | None, "foreign key to workspace"]
    summary: str | None = fields.TextField(null=True)
    comment_gid = GlobalIDField(null=True)
    claim_id: UUID | None = fields.UUIDField(null=True)
    filters = AttachmentFilters()

    class Meta:
        ordering = ["created_at"]
        indexes = (
            ("workspace_id",),
            ("comment_gid", "claim_id", "created_at"),
        )

    @property
    def is_image(self):
        return self.file.content_type.startswith("image/")

    @property
    def is_pdf(self):
        return self.file.content_type == "application/pdf"

    @property
    def is_document(self):
        return self.file.content_type in [
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.ms-excel",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/plain",
        ]

    async def copy(self, data: dict[str, Any] = {}, using_db: BaseDBAsyncClient | None = None):
        await self.fetch_related("file", using_db=using_db)
        file_copy = await self.file.copy(using_db=using_db)
        return await super().copy({**data, "file_id": file_copy.id}, using_db=using_db)

    @property
    def download_urls(self) -> list[str]:
        urls = [
            urljoin(
                str(settings.base_url),
                f"workspaces/attachments/{self.id}/download",
            )
        ]

        # If claimed to a workspace, include the more specific URL
        if self.workspace_id:
            urls.append(
                urljoin(
                    str(settings.base_url),
                    f"workspaces/{self.workspace_id}/attachments/{self.id}/download",
                )
            )

        return urls

    def _is_referenced_in_html(self, html_content: str) -> bool:
        """Check if this attachment is referenced in the given HTML content.

        Checks if the attachment ID appears in any attachment URLs in the HTML.
        Used to determine if inline attachments are still in use.
        """
        if not html_content:
            return False

        return f"attachments/{self.id}" in html_content

    @classmethod
    async def claim_for_live_document_content(
        cls,
        workspace_id: UUID,
        markdown: str,
        *,
        owner_id: UUID | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> int:
        # Document image uploads carry a non-null `claim_id` that no document save path
        # clears (unlike comments, which call UnclaimedAttachments.claim_for_comment).
        # Without this sweep, CleanupUnclaimedAttachmentsJob hard-deletes images that
        # are still referenced in the document's Yjs markdown.
        #
        # owner_id also claims that user's org-wide uploads (workspace_id IS NULL) referenced
        # in the content, promoting them into this workspace. Publishing a post drafted from the
        # inline composer is the case that needs it: those uploads never carry a workspace_id and
        # the publish path has no claim_id to run UnclaimedAttachments.claim, so without this they
        # stay unclaimed and get swept.
        if not markdown:
            return 0

        scope = Q(workspace_id=workspace_id)
        if owner_id:
            scope |= Q(workspace_id__isnull=True, user_id=owner_id)
        candidates = await cls.filter(scope, claim_id__isnull=False, comment_gid__isnull=True).using_db(using_db).all()
        return await cls._claim_referenced(candidates, markdown, workspace_id, using_db=using_db)

    @classmethod
    async def claim_referenced_in_content(
        cls,
        workspace_id: UUID,
        user_id: UUID,
        content: str,
        *,
        using_db: BaseDBAsyncClient | None = None,
    ) -> int:
        # Same content-referenced approach as claim_for_live_document_content: only clear
        # claim_id for uploads actually referenced in the saved markdown. Uploads the author
        # never referenced (or later removed) keep their claim_id, so CleanupUnclaimedAttachmentsJob
        # can still sweep them — an abandoned draft's attachments are reclaimed rather than
        # retained forever. Scoped to the uploading user so another member's uploads can't be
        # claimed by referencing their URL.
        if not content:
            return 0

        candidates = (
            await cls.filter(
                workspace_id=workspace_id,
                user_id=user_id,
                claim_id__isnull=False,
                comment_gid__isnull=True,
            )
            .using_db(using_db)
            .all()
        )
        return await cls._claim_referenced(candidates, content, workspace_id, using_db=using_db)

    @classmethod
    async def _claim_referenced(
        cls,
        candidates: list["Attachment"],
        content: str,
        workspace_id: UUID,
        *,
        using_db: BaseDBAsyncClient | None = None,
    ) -> int:
        # Clears claim_id for the candidates actually referenced in the saved content, leaving
        # unreferenced ones sweepable. Writing workspace_id is a no-op for candidates already
        # scoped to it and promotes org-wide uploads (workspace_id IS NULL) into the workspace;
        # each caller's candidate query only surfaces this workspace's rows or unscoped ones, so
        # this never reassigns a foreign workspace.
        to_claim = [a.id for a in candidates if str(a.id) in content]
        if to_claim:
            await cls.filter(id__in=to_claim).using_db(using_db).update(claim_id=None, workspace_id=workspace_id)
        return len(to_claim)


#
# Visits
#
#


class VisitFilters:
    @classmethod
    def by_user(cls, user_id: UUID) -> Q:
        return Q(user_id=user_id)

    @classmethod
    def by_user_workspace(cls, user_id: UUID, workspace_id: UUID) -> Q:
        return Q(user_id=user_id, workspace_id=workspace_id)


class Visit(RecordModel):
    """The single per-(user, workspace) read-state primitive.

    This is what every "read state" / "last seen" / "viewed" / "unread" / "what's new"
    feature on a workspace resource is built from — posts, goals, documents, email threads,
    chats, meetings all record the same Visit. Reuse it rather than adding a parallel store.

    Timestamps: `updated_at` (from RecordModel) is the *current* last-view time; `last_visit_at`
    is the *prior* visit. `touch()` shifts updated_at → last_visit_at, so read consumers compare
    against `updated_at` for "since I last looked" (see ViewStateResolver and posts.WhatsNew).
    """

    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField("convictional.User", related_name="visits")
    user_id: Annotated[UUID, "foreign key to user"]
    workspace: fields.ForeignKeyRelation["Workspace"] = fields.ForeignKeyField(
        "convictional.Workspace", related_name="visits"
    )
    workspace_id: Annotated[UUID, "foreign key to workspace"]
    last_visit_at: datetime | None = fields.DatetimeField(null=True)
    last_event: fields.ForeignKeyNullableRelation["Event"] = fields.ForeignKeyField(
        "convictional.Event", on_delete=fields.SET_NULL, null=True
    )
    last_event_id: Annotated[UUID | None, "foreign key to last event"]
    filters = VisitFilters()

    class Meta:
        ordering = ["-updated_at"]
        unique_together = ("user_id", "workspace_id")

    @classmethod
    async def record(
        cls,
        user_id: UUID,
        workspace_id: UUID,
        last_event_id: UUID | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ):
        """The canonical write entry point for read state — idempotent per (user, workspace).

        Every recording surface (the /api/workspaces/{id}/visits endpoint, the HTMX _track
        partial, the React useWorkspaceVisitRecording hook) funnels here. Swallows the
        concurrent-create IntegrityError so callers never race on first visit.
        """
        try:
            async with transaction(using_db=using_db) as connection:
                visit = await cls.get_or_init(user_id=user_id, workspace_id=workspace_id, using_db=connection)
                visit.touch(last_event_id)
                await visit.save(using_db=connection)
        except IntegrityError:
            logger.warning(f"Failed to record visit for user {user_id} and workspace {workspace_id}")
            pass

    def touch(self, last_event_id: UUID | None = None):
        self.last_visit_at = self.updated_at if self.updated_at else self.created_at or datetime.now(UTC)
        self.updated_at = datetime.now(UTC)
        if last_event_id:
            self.last_event_id = last_event_id

    @classmethod
    async def rewind_cursor(
        cls,
        user_id: UUID,
        workspace_id: UUID,
        last_event_id: UUID | None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        """Reposition an existing visit's event cursor without counting as a new view.

        Unlike `record`, this leaves the view timestamps untouched and only moves
        `last_event_id` — used to rewind chat's read cursor on mark-as-unread. No-op when the
        user has no visit yet. Keeps cursor rewinds on the Visit write API instead of an ad-hoc save.
        """
        visit = await cls.filter(user_id=user_id, workspace_id=workspace_id).using_db(using_db).first()
        if visit:
            visit.last_event_id = last_event_id
            await visit.save(update_fields=["last_event_id"], using_db=using_db)


class ViewStateResolver:
    """The single read path from Visit rows to CollaboratorViewState.

    Every "seen-by" / "last viewed" / "caught up" / "what's new" / "unread" reader resolves
    view state through here — do not query Visit directly elsewhere. Prefetches `last_event`
    so consumers get the cursor event's timestamp (last_viewed_event_at) without a second
    query. A (user, workspace) with no Visit resolves to the unviewed default.
    """

    @classmethod
    async def for_workspace(
        cls, workspace_id: UUID, user_ids: list[UUID], using_db: BaseDBAsyncClient | None = None
    ) -> dict[UUID, CollaboratorViewState]:
        """Per-collaborator view state on one workspace, keyed by user_id. One bulk query."""
        if not user_ids:
            return {}
        visits = (
            await Visit.filter(workspace_id=workspace_id, user_id__in=user_ids)
            .prefetch_related("last_event")
            .using_db(using_db)
        )
        by_user = {visit.user_id: visit for visit in visits}
        return {user_id: cls._state(by_user.get(user_id)) for user_id in user_ids}

    @classmethod
    async def all_visitors_for_workspace(
        cls, workspace_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> dict[UUID, CollaboratorViewState]:
        """View state for every user who has visited this workspace, keyed by user_id. One bulk query.

        Unlike `for_workspace`, the caller supplies no user_ids — this is the seen-by population, which
        spans all visitors (collaborators and org-member viewers alike), not just a known roster.
        """
        visits = await Visit.filter(workspace_id=workspace_id).prefetch_related("last_event").using_db(using_db)
        return {visit.user_id: cls._state(visit) for visit in visits}

    @classmethod
    async def for_user(
        cls, user_id: UUID, workspace_ids: list[UUID], using_db: BaseDBAsyncClient | None = None
    ) -> dict[UUID, CollaboratorViewState]:
        """One user's view state across many workspaces, keyed by workspace_id (list reads)."""
        if not workspace_ids:
            return {}
        visits = (
            await Visit.filter(user_id=user_id, workspace_id__in=workspace_ids)
            .prefetch_related("last_event")
            .using_db(using_db)
        )
        by_workspace = {visit.workspace_id: visit for visit in visits}
        return {workspace_id: cls._state(by_workspace.get(workspace_id)) for workspace_id in workspace_ids}

    @classmethod
    async def for_user_in_workspace(
        cls, user_id: UUID, workspace_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> CollaboratorViewState:
        states = await cls.for_workspace(workspace_id, [user_id], using_db=using_db)
        return states[user_id]

    @staticmethod
    def _state(visit: "Visit | None") -> CollaboratorViewState:
        return CollaboratorViewState.from_visit(visit) if visit else CollaboratorViewState.unviewed()


#
# Link Previews
#
#

LINK_PREVIEW_DEFAULT_TTL_DAYS = 7


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


class LinkPreview(RecordModel):
    url = fields.TextField()
    url_hash = fields.CharField(max_length=64, unique=True, db_index=True)
    status = fields.CharEnumField(LinkPreviewStatus, default=LinkPreviewStatus.FAILED, max_length=255)
    type = fields.CharEnumField(LinkPreviewType, default=LinkPreviewType.LINK, max_length=255)
    title = fields.TextField(null=True)
    description = fields.TextField(null=True)
    image_url = fields.TextField(null=True)
    site_name = fields.TextField(null=True)
    oembed_html = fields.TextField(null=True)
    fetched_at = fields.DatetimeField(null=True)
    expires_at = fields.DatetimeField(null=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    async def upsert(cls, url: str, attrs: dict[str, Any], using_db: BaseDBAsyncClient | None = None) -> "LinkPreview":
        now = datetime.now(UTC)
        attrs = {**attrs, "fetched_at": now, "expires_at": now + timedelta(days=LINK_PREVIEW_DEFAULT_TTL_DAYS)}

        link_preview = await cls.filter(url_hash=url_hash(url)).using_db(using_db).first()
        if link_preview:
            link_preview.update_from_dict(attrs)
            await link_preview.save(using_db=using_db)
        else:
            link_preview = await cls.create(url=url, url_hash=url_hash(url), **attrs, using_db=using_db)

        return link_preview

    @property
    def domain(self) -> str:
        parsed = urlparse(self.url)
        return parsed.hostname or self.url

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return True
        return datetime.now(UTC) > self.expires_at

    @classmethod
    async def find_valid(cls, url: str) -> "LinkPreview | None":
        preview = await cls.filter(url_hash=url_hash(url)).first()
        if preview and not preview.is_expired and preview.status != LinkPreviewStatus.FAILED:
            return preview
        return None

    @classmethod
    async def associate(
        cls,
        model_class: "builtins.type[RecordModel]",
        record_id: UUID,
        link_preview_data: tuple[str, dict[str, Any]] | None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        if link_preview_data is None:
            await model_class.filter(id=record_id).using_db(using_db).update(link_preview_id=None)
            return

        url, attrs = link_preview_data
        link_preview: LinkPreview | None
        if attrs:
            link_preview = await cls.upsert(url, attrs, using_db=using_db)
        else:
            link_preview = await cls.filter(url_hash=url_hash(url)).using_db(using_db).first()

        if not link_preview:
            return

        await model_class.filter(id=record_id).using_db(using_db).update(link_preview_id=link_preview.id)
