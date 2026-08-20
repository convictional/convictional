import pytest

from infra.cache import PostgresCacheStore, cache


@pytest.fixture()
def use_postgres_cache():
    original_store = cache.store
    cache.store = PostgresCacheStore()
    yield
    cache.store = original_store
