import asyncio
from datetime import timedelta

import pytest
from freezegun import freeze_time

from infra.cache import Cache, CacheKeyValueStore, PostgresCacheStore


@pytest.mark.asyncio
async def test_postgres_cache():
    store = PostgresCacheStore()

    # Test basic write, read, delete operations
    key = "postgres_test_key"
    value = "postgres_test_value"
    expires_in = timedelta(seconds=30)

    await store.delete(key)
    assert not await store.exists(key)

    await store.write(key, value, expires_in)
    assert await store.exists(key)

    retrieved = await store.read(key)
    assert retrieved == value

    await store.delete(key)
    assert not await store.exists(key)
    assert await store.read(key) is None

    # Test updating an existing entry
    key = "update_test_key"
    value1 = "first_value"
    value2 = "second_value"
    expires_in = timedelta(minutes=5)

    # Clean up any existing entries
    await store.delete(key)

    await store.write(key, value1, expires_in)
    assert await store.read(key) == value1

    await store.write(key, value2, expires_in)
    assert await store.read(key) == value2

    await store.delete(key)

    # Test JSON
    key = "postgres_json_key"
    data = {"name": "postgres_test", "nested": {"value": 42}}
    expires_in = timedelta(minutes=5)

    # Clean up any existing entries
    await store.delete(key)
    await store.write_json(key, data, expires_in)
    retrieved = await store.read_json(key)
    assert retrieved == data
    await store.delete(key)

    # Test generators
    cache = Cache(store)
    key = "fetch_key"
    expires_in = timedelta(minutes=5)

    async def async_generator():
        await asyncio.sleep(0.001)  # Simulate async work
        return {"generated": True, "value": 123}

    def sync_generator():
        return {"generated": True, "value": 456}

    result1 = await cache.fetch(key, expires_in, async_generator)
    result2 = await cache.fetch(key, expires_in, async_generator)
    assert result1 == result2 == {"generated": True, "value": 123}

    await cache.delete(key)
    result3 = await cache.fetch(key, expires_in, sync_generator)
    assert result3 == {"generated": True, "value": 456}


@pytest.mark.asyncio
async def test_postgres_cache_set_operations():
    cache = Cache(PostgresCacheStore())
    key = "test_set"

    # Test adding members to a new set
    assert await cache.set_add(key, "member1") is True
    assert await cache.set_read(key) == {"member1"}
    assert await cache.set_add(key, "member2") is True
    assert await cache.set_read(key) == {"member1", "member2"}

    # Test adding duplicate member
    assert await cache.set_add(key, "member1") is False
    assert await cache.set_read(key) == {"member1", "member2"}

    # Test removing existing member
    assert await cache.set_remove(key, "member1") is True
    assert await cache.set_read(key) == {"member2"}

    # Test removing non-existent member
    assert await cache.set_remove(key, "nonexistent") is False
    assert await cache.set_read(key) == {"member2"}

    # Test removing from non-existent set
    await cache.delete(key)
    assert not await cache.exists(key)
    assert await cache.set_read(key) == set()
    assert await cache.set_remove(key, "member2") is False

    # Test adding to non-existent set creates it
    assert await cache.set_add(key, "new_member") is True
    assert await cache.exists(key)
    assert await cache.set_read(key) == {"new_member"}

    # Test removing last member deletes the set
    assert await cache.set_remove(key, "new_member") is True
    assert not await cache.exists(key)
    assert await cache.set_read(key) == set()


@pytest.mark.asyncio
async def test_postgres_cache_set_add_refreshes_expiry():
    cache = Cache(PostgresCacheStore())
    key = "presence_set"

    with freeze_time("2026-01-01 12:00:00") as frozen_time:
        await cache.set_add(key, "m1", expires_in=timedelta(seconds=60))

        # Re-adding an existing member returns False but must still push the
        # set's expiry forward — presence keepalives rely on this refresh.
        frozen_time.tick(timedelta(seconds=40))
        assert await cache.set_add(key, "m1", expires_in=timedelta(seconds=60)) is False

        # 80s after the first add (would have expired) but 40s after the refresh.
        frozen_time.tick(timedelta(seconds=40))
        assert await cache.set_read(key) == {"m1"}

        # Past the refreshed expiry.
        frozen_time.tick(timedelta(seconds=40))
        assert await cache.set_read(key) == set()

    await cache.delete(key)


@pytest.mark.asyncio
async def test_postgres_cache_expire():
    store = PostgresCacheStore()
    cache = Cache(store)
    key = "expire_test_key"
    value = "test_value"

    # Test expire on non-existent key returns False
    assert await cache.expire(key, timedelta(seconds=10)) is False

    with freeze_time("2024-01-01 12:00:00") as frozen_time:
        # Create a cache entry without expiration
        await store.write(key, value, timedelta(hours=1))
        assert await store.exists(key)

        # Test expire on existing key returns True and sets expiration
        assert await cache.expire(key, timedelta(seconds=10)) is True
        assert await store.exists(key)  # Should still exist

        # Move time forward past expiration
        frozen_time.tick(delta=timedelta(seconds=11))

        # Verify the key has expired
        assert not await store.exists(key)
        assert await store.read(key) is None

        # Test expire updates existing expiration
        await store.write(key, value, timedelta(hours=1))
        assert await cache.expire(key, timedelta(seconds=30)) is True
        assert await store.exists(key)  # Should still exist since 30 seconds hasn't passed


@pytest.mark.asyncio
@pytest.mark.usefixtures("use_postgres_cache")
async def test_postgres_key_value_store():
    kv = CacheKeyValueStore()
    key = "kv_test_key"
    collection = "test_collection"

    # Clean up
    await kv.delete(key, collection=collection)
    await kv.delete(key)

    # Test basic get/put without collection
    assert await kv.get(key) is None
    await kv.put(key, {"foo": "bar", "count": 42})
    result = await kv.get(key)
    assert result == {"foo": "bar", "count": 42}
    await kv.delete(key)
    assert await kv.get(key) is None

    # Test get/put with collection prefix
    await kv.put(key, {"data": "with_collection"}, collection=collection)
    assert await kv.get(key) is None  # No collection prefix
    assert await kv.get(key, collection=collection) == {"data": "with_collection"}

    # Test TTL
    await kv.put(key, {"ttl_test": True}, collection=collection, ttl=60.0)
    value, remaining_ttl = await kv.ttl(key, collection=collection)
    assert value == {"ttl_test": True}
    assert remaining_ttl is not None
    assert 55 < remaining_ttl <= 60

    # Test delete returns True when entry exists
    assert await kv.delete(key, collection=collection) is True
    assert await kv.delete(key, collection=collection) is False

    # Test bulk operations
    keys = ["bulk1", "bulk2", "bulk3"]
    values = [{"idx": 1}, {"idx": 2}, {"idx": 3}]
    await kv.put_many(keys, values, collection=collection, ttl=120)
    results = await kv.get_many(keys, collection=collection)
    assert results == values

    ttl_results = await kv.ttl_many(keys, collection=collection)
    for val, ttl_val in ttl_results:
        assert val is not None
        assert ttl_val is not None and ttl_val > 0

    deleted_count = await kv.delete_many(keys, collection=collection)
    assert deleted_count == 3


@pytest.mark.asyncio
@pytest.mark.usefixtures("use_postgres_cache")
async def test_postgres_cache_delete_returns_existed():
    store = PostgresCacheStore()
    key = "delete_return_test"

    # Delete non-existent key returns False
    assert await store.delete(key) is False

    # Create key
    await store.write(key, "value", timedelta(hours=1))

    # Delete existing key returns True
    assert await store.delete(key) is True

    # Delete again returns False (already deleted)
    assert await store.delete(key) is False
