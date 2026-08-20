from dataclasses import dataclass
from typing import Annotated, ClassVar, cast
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields
from tortoise.queryset import Q
from tortoise.signals import post_delete, post_save

from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mixins import AnnotationMixin, ResolvableMixin
from app.models.collaboration.workspace import (
    CommentMixin,
    NotificationPolicy,
    Workspace,
    WorkspaceMixin,
    WorkspaceMixinFilters,
    delete_decision_for_comment,
)
from config.enums import Sharing
from infra.db import RecordModel
from infra.messaging import Topic


class DocumentFilters(WorkspaceMixinFilters):
    @classmethod
    def available_to(cls, user_id: UUID) -> Q:
        # Every document the user can actually open: their own, ones they
        # collaborate on, and anything shared with the whole organization. This
        # is the universe the ownership filters partition — mirrors
        # CollaborationPolicy.can_be_accessed_by.
        return cls.by_creator(user_id) | cls.by_collaborated_workspaces(user_id) | Q(sharing=Sharing.ORGANIZATION)

    @classmethod
    def owned_by_me(cls, user_id: UUID) -> Q:
        return cls.by_creator(user_id)

    @classmethod
    def owned_by_others(cls, user_id: UUID) -> Q:
        return cls.available_to(user_id) & ~cls.by_creator(user_id)


@dataclass
class DocumentNotificationPolicy(NotificationPolicy):
    async def thread_participant_ids(self, comment_id: UUID, using_db: BaseDBAsyncClient | None = None) -> set[UUID]:
        # A document comment thread is the comments sharing one annotation anchor
        # (comment_mark_id) on the same document; every author in it is a participant.
        comment = await DocumentComment.filter(id=comment_id).using_db(using_db).first()
        if comment is None:
            return set()
        rows = cast(
            list[UUID],
            await DocumentComment.filter(document_id=comment.document_id, comment_mark_id=comment.comment_mark_id)
            .using_db(using_db)
            .values_list("user_id", flat=True),
        )
        return set(rows)


class Document(WorkspaceMixin, RecordModel):
    sharing = fields.CharEnumField(Sharing, default=Sharing.PRIVATE, max_length=255)
    document_comments: fields.ReverseRelation["DocumentComment"]

    filters = DocumentFilters()

    class Meta:
        ordering = ["-updated_at"]
        indexes = (("organization_id",),)

    @property
    def notification_policy(self) -> DocumentNotificationPolicy:
        return DocumentNotificationPolicy(workspace=self.workspace)

    @classmethod
    def notification_policy_class(cls) -> type[DocumentNotificationPolicy]:
        return DocumentNotificationPolicy

    @property
    def live_document_topic(self) -> Topic:
        return Topic("document", document_id=self.id)

    async def get_live_document_markdown(self) -> str:
        live_doc = await LiveDocument.for_topic(self.live_document_topic)
        return live_doc.markdown or ""


class DocumentComment(CommentMixin, AnnotationMixin, ResolvableMixin, RecordModel):
    comment_topic: ClassVar[str] = "document_comments"
    comment_topic_param: ClassVar[str] = "document_id"

    document: fields.ForeignKeyRelation[Document] = fields.ForeignKeyField(
        "convictional.Document", related_name="document_comments"
    )
    document_id: Annotated[UUID, "foreign key to document"]

    class Meta:
        ordering = ["created_at"]
        indexes = (("document_id",),)

    async def broadcast_resolved(self, author_id: UUID) -> None:
        await self.topic().broadcast(
            resolved_thread_mark_id=self.comment_mark_id,
            author_id=str(author_id),
        )


post_delete(DocumentComment)(delete_decision_for_comment)


@post_save(DocumentComment)
async def ensure_document_comment_collaborator(
    sender: "type[DocumentComment]",
    instance: DocumentComment,
    created: bool,
    using_db: BaseDBAsyncClient | None,
    update_fields: list[str],
) -> None:
    if not created:
        return

    if not isinstance(instance.document, Document):
        await instance.fetch_related("document")

    await Workspace.ensure_collaborator(instance.document.workspace_id, instance.user_id, using_db=using_db)
