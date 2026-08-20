from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, ClassVar, Self, cast
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields
from tortoise.expressions import Subquery
from tortoise.queryset import Q
from tortoise.signals import post_delete, post_save

from app.models.accounts import Group, GroupMember, User
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import (
    AuthoredPreview,
    BaseMailboxEntry,
    BaseMailboxEntryFilters,
    Mailbox,
    MailboxEntry,
)
from app.models.collaboration.mixins import AnnotationMixin, ResolvableMixin
from app.models.collaboration.workspace import (
    Attachment,
    Collaborator,
    CommentMixin,
    Decision,
    Event,
    NotificationPolicy,
    Workspace,
    WorkspaceMixin,
    WorkspaceMixinFilters,
    delete_decision_for_comment,
)
from config.enums import EmailDelivery, EventAction, Sharing, SubscriptionLevel
from infra.db import GlobalID, RecordModel, SoftDeleteableMixin, transaction
from infra.messaging import Topic


@dataclass
class PostNotificationPolicy(NotificationPolicy):
    post: "Post"

    default_subscription_level: ClassVar[SubscriptionLevel] = SubscriptionLevel.BROADCASTS

    @property
    def notification_group_id(self) -> UUID | None:
        return self.post.group_id

    @property
    def broadcasts_to_organization(self) -> bool:
        # Grouped posts still broadcast: org members with global ALL get an inbox entry.
        # In-group mutes are the opt-out path for group members; non-members fall through
        # to their global Post preference.
        return self.post.sharing.is_organization

    def force_include_for_inbox(self, action: EventAction | None = None) -> bool:
        # An announcement is "sent to everyone, even if unsubscribed" (the composer's own
        # promise): the announce event must land in every reachable member's inbox regardless of
        # their Post preference, so a RELEVANT_ONLY reader can't opt out of it. Scoped to the
        # announce event only — later comments follow normal tier rules, so a RELEVANT_ONLY
        # reader isn't dragged back into the thread by others' replies (that would contradict the
        # preference). Ordinary posts stay tier-gated. Inbox only — announcements never push.
        #
        # resolve_for_inbox honors this by force-including the org accessors an org-wide post
        # already resolves (never-logged-in and deleted accounts filtered out there) — reaching
        # everyone via org-accessor resolution, without writing a per-member row.
        return self.post.is_announcement and action == EventAction.POST_ANNOUNCED

    @property
    def notify_mention_push(self) -> bool:
        # An @mention names you specifically, so a post @mention pushes — same as
        # a chat @mention. Publishing a post (and its subscriber fan-out) does not.
        return True

    # A reply/comment on a post reaches its creator and assignee (the "reply on yours
    # (resource)" audience) on both push and inbox. POST_CREATED is absent: publishing to the
    # org fans out to subscribers but doesn't push. DECIDED rides the same contour by contract
    # ("a mark routes like a new comment").
    creator_and_assignee_reply_actions: ClassVar[frozenset[EventAction]] = frozenset(
        {EventAction.POST_COMMENTED, EventAction.DECIDED}
    )

    async def muted_user_ids(self, using_db: BaseDBAsyncClient | None = None) -> set[UUID]:
        if not self.post.group_id:
            return set()
        rows = cast(
            list[UUID],
            await PostGroupMute.filter(group_id=self.post.group_id)
            .using_db(using_db)
            .values_list("user_id", flat=True),
        )
        return set(rows)

    async def thread_participant_ids(self, comment_id: UUID, using_db: BaseDBAsyncClient | None = None) -> set[UUID]:
        # A post comment thread is one level deep: a root comment (parent_id is null) plus
        # replies pointing at it. Participants are everyone who authored in that root's thread.
        comment = await PostComment.filter(id=comment_id).using_db(using_db).first()
        if comment is None:
            return set()
        root_id = comment.parent_id or comment.id
        rows = cast(
            list[UUID],
            await PostComment.filter(Q(id=root_id) | Q(parent_id=root_id))
            .using_db(using_db)
            .values_list("user_id", flat=True),
        )
        return set(rows)


class PostFilters(WorkspaceMixinFilters):
    draft: Q = Q(published_at__isnull=True)
    published: Q = Q(published_at__isnull=False)
    everyone: Q = Q(group_id__isnull=True)
    grouped: Q = Q(group_id__isnull=False)

    @classmethod
    def decided(cls, organization_id: UUID) -> Q:
        # A post is decided when its workspace holds any decision (decisions are
        # workspace-scoped; the legacy per-post decided_at column is gone). Scope the
        # subquery to the org's own decisions so it doesn't materialise workspace IDs
        # across every org as the global Decision table grows; distinct collapses the
        # one-row-per-decision result to one row per workspace.
        return Q(
            workspace_id__in=Subquery(
                Decision.filter(workspace__organization_id=organization_id)
                # order_by clears the model's default decided_at ordering, which a
                # SELECT DISTINCT rejects unless the column is also selected.
                .order_by("workspace_id")
                .distinct()
                .values_list("workspace_id", flat=True)
            )
        )

    @classmethod
    def drafts_visible_to(cls, user_id: UUID) -> Q:
        return cls.draft & (cls.by_creator(user_id) | cls.by_collaborated_workspaces(user_id))

    @classmethod
    def by_group(cls, group_ids: list[UUID]) -> Q:
        return Q(group_id__in=group_ids)

    @classmethod
    def pinned(cls) -> Q:
        return Q(pinned_at__isnull=False)

    @classmethod
    def not_pinned(cls) -> Q:
        return Q(pinned_at__isnull=True)


class Post(WorkspaceMixin, RecordModel):
    sharing = fields.CharEnumField(Sharing, default=Sharing.ORGANIZATION, max_length=255)
    group: fields.ForeignKeyNullableRelation[Group] = fields.ForeignKeyField(
        "convictional.Group", null=True, related_name="posts", on_delete=fields.SET_NULL
    )
    group_id: Annotated[UUID | None, "foreign key to group"]
    is_announcement = fields.BooleanField(default=False)
    pinned_at: datetime | None = fields.DatetimeField(null=True)
    published_at: datetime | None = fields.DatetimeField(null=True)
    comments: fields.ReverseRelation["PostComment"]
    filters = PostFilters()
    email_delivery = EmailDelivery.SKIP

    _on_publish: ClassVar[list[Callable[["Post"], Awaitable[None]]]] = []

    @classmethod
    def on_publish(cls, hook: Callable[["Post"], Awaitable[None]]) -> None:
        cls._on_publish.append(hook)

    class Meta:
        ordering = ["-created_at"]
        indexes = (("organization_id", "published_at"),)

    @property
    def notification_policy(self) -> PostNotificationPolicy:
        return PostNotificationPolicy(workspace=self.workspace, post=self)

    @classmethod
    def notification_policy_class(cls) -> type[PostNotificationPolicy]:
        return PostNotificationPolicy

    @property
    def is_draft(self) -> bool:
        return self.published_at is None

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    @property
    def is_pinned(self) -> bool:
        return self.pinned_at is not None

    async def pin(self, using_db: BaseDBAsyncClient | None = None):
        self.pinned_at = datetime.now(UTC)
        await self.save(using_db=using_db)

    async def unpin(self, using_db: BaseDBAsyncClient | None = None):
        self.pinned_at = None
        await self.save(using_db=using_db)

    def editable_by(self, user: User) -> bool:
        return self.creator_id == user.id or user.is_admin

    def deletable_by(self, user: User) -> bool:
        return self.creator_id == user.id or user.is_admin

    @staticmethod
    def pinnable_by(user: User) -> bool:
        return user.is_admin

    @property
    def live_document_topic(self) -> Topic:
        return Topic("post_draft", post_id=self.id)

    async def get_live_document_markdown(self) -> str:
        live_doc = await LiveDocument.for_topic(self.live_document_topic)
        return live_doc.markdown or ""

    # Quoted forward reference is mandatory: PostComment is defined later in this
    # module and there's no `from __future__ import annotations`, so a bare
    # annotation would NameError at import time.
    async def publish(self, content: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None) -> "PostComment":
        async with transaction(using_db=using_db) as connection:
            self.published_at = datetime.now(UTC)
            self.sharing = Sharing.ORGANIZATION
            await self.save(using_db=connection)
            # Hard delete is intentional — replaces any draft-phase comments with the
            # live document content as the canonical first comment on the published post
            deleted_comment_ids = cast(
                list[UUID],
                await PostComment.filter(post_id=self.id).using_db(connection).values_list("id", flat=True),
            )
            deleted_draft_comment_ids = cast(
                list[UUID],
                await PostDraftComment.filter(post_id=self.id).using_db(connection).values_list("id", flat=True),
            )
            deleted_comment_gids = [
                GlobalID.create(PostComment.record_type, comment_id) for comment_id in deleted_comment_ids
            ] + [GlobalID.create(PostDraftComment.record_type, comment_id) for comment_id in deleted_draft_comment_ids]
            await PostComment.filter(post_id=self.id).using_db(connection).delete()
            await PostDraftComment.filter(post_id=self.id).using_db(connection).delete()
            # The bulk comment delete above can't fire post_delete, so decisions
            # anchored to the deleted comments are deleted as instances here. Each
            # instance delete fires the DELETE observer that cleans up its index entry.
            if deleted_comment_gids:
                orphaned_decisions = await Decision.filter(comment_gid__in=deleted_comment_gids).using_db(connection)
                for decision in orphaned_decisions:
                    await decision.delete(using_db=connection)
            comment = await PostComment.create(content=content, user_id=user_id, post_id=self.id, using_db=connection)
            await Attachment.claim_for_live_document_content(
                self.workspace_id, content, owner_id=user_id, using_db=connection
            )

            self.workspace.resource = self

        await self.fire_publish_hooks()

        return comment

    async def fire_publish_hooks(self) -> None:
        for hook in self._on_publish:
            await hook(self)

    async def soft_delete(self, using_db: BaseDBAsyncClient | None = None):
        result = await super().soft_delete(using_db)
        await Mailbox.delete(self)
        return result

    @property
    def original_comment(self):
        return self.comments[0] if len(self.comments) > 0 else None

    @property
    def top_level(self):
        return [comment for comment in self.comments if comment != self.original_comment and not comment.is_reply]

    @property
    def commenter_ids(self):
        return {comment.user_id for comment in self.comments}


class PostComment(SoftDeleteableMixin, CommentMixin, RecordModel):
    comment_topic: ClassVar[str] = "post_comments"
    comment_topic_param: ClassVar[str] = "post_id"

    post: fields.ForeignKeyRelation[Post] = fields.ForeignKeyField("convictional.Post", related_name="comments")
    post_id: Annotated[UUID, "foreign key to post"]
    parent: fields.ForeignKeyNullableRelation["PostComment"] = fields.ForeignKeyField(
        "convictional.PostComment", related_name="replies", null=True
    )
    parent_id: Annotated[UUID, "foreign key to parent comment"]
    replies: fields.ReverseRelation["PostComment"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("post_id"),)

    @property
    def is_top_level(self):
        return self.parent_id is None and not self.is_original

    @property
    def is_reply(self):
        return self.parent_id is not None and self.parent_id != self.id

    def editable_by(self, user: User) -> bool:
        return self.user_id == user.id

    def deletable_by(self, user: User) -> bool:
        return self.user_id == user.id


class PostGroupMute(RecordModel):
    # Existence semantics: a row means "silence post notifications scoped to this group for
    # this user." SubscriberResolver consults this via PostNotificationPolicy.muted_user_ids
    # and flips an in-group member's level from ALL to RELEVANT_ONLY without touching
    # membership. No level column — for a member the only meaningful state is muted or not.
    user: fields.ForeignKeyRelation[User] = fields.ForeignKeyField(
        "convictional.User", related_name="post_group_mutes"
    )
    user_id: Annotated[UUID, "foreign key to user"]
    group: fields.ForeignKeyRelation["Group"] = fields.ForeignKeyField("convictional.Group", related_name="post_mutes")
    group_id: Annotated[UUID, "foreign key to group"]

    class Meta:
        unique_together = (("user_id", "group_id"),)

    @classmethod
    async def mute(cls, *, user_id: UUID, group_id: UUID, using_db: BaseDBAsyncClient | None = None) -> None:
        await cls.get_or_create(user_id=user_id, group_id=group_id, using_db=using_db)

    @classmethod
    async def unmute(cls, *, user_id: UUID, group_id: UUID, using_db: BaseDBAsyncClient | None = None) -> None:
        await cls.filter(user_id=user_id, group_id=group_id).using_db(using_db).delete()


class PostDraftComment(CommentMixin, AnnotationMixin, ResolvableMixin, RecordModel):
    comment_topic: ClassVar[str] = "post_draft_comments"
    comment_topic_param: ClassVar[str] = "post_id"

    post: fields.ForeignKeyRelation[Post] = fields.ForeignKeyField("convictional.Post", related_name="draft_comments")
    post_id: Annotated[UUID, "foreign key to post"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("post_id",),)

    async def broadcast_resolved(self, author_id: UUID) -> None:
        await self.topic().broadcast(
            resolved_thread_mark_id=self.comment_mark_id,
            author_id=str(author_id),
        )


post_delete(PostComment)(delete_decision_for_comment)
post_delete(PostDraftComment)(delete_decision_for_comment)


@post_save(PostComment)
async def ensure_collaborator(
    sender: "type[PostComment]",
    instance: PostComment,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if not isinstance(instance.post, Post):
        await instance.fetch_related("post")

    await Workspace.ensure_collaborator(instance.post.workspace_id, instance.user_id, using_db=using_db)


@post_save(Post)
async def ensure_post_group_collaborators(
    sender: "type[Post]",
    instance: Post,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if not instance.group_id or instance.is_draft:
        return

    group_members = await GroupMember.filter(group_id=instance.group_id).using_db(using_db)
    for member in group_members:
        await Collaborator.get_or_create(workspace_id=instance.workspace_id, user_id=member.user_id, using_db=using_db)


@post_save(GroupMember)
async def add_new_group_member_as_post_collaborator(
    sender: "type[GroupMember]",
    instance: GroupMember,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if not created:
        return

    group_posts = (
        await Post.filter(Post.filters.published & Post.filters.by_group([instance.group_id]))
        .prefetch_related("workspace")
        .using_db(using_db)
    )
    for post in group_posts:
        await Collaborator.get_or_create(workspace_id=post.workspace_id, user_id=instance.user_id, using_db=using_db)


class PostMailboxEntryFilters(BaseMailboxEntryFilters):
    pass


@dataclass
class PostMailboxEntry(BaseMailboxEntry):
    resource_model: ClassVar[type] = Post
    entry_filters: ClassVar[type[BaseMailboxEntryFilters]] = PostMailboxEntryFilters
    post: Post

    prefetch_for_sync: ClassVar[tuple[str, ...]] = (
        "workspace__collaborators__user",
        "workspace__events",
        "workspace__attachments",
        "comments",
    )

    @classmethod
    def from_resource(cls, resource: RecordModel) -> Self:
        assert isinstance(resource, Post)
        return cls(post=resource)

    @property
    def resource(self) -> Post:
        return self.post

    async def touch(self, user: User, *, using_db: BaseDBAsyncClient | None = None) -> None:
        await self.post.fetch_related(*self.prefetch_for_sync, using_db=using_db)

        if sync := await self.refresh_row_and_mark_unread(user, using_db=using_db):
            await sync.broadcast()

    def _refresh_resource_fields(self, entry: MailboxEntry) -> None:
        entry.title = self.post.title
        entry.is_shared = self.post.creator_id != entry.owner_id
        self._apply_event_preview(entry)

    def _authored_preview(self, event: Event) -> AuthoredPreview | None:
        # Two authored cases, each rendered as a chip with the author's avatar: a discussion comment,
        # and the post's own body (its original comment) when the post is first published — publishing
        # otherwise shows a bare "Posted"/"Announced" line, which says nothing about the post. Every
        # other post event (pinned/decided, a collaborator add) falls through to None so the base pins
        # it as an activity line the client phrases from the action + details (see PostEntryBody).
        match event.action:
            case EventAction.POST_COMMENTED if comment := self._event_comment(event):
                return AuthoredPreview(comment.content, comment.user_id, is_comment=True)
            case EventAction.POST_CREATED | EventAction.POST_ANNOUNCED if original := self.post.original_comment:
                return AuthoredPreview(original.content, original.user_id, is_comment=True)
            case _:
                return None

    def _event_comment(self, event: Event) -> "PostComment | None":
        # The comment the POST_COMMENTED event recorded (event.recordable). Falls through to the
        # activity line when it's since been soft-deleted (dropped from the comments relation).
        return next((comment for comment in self.post.comments if comment.id == event.recordable_id), None)
