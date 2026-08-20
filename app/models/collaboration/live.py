from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pycrdt import Doc, Map, Text
from tortoise import BaseDBAsyncClient, fields
from tortoise.functions import Max
from tortoise.queryset import Q

from config import logger
from infra.cache import cache
from infra.db import RecordModel, transaction
from infra.messaging import Topic

#
# Documents
#
#


class LiveDocumentFilters:
    @staticmethod
    def for_topic(topic: Topic):
        return Q(topic_name=topic.name)

    @staticmethod
    def for_stream(stream: str):
        return Q(topic_name__startswith=stream + ":")


class LiveDocumentUpdate(RecordModel):
    topic_name = fields.CharField(max_length=500, db_index=True)
    update_data = fields.BinaryField()

    class Meta:
        table = "livedocumentupdate"
        ordering = ["created_at"]
        indexes = (("topic_name", "created_at"),)

    @property
    def topic(self):
        return Topic.from_name(self.topic_name)

    @classmethod
    async def apply_all_updates(cls, doc: Doc, topic: Topic) -> None:
        async for update in cls.filter(LiveDocumentFilters.for_topic(topic)):
            doc.apply_update(update.update_data)


class LiveDocument(Doc):
    @classmethod
    async def for_topic(cls, topic: Topic) -> "LiveDocument":
        doc = cls(allow_multithreading=True)
        await LiveDocumentUpdate.apply_all_updates(doc, topic)
        return doc

    @property
    def markdown(self) -> str:
        markdown_text = self.get("markdown", type=Text)
        if markdown_text:
            return str(markdown_text)

        initial_content = self.get("initial_content", type=Text)
        if initial_content:
            return str(initial_content)

        return ""

    @staticmethod
    async def set_initial_content(
        topic: Topic, markdown_content: str, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        # Create a new Yjs document with initial content
        doc: Doc = Doc()
        initial_content = doc.get("initial_content", type=Text)
        initial_content.insert(0, markdown_content)

        # Create the update record to persist this initial state
        update_data = doc.get_update()
        if update_data:
            await LiveDocumentUpdate.create(topic_name=topic.name, update_data=update_data, using_db=using_db)

    @staticmethod
    async def get_topics_stable_for(minutes: int, stream: str | None = None):
        threshold = datetime.now(UTC) - timedelta(minutes=minutes)
        filter = Q(most_recent_update__lt=threshold)
        if stream:
            filter &= LiveDocumentFilters.for_stream(stream)
        topic_names = (
            await LiveDocumentUpdate.filter(filter)
            .annotate(most_recent_update=Max("created_at"))
            .group_by("topic_name")
            .values_list("topic_name", flat=True)
        )
        return [Topic.from_name(str(name[0]) if isinstance(name, tuple) else str(name)) for name in topic_names]

    @staticmethod
    async def merge_stable_topics(minutes: int, stream: str | None = None):
        stable_topics = await LiveDocument.get_topics_stable_for(minutes, stream)
        logger.info(f"Found {len(stable_topics)} stable topics for merging")
        for topic in stable_topics:
            logger.info(f"Merging stable topic: {topic.name}")
            async with transaction() as db:
                updates = await LiveDocumentUpdate.filter(LiveDocumentFilters.for_topic(topic)).using_db(db)
                logger.info(f"Found {len(updates)} updates for topic {topic.name} {updates}")
                if not updates or len(updates) <= 1:
                    continue

                doc = LiveDocument()
                for update in updates:
                    doc.apply_update(update.update_data)

                editor_ids = set()
                with doc.transaction():
                    editors: Map = doc.get("editors", type=Map)
                    for editor in editors.keys():
                        editor_ids.add(UUID(editor))
                    editors.clear()

                await LiveDocumentUpdate.create(
                    topic_name=topic.name,
                    update_data=doc.get_update(),
                    created_at=updates[0].created_at,
                    using_db=db,
                )

                await LiveDocumentUpdate.filter(id__in=[update.id for update in updates]).using_db(db).delete()

                yield topic, editor_ids, doc.markdown


#
# Live Activity
#
#


def workspace_scope_key(workspace_id: UUID) -> str:
    return f"workspace:{workspace_id}"


def email_thread_scope_key(email_thread_id: UUID) -> str:
    return f"email_thread:{email_thread_id}"


@dataclass
class LiveActivity(ABC):
    scope_key: str

    @property
    @abstractmethod
    def cache_key_prefix(self) -> str:
        pass

    @property
    @abstractmethod
    def activity_window(self) -> timedelta:
        pass

    @property
    @abstractmethod
    def heartbeat_timeout(self) -> timedelta:
        pass

    @property
    def _cache_key(self) -> str:
        return f"{self.cache_key_prefix}:{self.scope_key}"

    async def get_active_user_ids(self) -> list[UUID]:
        user_ids: list[str] = list(await cache.set_read(self._cache_key))
        if not user_ids:
            return []

        # Batch the per-member timestamp lookups into one read rather than a
        # query per member — this loop is the presence N+1 on /channels.
        timestamps = await cache.read_many([f"{self._cache_key}:timestamp:{user_id}" for user_id in user_ids])
        return [UUID(user_id) for user_id, timestamp in zip(user_ids, timestamps, strict=True) if timestamp]

    async def add_user(self, user_id: UUID) -> list[UUID]:
        # Add user to the cache set, refreshing the set's expiration in the same write
        await cache.set_add(self._cache_key, str(user_id), expires_in=self.activity_window)

        # Update timestamp for this user with expiration
        timestamp_key = f"{self._cache_key}:timestamp:{user_id}"
        await cache.write(timestamp_key, datetime.now(UTC).isoformat(), self.heartbeat_timeout)

        # Return current active users (including this one)
        return await self.get_active_user_ids()

    async def remove_user(self, user_id: UUID) -> list[UUID]:
        # Remove user from the cache set
        await cache.set_remove(self._cache_key, str(user_id))
        await cache.delete(f"{self._cache_key}:timestamp:{user_id}")
        return await self.get_active_user_ids()


@dataclass
class Presence(LiveActivity):
    @property
    def cache_key_prefix(self) -> str:
        return "presence"

    @property
    def activity_window(self) -> timedelta:
        return timedelta(minutes=5)

    @property
    def heartbeat_timeout(self) -> timedelta:
        return timedelta(seconds=100)  # Higher than the 90s keep alive timeout for channels


@dataclass
class Typing(LiveActivity):
    @property
    def cache_key_prefix(self) -> str:
        return "typing"

    @property
    def activity_window(self) -> timedelta:
        return timedelta(seconds=5)

    @property
    def heartbeat_timeout(self) -> timedelta:
        return timedelta(seconds=1.5)
