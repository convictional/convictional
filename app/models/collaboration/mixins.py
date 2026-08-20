from datetime import UTC, datetime
from typing import ClassVar, TypeVar
from uuid import UUID

from tortoise import BaseDBAsyncClient, fields
from tortoise.expressions import Q
from tortoise.queryset import QuerySet
from tortoise.signals import pre_save

from infra.db import JSONField, RecordModel, transaction

#
# Sortable
#
#

SortableType = TypeVar("SortableType", bound="SortableMixin")


class SortableMixin(RecordModel):
    position = fields.IntField(default=0)

    class Meta:
        abstract = True

    @classmethod
    async def reorder_by_ids(cls, ids: list[UUID], scope: QuerySet[SortableType]):
        async with transaction() as connection:
            sortables = await scope.filter(id__in=ids).using_db(connection).select_for_update()
            for index, id in enumerate(ids):
                sortable = next((o for o in sortables if o.id == id), None)
                if sortable:
                    sortable.position = index
                    await sortable.save(using_db=connection)


#
# Closeable
#
#


class CloseableFilters:
    closed: ClassVar[Q] = Q(closed_at__isnull=False)
    open: ClassVar[Q] = Q(closed_at__isnull=True)


class CloseableMixin(RecordModel):
    closed_at: datetime | None = fields.DatetimeField(null=True)

    class Meta:
        abstract = True

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    async def close(self, using_db: BaseDBAsyncClient | None = None):
        self.closed_at = datetime.now(UTC)
        await self.save(using_db=using_db)

    async def open(self, using_db: BaseDBAsyncClient | None = None):
        self.closed_at = None
        await self.save(using_db=using_db)


#
# Completable
#
#


class CompletableFilters:
    completed: ClassVar[Q] = Q(completed_at__isnull=False)
    incomplete: ClassVar[Q] = Q(completed_at__isnull=True)


class CompletableMixin(RecordModel):
    completed_at: datetime | None = fields.DatetimeField(null=True)

    class Meta:
        abstract = True

    @property
    def is_completed(self) -> bool:
        return self.completed_at is not None

    @is_completed.setter
    def is_completed(self, value: bool):
        self.completed_at = datetime.now(UTC) if value else None

    @property
    def is_incomplete(self) -> bool:
        return self.completed_at is None

    async def complete(self, using_db: BaseDBAsyncClient | None = None):
        self.completed_at = datetime.now(UTC)
        await self.save(using_db=using_db)

    async def incomplete(self, using_db: BaseDBAsyncClient | None = None):
        self.completed_at = None
        await self.save(using_db=using_db)


#
# Resolvable
#
#


class ResolvableFilters:
    resolved: ClassVar[Q] = Q(resolved_at__isnull=False)
    unresolved: ClassVar[Q] = Q(resolved_at__isnull=True)


class ResolvableMixin(RecordModel):
    resolved_at: datetime | None = fields.DatetimeField(null=True)

    class Meta:
        abstract = True

    @property
    def is_resolved(self) -> bool:
        return self.resolved_at is not None


#
# Annotation
#
#


class AnnotationMixin(RecordModel):
    comment_mark_id = fields.CharField(max_length=36)
    quoted_text = fields.TextField()

    class Meta:
        abstract = True


#
# Taggable
#
#


class TaggableMixin:
    tags: list[str] = JSONField(default=[])

    class Meta:
        abstract = True

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        pre_save(cls)(clean_tags)


async def clean_tags(
    sender: type[TaggableMixin], instance: TaggableMixin, using_db: BaseDBAsyncClient | None, update_fields: list[str]
) -> None:
    instance.tags = [str(tag).strip() for tag in instance.tags if tag]
    instance.tags = [tag for tag in instance.tags if tag]
    instance.tags = list(set(instance.tags))
