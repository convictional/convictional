import inspect
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, SupportsFloat
from uuid import uuid4 as generate_uuid

from tortoise import BaseDBAsyncClient, Model, Tortoise, fields

from config import settings
from config.settings import CacheStore as CacheStoreEnum
from infra.db import JSONField, transaction
from lib.json import JSONDumps, JSONLoads


class CacheStore(ABC):
    @abstractmethod
    async def read(self, key: str) -> str | None:
        """Retrieve a value from the cache."""
        pass

    @abstractmethod
    async def read_many(self, keys: Sequence[str]) -> list[str | None]:
        """Retrieve multiple values from the cache atomically.

        Returns a list of values in the same order as the input keys.
        Missing or expired keys return None at their position.
        """
        pass

    @abstractmethod
    async def write(self, key: str, value: str, expires_in: timedelta) -> None:
        """Store a value in the cache with expiration."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value from the cache.

        Returns True if the key existed and was deleted, False otherwise.
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all cache entries."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        pass

    @abstractmethod
    async def expire(self, key: str, expires_in: timedelta) -> bool:
        """Set expiration time for an existing key. Returns True if key exists and expiration was set."""
        pass

    @abstractmethod
    async def cleanup_expired(self) -> int:
        """Remove expired cache entries and return count of deleted entries."""
        pass

    @abstractmethod
    async def set_add(self, key: str, member: str, expires_in: timedelta | None = None) -> bool:
        """Add member to set. Returns True if added, False if already exists.

        When expires_in is given, the set's expiration is refreshed in the same
        write, avoiding a separate expire() round trip on hot paths like presence.
        """
        pass

    @abstractmethod
    async def set_remove(self, key: str, member: str) -> bool:
        """Remove member from set. Returns True if removed, False if didn't exist."""
        pass

    @abstractmethod
    async def set_read(self, key: str) -> set[str]:
        """Get all members of a set."""
        pass

    @abstractmethod
    async def read_with_ttl(self, key: str) -> tuple[str | None, float | None]:
        """Retrieve a value and its remaining TTL from the cache."""
        pass

    async def read_json(self, key: str) -> Any:
        """Retrieve and deserialize a JSON value from the cache."""
        value = await self.read(key)
        if value is None:
            return None
        return JSONLoads(value)

    async def write_json(self, key: str, value: Any, expires_in: timedelta) -> None:
        """Serialize and store a JSON value in the cache."""
        serialized = JSONDumps(value)
        await self.write(key, serialized, expires_in)


class NullCacheStore(CacheStore):
    async def read(self, key: str) -> str | None:
        return None

    async def read_many(self, keys: Sequence[str]) -> list[str | None]:
        return [None] * len(keys)

    async def write(self, key: str, value: str, expires_in: timedelta) -> None:
        pass

    async def delete(self, key: str) -> bool:
        return False

    async def clear(self) -> None:
        pass

    async def exists(self, key: str) -> bool:
        return False

    async def expire(self, key: str, expires_in: timedelta) -> bool:
        return False

    async def cleanup_expired(self) -> int:
        return 0

    async def set_add(self, key: str, member: str, expires_in: timedelta | None = None) -> bool:
        return False

    async def set_remove(self, key: str, member: str) -> bool:
        return False

    async def set_read(self, key: str) -> set[str]:
        return set()

    async def read_with_ttl(self, key: str) -> tuple[str | None, float | None]:
        return None, None


class CacheEntry(Model):
    id = fields.UUIDField(primary_key=True)
    cache_key = fields.CharField(max_length=500, unique=True)
    value = fields.TextField(null=True)
    set_value = JSONField[dict](default={})
    expires_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    class Meta:
        indexes = (("cache_key",), ("expires_at",))

    @classmethod
    async def write(
        cls, key: str, value: str, expires_at: datetime, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        connection = using_db or Tortoise.get_connection("auxiliary")
        await connection.execute_query(
            """
            INSERT INTO cacheentry (id, cache_key, value, expires_at, created_at, updated_at)
            VALUES ($1::uuid, $2, $3, $4, NOW(), NOW())
            ON CONFLICT (cache_key) DO UPDATE SET
                value = EXCLUDED.value,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW();
            """,
            [str(generate_uuid()), key, value, expires_at],
        )

    @classmethod
    async def set_add(
        cls,
        key: str,
        member: str,
        expires_at: datetime | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> bool:
        connection = using_db or Tortoise.get_connection("auxiliary")
        # The UPDATE always runs so expires_at is refreshed even when the member
        # already exists (callers refreshing presence depend on this); merging
        # set_value is idempotent. "added" is derived from the pre-upsert
        # snapshot, which both CTEs share, so it ignores the UPDATE's changes.
        rows = await connection.execute_query_dict(
            """
            WITH existing AS (
                SELECT set_value ? $3::text AS already_member
                FROM cacheentry
                WHERE cache_key = $2
            ),
            upsert AS (
                INSERT INTO cacheentry (id, cache_key, set_value, expires_at, created_at, updated_at)
                VALUES ($1::uuid, $2, jsonb_build_object($3::text, TRUE), $4, NOW(), NOW())
                ON CONFLICT (cache_key) DO UPDATE
                SET
                    set_value = cacheentry.set_value || EXCLUDED.set_value,
                    expires_at = COALESCE($4, cacheentry.expires_at),
                    updated_at = NOW()
            )
            SELECT NOT COALESCE((SELECT already_member FROM existing), FALSE) AS added;
            """,
            [str(generate_uuid()), key, member, expires_at],
        )
        return bool(rows and rows[0]["added"])

    @classmethod
    async def set_remove(cls, key: str, member: str, using_db: BaseDBAsyncClient | None = None) -> bool:
        connection = using_db or Tortoise.get_connection("auxiliary")
        async with transaction(using_db=connection) as conn:
            rows = await conn.execute_query_dict(
                """
                UPDATE cacheentry
                SET set_value = set_value - $2::text, updated_at = NOW()
                WHERE cache_key = $1
                AND set_value ? $2::text
                RETURNING id, (set_value = '{}'::jsonb) AS is_now_empty;
                """,
                [key, member],
            )
            if not rows:
                return False
            if rows[0]["is_now_empty"]:
                await conn.execute_query("DELETE FROM cacheentry WHERE id = $1;", [rows[0]["id"]])

            return True

    @classmethod
    async def set_read(cls, key: str, using_db: BaseDBAsyncClient | None = None) -> set[str]:
        connection = using_db or Tortoise.get_connection("auxiliary")
        entry = await cls.get_or_none(cache_key=key, using_db=connection)
        if entry is None or entry.is_expired:
            return set()
        return set(entry.set_value)

    @property
    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return self.expires_at < datetime.now(UTC)


class PostgresCacheStore(CacheStore):
    async def read(self, key: str) -> str | None:
        connection = Tortoise.get_connection("auxiliary")
        entry = await CacheEntry.get_or_none(cache_key=key, using_db=connection)
        if entry is None or entry.is_expired:
            return None

        return entry.value

    async def read_many(self, keys: Sequence[str]) -> list[str | None]:
        if not keys:
            return []
        connection = Tortoise.get_connection("auxiliary")
        entries = await CacheEntry.filter(cache_key__in=list(keys)).using_db(connection)
        entries_by_key = {entry.cache_key: entry for entry in entries}
        return [
            entries_by_key[key].value if key in entries_by_key and not entries_by_key[key].is_expired else None
            for key in keys
        ]

    async def write(self, key: str, value: str, expires_in: timedelta) -> None:
        connection = Tortoise.get_connection("auxiliary")
        expires_at = datetime.now(UTC) + expires_in
        await CacheEntry.write(key, value, expires_at, using_db=connection)

    async def delete(self, key: str) -> bool:
        connection = Tortoise.get_connection("auxiliary")
        deleted_count = await CacheEntry.filter(cache_key=key).using_db(connection).delete()
        return deleted_count > 0

    async def clear(self) -> None:
        connection = Tortoise.get_connection("auxiliary")
        await CacheEntry.all().using_db(connection).delete()

    async def exists(self, key: str) -> bool:
        connection = Tortoise.get_connection("auxiliary")
        entry = await CacheEntry.get_or_none(cache_key=key, using_db=connection)
        return entry is not None and not entry.is_expired

    async def expire(self, key: str, expires_in: timedelta) -> bool:
        connection = Tortoise.get_connection("auxiliary")
        expires_at = datetime.now(UTC) + expires_in
        result = await CacheEntry.filter(cache_key=key).using_db(connection).update(expires_at=expires_at)
        return result > 0

    async def cleanup_expired(self) -> int:
        connection = Tortoise.get_connection("auxiliary")
        return await CacheEntry.filter(expires_at__lt=datetime.now(UTC)).using_db(connection).delete()

    async def set_add(self, key: str, member: str, expires_in: timedelta | None = None) -> bool:
        connection = Tortoise.get_connection("auxiliary")
        expires_at = datetime.now(UTC) + expires_in if expires_in is not None else None
        return await CacheEntry.set_add(key, member, expires_at=expires_at, using_db=connection)

    async def set_remove(self, key: str, member: str) -> bool:
        connection = Tortoise.get_connection("auxiliary")
        return await CacheEntry.set_remove(key, member, using_db=connection)

    async def set_read(self, key: str) -> set[str]:
        connection = Tortoise.get_connection("auxiliary")
        return await CacheEntry.set_read(key, using_db=connection)

    async def read_with_ttl(self, key: str) -> tuple[str | None, float | None]:
        connection = Tortoise.get_connection("auxiliary")
        entry = await CacheEntry.get_or_none(cache_key=key, using_db=connection)
        if entry is None or entry.is_expired:
            return None, None

        remaining_ttl = None
        if entry.expires_at:
            remaining_ttl = (entry.expires_at - datetime.now(UTC)).total_seconds()

        return entry.value, remaining_ttl


@dataclass
class Cache:
    store: CacheStore

    async def read(self, key: str) -> str | None:
        """Retrieve a value from the cache."""
        return await self.store.read(key)

    async def read_many(self, keys: Sequence[str]) -> list[str | None]:
        """Retrieve multiple values from the cache atomically."""
        return await self.store.read_many(keys)

    async def write(self, key: str, value: str, expires_in: timedelta) -> None:
        """Store a value in the cache with expiration."""
        await self.store.write(key, value, expires_in)

    async def delete(self, key: str) -> bool:
        """Delete a value from the cache. Returns True if key existed."""
        return await self.store.delete(key)

    async def clear(self) -> None:
        """Clear all cache entries."""
        await self.store.clear()

    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache."""
        return await self.store.exists(key)

    async def read_json(self, key: str) -> Any:
        """Retrieve and deserialize a JSON value from the cache."""
        return await self.store.read_json(key)

    async def read_json_many(self, keys: Sequence[str]) -> list[Any]:
        """Retrieve and deserialize multiple JSON values from the cache atomically."""
        values = await self.store.read_many(keys)
        return [JSONLoads(v) if v is not None else None for v in values]

    async def write_json(self, key: str, value: Any, expires_in: timedelta) -> None:
        """Serialize and store a JSON value in the cache."""
        await self.store.write_json(key, value, expires_in)

    async def fetch(
        self, key: str, expires_in: timedelta, generator: Callable[[], Any] | Callable[[], Awaitable[Any]]
    ) -> Any:
        """Fetch from cache or generate and cache the value."""
        value = await self.read_json(key)
        if value is not None:
            return value

        if inspect.iscoroutinefunction(generator):
            generated_value = await generator()
        else:
            generated_value = generator()

        await self.write_json(key, generated_value, expires_in)
        return generated_value

    async def set_add(self, key: str, member: str, expires_in: timedelta | None = None) -> bool:
        """Add member to set. Returns True if added, False if already exists.

        When expires_in is given, the set's expiration is refreshed in the same
        write, avoiding a separate expire() round trip on hot paths like presence.
        """
        return await self.store.set_add(key, member, expires_in)

    async def set_remove(self, key: str, member: str) -> bool:
        """Remove member from set. Returns True if removed, False if didn't exist."""
        return await self.store.set_remove(key, member)

    async def set_read(self, key: str) -> set[str]:
        """Get all members of a set."""
        return await self.store.set_read(key)

    async def expire(self, key: str, expires_in: timedelta) -> bool:
        """Set expiration time for an existing key. Returns True if key exists and expiration was set."""
        return await self.store.expire(key, expires_in)

    async def read_with_ttl(self, key: str) -> tuple[str | None, float | None]:
        """Retrieve a value and its remaining TTL from the cache."""
        return await self.store.read_with_ttl(key)

    async def read_json_with_ttl(self, key: str) -> tuple[Any, float | None]:
        """Retrieve and deserialize a JSON value and its remaining TTL from the cache."""
        value, ttl = await self.store.read_with_ttl(key)
        if value is None:
            return None, None
        return JSONLoads(value), ttl


def create_cache_store() -> CacheStore:
    if settings.cache_store == CacheStoreEnum.POSTGRES:
        return PostgresCacheStore()
    else:
        return NullCacheStore()


cache = Cache(create_cache_store())


class CacheKeyValueStore:
    def _prefixed_key(self, key: str, collection: str | None) -> str:
        if collection:
            return f"{collection}:{key}"
        return key

    async def get(self, key: str, *, collection: str | None = None) -> dict[str, Any] | None:
        prefixed = self._prefixed_key(key, collection)
        return await cache.read_json(prefixed)

    async def put(
        self,
        key: str,
        value: Mapping[str, Any],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        prefixed = self._prefixed_key(key, collection)
        expires_in = timedelta(seconds=float(ttl)) if ttl is not None else timedelta(days=365 * 10)
        serialized = JSONDumps(dict(value))
        await cache.write(prefixed, serialized, expires_in)

    async def delete(self, key: str, *, collection: str | None = None) -> bool:
        prefixed = self._prefixed_key(key, collection)
        return await cache.delete(prefixed)

    async def ttl(self, key: str, *, collection: str | None = None) -> tuple[dict[str, Any] | None, float | None]:
        return await cache.read_json_with_ttl(self._prefixed_key(key, collection))

    async def get_many(self, keys: Sequence[str], *, collection: str | None = None) -> list[dict[str, Any] | None]:
        prefixed_keys = [self._prefixed_key(key, collection) for key in keys]
        return await cache.read_json_many(prefixed_keys)

    async def put_many(
        self,
        keys: Sequence[str],
        values: Sequence[Mapping[str, Any]],
        *,
        collection: str | None = None,
        ttl: SupportsFloat | None = None,
    ) -> None:
        for key, value in zip(keys, values, strict=True):
            await self.put(key, value, collection=collection, ttl=ttl)

    async def delete_many(self, keys: Sequence[str], *, collection: str | None = None) -> int:
        count = 0
        for key in keys:
            if await self.delete(key, collection=collection):
                count += 1
        return count

    async def ttl_many(
        self, keys: Sequence[str], *, collection: str | None = None
    ) -> list[tuple[dict[str, Any] | None, float | None]]:
        return [await self.ttl(key, collection=collection) for key in keys]
