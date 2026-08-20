from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Annotated, ClassVar, Self, cast
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields
from tortoise.expressions import Q
from tortoise.functions import Count, Max
from tortoise.queryset import QuerySet
from tortoise.signals import post_delete, post_save

from app.models.accounts import Group, GroupMember, Organization, User
from app.models.collaboration.content import Content
from app.models.collaboration.mailbox import (
    AuthoredPreview,
    BaseMailboxEntry,
    BaseMailboxEntryFilters,
    MailboxEntry,
)
from app.models.collaboration.mixins import (
    CloseableFilters,
    CloseableMixin,
    CompletableFilters,
    CompletableMixin,
    SortableMixin,
)
from app.models.collaboration.workspace import (
    Collaborator,
    CommentMixin,
    Event,
    NotificationPolicy,
    WorkspaceMixin,
    WorkspaceMixinFilters,
    delete_decision_for_comment,
)
from config.enums import EmailDelivery, EventAction, GoalStatus, Sharing, SignalStrength
from infra.db import RecordModel, SoftDeleteableFilters, SoftDeleteableMixin
from infra.messaging import Topic


class GoalFilters(CloseableFilters, CompletableFilters, WorkspaceMixinFilters):
    top_level: ClassVar[Q] = Q(parent_id__isnull=True)
    subgoal: ClassVar[Q] = Q(parent_id__isnull=False)
    draft: ClassVar[Q] = Q(activated_at__isnull=True)
    activated: ClassVar[Q] = Q(activated_at__isnull=False)

    @classmethod
    def by_owner(cls, owner_id: UUID) -> Q:
        return Q(owner_id=owner_id)

    @classmethod
    def for_user(cls, user_id: UUID, group_ids: list[UUID]) -> Q:
        if group_ids:
            return Q(owner_id=user_id) | Q(group_id__in=group_ids)
        return Q(owner_id=user_id)

    @classmethod
    def by_planning_list_name(cls, planning_list_name: str) -> Q:
        return Q(planning_list_name=planning_list_name)

    @classmethod
    def by_planning_list(cls, organization_id: UUID, planning_list_name: str) -> Q:
        return (
            cls.by_organization(organization_id)
            & cls.top_level
            & cls.by_planning_list_name(planning_list_name)
            & cls.draft
        )

    @classmethod
    def by_active_open(cls, organization_id: UUID) -> Q:
        return cls.by_organization(organization_id) & cls.activated & cls.open

    @classmethod
    def by_active_open_top_level(cls, organization_id: UUID) -> Q:
        return cls.by_organization(organization_id) & cls.top_level & cls.activated & cls.open


@dataclass
class GoalNotificationPolicy(NotificationPolicy):
    goal: "Goal"

    async def thread_participant_ids(self, comment_id: UUID, using_db: BaseDBAsyncClient | None = None) -> set[UUID]:
        # A goal comment thread is one level deep: a root comment (parent_id is null) plus
        # replies pointing at it. Participants are everyone who authored in that root's thread.
        comment = await GoalComment.filter(id=comment_id).using_db(using_db).first()
        if comment is None:
            return set()
        root_id = comment.parent_id or comment.id
        rows = cast(
            list[UUID],
            await GoalComment.filter(Q(id=root_id) | Q(parent_id=root_id))
            .using_db(using_db)
            .values_list("user_id", flat=True),
        )
        return set(rows)

    def relevant_to_user_ids(self, event: Event) -> set[UUID]:
        # An update request is a direct ask to the goal's owner — "relevant to me" reach that
        # surfaces in their inbox even at RELEVANT_ONLY, without pinning the owner to ALL.
        if event.action == EventAction.GOAL_UPDATE_REQUESTED and self.goal.owner_id:
            return {self.goal.owner_id}
        return set()

    def reaches_only_direct_recipients(self, action: EventAction | None = None) -> bool:
        # The update request reaches the owner (relevant_to_user_ids) and no one else — not the
        # ALL-level group members or subscribers a level-reach event would fan out to.
        return action == EventAction.GOAL_UPDATE_REQUESTED


class Goal(SortableMixin, CloseableMixin, CompletableMixin, WorkspaceMixin, RecordModel):
    title: str | None = fields.TextField(null=True)  # type: ignore[assignment]
    description: str = fields.TextField(null=False)
    sharing = fields.CharEnumField(Sharing, default=Sharing.ORGANIZATION, max_length=255)
    target_date: date | None = fields.DateField(null=True)
    start_date: date | None = fields.DateField(null=True)
    completed_at: datetime | None = fields.DatetimeField(null=True)
    activated_at: datetime | None = fields.DatetimeField(null=True)
    status: GoalStatus = fields.CharEnumField(GoalStatus, default=GoalStatus.ON_TRACK, max_length=255)
    # null = progress isn't tracked for this goal (distinct from a tracked 0%).
    progress: float | None = fields.FloatField(null=True)
    planning_list_name: str | None = fields.TextField(null=True)
    extras: dict[str, str] = fields.JSONField(default=dict)

    owner: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User", null=True, related_name="owned_goals", on_delete=fields.SET_NULL
    )
    owner_id: Annotated[UUID | None, "foreign key to owner user"]
    group: fields.ForeignKeyNullableRelation[Group] = fields.ForeignKeyField(
        "convictional.Group", null=True, related_name="goals", on_delete=fields.SET_NULL
    )
    group_id: Annotated[UUID | None, "foreign key to group"]
    parent: fields.ForeignKeyNullableRelation["Goal"] = fields.ForeignKeyField(
        "convictional.Goal", related_name="subgoals", null=True
    )
    parent_id: Annotated[UUID | None, "foreign key to parent goal"]
    subgoals: fields.ReverseRelation["Goal"]
    comments: fields.ReverseRelation["GoalComment"]
    updates: fields.ReverseRelation["GoalUpdate"]
    filters = GoalFilters()
    # Goals are inbox-native (GoalMailboxEntry) — they surface via the mailbox, never legacy email.
    email_delivery = EmailDelivery.SKIP

    # Relations the prompt templates read off a goal (owner, group, and the `goal.subgoals` reverse
    # relation the org system prompt iterates). Centralized so every query that loads a goal for a
    # prompt prefetches the same set — a single missing relation raises NoValuesFetched deep inside
    # Jinja and silently kills LLM generation, so every goal-for-prompt loader prefetches via this.
    PROMPT_CONTEXT_RELATIONS: ClassVar[tuple[str, ...]] = ("owner", "group", "subgoals")

    class Meta:
        ordering = ["position", "-created_at"]
        indexes = (
            ("organization_id",),
            ("parent_id",),
            ("organization_id", "activated_at"),
            ("organization_id", "closed_at"),
            ("organization_id", "parent_id", "activated_at", "closed_at"),
        )

    @property
    def notification_policy(self) -> GoalNotificationPolicy:
        return GoalNotificationPolicy(workspace=self.workspace, goal=self)

    @classmethod
    def notification_policy_class(cls) -> type[GoalNotificationPolicy]:
        return GoalNotificationPolicy

    @classmethod
    async def _get_user_group_ids(cls, user_id: UUID) -> list[UUID]:
        memberships = await GroupMember.filter(user_id=user_id).values_list("group_id", flat=True)
        return cast(list[UUID], memberships)

    @classmethod
    async def for_user(cls, user: User) -> list["Goal"]:
        """
        Fetch goals relevant to a user.

        Priority order:
        1. Goals owned by the user
        2. Goals owned by groups the user belongs to
        3. Top-level organization goals (fallback if user has no direct goals)
        """
        group_ids = await cls._get_user_group_ids(user.id)

        user_goals = await (
            cls.filter(cls.filters.by_organization(user.organization_id))
            .filter(cls.filters.open)
            .filter(cls.filters.for_user(user.id, group_ids))
            .prefetch_related(*cls.PROMPT_CONTEXT_RELATIONS)
            .limit(20)
        )

        if user_goals:
            return list(user_goals)

        org_goals = await (
            cls.filter(cls.filters.by_organization(user.organization_id))
            .filter(cls.filters.open & cls.filters.top_level)
            .prefetch_related(*cls.PROMPT_CONTEXT_RELATIONS)
            .limit(10)
        )

        return list(org_goals)

    @classmethod
    async def exists_for_user(cls, user: User) -> bool:
        """Check if any relevant goals exist for the user."""
        group_ids = await cls._get_user_group_ids(user.id)

        has_user_goals = await (
            cls.filter(cls.filters.by_organization(user.organization_id))
            .filter(cls.filters.open)
            .filter(cls.filters.for_user(user.id, group_ids))
            .exists()
        )

        if has_user_goals:
            return True

        return await (
            cls.filter(cls.filters.by_organization(user.organization_id))
            .filter(cls.filters.open & cls.filters.top_level)
            .exists()
        )

    @classmethod
    async def next_position_in_scope(cls, scope: "QuerySet[Goal]", connection: BaseDBAsyncClient) -> int:
        """Get the next position for a new goal within a scope, using select_for_update for atomicity."""
        result = await (
            scope.using_db(connection).select_for_update().annotate(max_pos=Max("position")).values("max_pos")
        )
        max_position = result[0]["max_pos"] if result else 0
        return (max_position or 0) + 1

    @property
    def is_subgoal(self) -> bool:
        return self.parent_id is not None

    @property
    def subgoals_completed_count(self) -> int:
        return sum(1 for subgoal in self.subgoals if subgoal.is_completed)

    @property
    def subgoals_count(self) -> int:
        return len(self.subgoals)

    @property
    def is_draft(self) -> bool:
        return self.activated_at is None

    @property
    def is_active(self) -> bool:
        return self.activated_at is not None

    @property
    def top_level_comments(self) -> list["GoalComment"]:
        return [comment for comment in self.comments if comment.is_top_level]

    async def fetch_parent_goal(self, using_db: BaseDBAsyncClient | None = None) -> "Goal | None":
        if not self.parent_id:
            return None
        await self.fetch_related("parent__subgoals", using_db=using_db)
        return self.parent

    async def close_as_complete(self, using_db: BaseDBAsyncClient | None = None):
        await self.complete(using_db=using_db)
        return await self.close(using_db=using_db)

    async def activate(self, using_db: BaseDBAsyncClient | None = None):
        self.activated_at = datetime.now(UTC)
        self.planning_list_name = None
        await self.save(using_db=using_db)

        if self.subgoals:
            for subgoal in self.subgoals:
                subgoal.activated_at = datetime.now(UTC)
                subgoal.planning_list_name = None
                await subgoal.save(using_db=using_db)

    async def broadcast_comments_update(self, **data):
        await Topic("goal_comments", goal_id=self.id).broadcast(**data)

    async def broadcast_update(self, additional_views: list[str] | None = None):
        view = self._current_index_view()
        views = [view] if view else []
        if additional_views:
            views.extend(additional_views)
        await Goal.broadcast_index_views(self.organization_id, set(views))
        await Topic("goal_timeline", goal_id=self.id).broadcast()

    @classmethod
    async def broadcast_index_views(cls, organization_id: UUID, views: list[str] | set[str]):
        for view in views:
            await Topic("goals_index", organization_id=organization_id, view=view).broadcast()

    def _current_index_view(self) -> str | None:
        if self.is_draft and self.planning_list_name:
            return self.planning_list_name
        elif self.is_completed and self.closed_at is not None:
            return "completed"
        elif self.closed_at is not None:
            return "closed"
        elif self.is_active:
            return "active"
        return None

    @staticmethod
    def select_priority_sorted(goals: list["Goal"]) -> list["Goal"]:
        # Score each goal by `((n - position_rank) / n) * status_weight` and return
        # the list sorted by score descending. `sorted` is stable, so ties resolve
        # in position-then-created_at order — matching `select_highest_priority`.
        status_weights: dict[GoalStatus, float] = {
            GoalStatus.ON_TRACK: 1.0,
            GoalStatus.AT_RISK: 1.5,
            GoalStatus.OFF_TRACK: 3.0,
        }
        position_sorted = sorted(goals, key=lambda g: (g.position, -g.created_at.timestamp()))
        n = len(position_sorted)
        if n == 0:
            return []
        scored = [(((n - i) / n) * status_weights.get(g.status, 1.0), g) for i, g in enumerate(position_sorted)]
        return [g for _, g in sorted(scored, key=lambda pair: pair[0], reverse=True)]

    @classmethod
    def select_highest_priority(cls, goals: list["Goal"]) -> "Goal":
        return cls.select_priority_sorted(goals)[0]

    @classmethod
    async def top_goal_for_user(
        cls,
        base_queryset: QuerySet["Goal"],
        *,
        user_id: UUID,
        group_ids: list[UUID],
    ) -> tuple["Goal | None", int]:
        # Owned goals are preferred; group goals only fire when the user owns nothing.
        # `pool_size` is the size of the pool the picked goal came from, so callers can
        # compute "other goals like this one" as `pool_size - 1` without re-querying.
        # The caller owns the base queryset (filters + select/prefetch chain) so each
        # call site can pull exactly the related rows it needs to render.
        owned = await base_queryset.filter(owner_id=user_id)
        if owned:
            return cls.select_highest_priority(owned), len(owned)
        if group_ids:
            group_goals = await base_queryset.filter(group_id__in=group_ids)
            if group_goals:
                return cls.select_highest_priority(group_goals), len(group_goals)
        return None, 0

    @classmethod
    async def top_goals_for_users(
        cls, users: list[User], organization_id: UUID
    ) -> tuple[dict[UUID, "Goal"], dict[UUID, int]]:
        user_ids = [user.id for user in users]
        memberships = await GroupMember.filter(user_id__in=user_ids).all()

        group_ids_by_user: dict[UUID, list[UUID]] = {}
        all_group_ids: set[UUID] = set()
        for membership in memberships:
            group_ids_by_user.setdefault(membership.user_id, []).append(membership.group_id)
            all_group_ids.add(membership.group_id)

        goal_filter = Q(owner_id__in=user_ids)
        if all_group_ids:
            goal_filter |= Q(group_id__in=all_group_ids)

        base_filters = (
            cls.filters.by_organization(organization_id)
            & cls.filters.activated
            & cls.filters.open
            & cls.filters.incomplete
        )
        goals = (
            await cls.filter(goal_filter & base_filters)
            .prefetch_related("parent", "owner__avatar_file", "group")
            .all()
        )

        goals_by_user: dict[UUID, list[Goal]] = {}
        goals_by_group: dict[UUID, list[Goal]] = {}
        for goal in goals:
            if goal.owner_id is not None:
                goals_by_user.setdefault(goal.owner_id, []).append(goal)
            if goal.group_id is not None:
                goals_by_group.setdefault(goal.group_id, []).append(goal)

        top_goals: dict[UUID, Goal] = {
            user_id: cls.select_highest_priority(user_goals) for user_id, user_goals in goals_by_user.items()
        }
        extra_goal_counts = {user_id: len(user_goals) - 1 for user_id, user_goals in goals_by_user.items()}

        for user_id, group_ids in group_ids_by_user.items():
            if user_id not in top_goals:
                candidate_goals = [goal for group_id in group_ids for goal in goals_by_group.get(group_id, [])]
                if candidate_goals:
                    top_goals[user_id] = cls.select_highest_priority(candidate_goals)

        return top_goals, extra_goal_counts


class GoalComment(SoftDeleteableMixin, CloseableMixin, CommentMixin, RecordModel):
    comment_topic: ClassVar[str] = "goal_comments"
    comment_topic_param: ClassVar[str] = "goal_id"

    goal: fields.ForeignKeyRelation[Goal] = fields.ForeignKeyField("convictional.Goal", related_name="comments")
    goal_id: Annotated[UUID, "foreign key to goal"]
    parent: fields.ForeignKeyNullableRelation["GoalComment"] = fields.ForeignKeyField(
        "convictional.GoalComment", related_name="replies", null=True
    )
    parent_id: Annotated[UUID | None, "foreign key to parent comment"]
    replies: fields.ReverseRelation["GoalComment"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("goal_id"),)

    async def broadcast_created(self) -> None:
        await self.topic().broadcast(new_comment_id=str(self.id), author_id=str(self.user_id), panel_updated=True)

    async def broadcast_deleted(self) -> None:
        await self.topic().broadcast(deleted_comment_id=str(self.id), panel_updated=True)

    @property
    def is_top_level(self):
        return self.parent_id is None

    @property
    def is_reply(self):
        return self.parent_id is not None


class GoalMailboxEntryFilters(BaseMailboxEntryFilters):
    pass


@dataclass
class GoalMailboxEntry(BaseMailboxEntry):
    resource_model: ClassVar[type[Goal]] = Goal
    entry_filters: ClassVar[type[BaseMailboxEntryFilters]] = GoalMailboxEntryFilters
    goal: Goal

    # `workspace__events` drives the latest-event line-2 preview; `comments` and `updates`
    # resolve its authored comment / posted-update text. Evergreen status/progress/description
    # are read live off the goal at serialize time.
    prefetch_for_sync: ClassVar[tuple[str, ...]] = (
        "workspace__collaborators__user",
        "workspace__events",
        "workspace__attachments",
        "owner",
        "comments",
        "updates",
    )

    @classmethod
    def from_resource(cls, resource: RecordModel) -> Self:
        assert isinstance(resource, Goal)
        return cls(goal=resource)

    @property
    def resource(self) -> Goal:
        return self.goal

    async def touch(self, user: User, *, using_db: BaseDBAsyncClient | None = None) -> None:
        await self.goal.fetch_related(*self.prefetch_for_sync, using_db=using_db)

        if sync := await self.refresh_row_and_mark_unread(user, using_db=using_db):
            await sync.broadcast()

    def _refresh_resource_fields(self, entry: MailboxEntry) -> None:
        entry.title = self.goal.title or ""
        entry.preview = self.goal.description
        entry.is_shared = self.goal.owner_id != entry.owner_id
        self._apply_event_preview(entry)

    def _authored_preview(self, event: "Event") -> "AuthoredPreview | None":
        # A goal comment renders as a chip; a posted update as plain avatar+text (both authored).
        # Everything else falls through to None so the base pins it as an activity line the client
        # phrases from the action + details (see GoalEntryBody), keeping goal strings out of the model.
        match event.action:
            # The newest comment may be hidden (closed/deleted root); fall back to the latest
            # visible one the goal panel would render, else treat it as a plain activity line.
            case EventAction.GOAL_COMMENTED if comment := self._latest_visible_comment():
                return AuthoredPreview(comment.content, comment.user_id, is_comment=True)
            case EventAction.GOAL_UPDATE_POSTED if update := self._event_update(event):
                text = (update.answer_text or "").strip() or "Posted an update"
                return AuthoredPreview(text, update.creator_id, is_comment=False)
            case _:
                return None

    def _event_update(self, event: "Event") -> "GoalUpdate | None":
        return next((update for update in self.goal.updates if update.id == event.recordable_id), None)

    def _latest_visible_comment(self) -> "GoalComment | None":
        # `goal.comments` excludes soft-deleted comments via the NonDeletedManager. The goal show
        # panel renders only open top-level comments and the replies hanging off them, so mirror
        # that: a comment is visible when it's an open root, or a reply whose root is a visible
        # root. This drops closed roots, their replies, and replies orphaned by a deleted root.
        comments = list(self.goal.comments)
        visible_root_ids = {comment.id for comment in comments if comment.is_top_level and comment.is_open}
        visible = [
            comment
            for comment in comments
            if comment.is_open and (comment.is_top_level or comment.parent_id in visible_root_ids)
        ]
        return max(visible, key=lambda comment: comment.created_at, default=None)


class GoalUpdateFilters(CompletableFilters, CloseableFilters, WorkspaceMixinFilters):
    @classmethod
    def by_goal(cls, goal_id: UUID) -> Q:
        return Q(goal_id=goal_id)

    @classmethod
    def for_user(cls, user_id: UUID) -> Q:
        return Q(creator_id=user_id)

    @classmethod
    def pending_for_user(cls, user_id: UUID) -> Q:
        return cls.for_user(user_id) & cls.incomplete & cls.open

    @classmethod
    def pending_for_goal(cls, goal_id: UUID) -> Q:
        return cls.by_goal(goal_id) & cls.incomplete & cls.open

    @classmethod
    def completed_for_goal(cls, goal_id: UUID) -> Q:
        return cls.by_goal(goal_id) & cls.completed


class GoalUpdate(CloseableMixin, CompletableMixin, RecordModel):
    goal: fields.ForeignKeyRelation["Goal"] = fields.ForeignKeyField("convictional.Goal", related_name="updates")
    goal_id: Annotated[UUID, "foreign key to goal"]
    creator: fields.ForeignKeyRelation["User"] = fields.ForeignKeyField(
        "convictional.User", related_name="goal_updates"
    )
    creator_id: Annotated[UUID, "foreign key to user"]
    requested_by: fields.ForeignKeyNullableRelation[User] = fields.ForeignKeyField(
        "convictional.User", null=True, related_name="requested_goal_updates", on_delete=fields.SET_NULL
    )
    requested_by_id: Annotated[UUID | None, "foreign key to requesting user"]
    status: GoalStatus = fields.CharEnumField(GoalStatus, max_length=255)
    progress: float | None = fields.FloatField(null=True)
    question_text: str = fields.TextField(null=False)
    answer_text: str | None = fields.TextField(null=True)

    filters = GoalUpdateFilters()

    class Meta:
        ordering = ["-created_at"]
        indexes = (
            ("goal_id",),
            ("creator_id",),
            ("requested_by_id",),
        )

    @classmethod
    async def pending_for_goal(cls, goal_id: UUID) -> "GoalUpdate | None":
        return await cls.filter(cls.filters.pending_for_goal(goal_id)).first()

    @classmethod
    async def pending_or_new_for_goal(cls, goal: Goal) -> "GoalUpdate":
        return await cls.pending_for_goal(goal.id) or cls(goal=goal)


class GoalAlignmentFilters(SoftDeleteableFilters):
    not_actioned: ClassVar[Q] = Q(pinned_by_id__isnull=True)
    actioned: ClassVar[Q] = Q(pinned_by_id__isnull=False) | Q(deleted_at__isnull=False)

    @classmethod
    def by_organization(cls, organization_id: UUID) -> Q:
        return Q(organization_id=organization_id)

    @classmethod
    def by_goal(cls, goal_id: UUID) -> Q:
        return Q(goal_id=goal_id)

    @classmethod
    def by_content(cls, content_id: UUID) -> Q:
        return Q(content_id=content_id)

    @classmethod
    def stale_for_organization(cls, organization_id: UUID, active_goal_ids: list[UUID]) -> Q:
        return cls.by_organization(organization_id) & cls.not_actioned & ~Q(goal_id__in=active_goal_ids)


class GoalAlignment(SoftDeleteableMixin, RecordModel):
    content: fields.ForeignKeyRelation[Content] = fields.ForeignKeyField(
        "convictional.Content", related_name="goal_alignments", on_delete=fields.CASCADE
    )
    content_id: Annotated[UUID, "foreign key to content"]
    goal: fields.ForeignKeyRelation[Goal] = fields.ForeignKeyField(
        "convictional.Goal", related_name="alignments", on_delete=fields.CASCADE
    )
    goal_id: Annotated[UUID, "foreign key to goal"]
    content_indexed_at = fields.DatetimeField()
    signal = fields.CharEnumField(SignalStrength, max_length=255)
    alignment_score = fields.FloatField()
    description = fields.TextField()
    pinned_by: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "convictional.User", null=True, related_name="pinned_goal_alignments", on_delete=fields.SET_NULL
    )
    pinned_by_id: Annotated[UUID | None, "foreign key to user who pinned"]
    created_by: fields.ForeignKeyRelation[User] | None = fields.ForeignKeyField(
        "convictional.User", null=True, related_name="created_goal_alignments", on_delete=fields.SET_NULL
    )
    created_by_id: Annotated[UUID | None, "foreign key to user who created"]
    organization: fields.ForeignKeyRelation[Organization] = fields.ForeignKeyField(
        "convictional.Organization", related_name="goal_alignments", on_delete=fields.CASCADE
    )
    organization_id: Annotated[UUID, "foreign key to organization"]

    filters = GoalAlignmentFilters()

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("content_id", "goal_id", "content_indexed_at")
        indexes = (
            ("goal_id",),
            ("organization_id",),
            ("organization_id", "goal_id"),
        )

    @property
    def score(self) -> float:
        if self.pinned_by_id:
            return 1.0
        return self.alignment_score


post_delete(GoalComment)(delete_decision_for_comment)


@post_save(Goal)
async def set_subgoal_title_from_parent(
    sender: "type[Goal]",
    instance: Goal,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if not created or not instance.parent_id or instance.title:
        return

    results = await (
        Goal.filter(id=instance.parent_id)
        .annotate(subgoals_total=Count("subgoals"))
        .using_db(using_db)
        .values("title", "subgoals_total")
    )
    if not results or not results[0]["title"]:
        return

    title = f"{results[0]['title']}-{results[0]['subgoals_total']}"
    instance.title = title
    await instance.save(using_db=using_db)


@post_save(Goal)
async def ensure_goal_collaborators(
    sender: "type[Goal]",
    instance: Goal,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if instance.owner_id:
        await Collaborator.get_or_create(
            workspace_id=instance.workspace_id, user_id=instance.owner_id, using_db=using_db
        )

    if instance.group_id:
        group_members = await GroupMember.filter(group_id=instance.group_id).using_db(using_db)
        for member in group_members:
            await Collaborator.get_or_create(
                workspace_id=instance.workspace_id, user_id=member.user_id, using_db=using_db
            )


@post_save(GroupMember)
async def add_new_group_member_as_goal_collaborator(
    sender: "type[GroupMember]",
    instance: GroupMember,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if not created:
        return

    group_goals = await Goal.filter(group_id=instance.group_id).using_db(using_db)
    for goal in group_goals:
        await Collaborator.get_or_create(workspace_id=goal.workspace_id, user_id=instance.user_id, using_db=using_db)
