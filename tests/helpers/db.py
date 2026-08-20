import pytest_asyncio
from pytest import FixtureRequest
from tortoise import Tortoise
from tortoise.contrib.test import _init_db, getDBConfig


@pytest_asyncio.fixture()
async def setup_in_memory_db(request: FixtureRequest):
    async def _configure(modules=[]):
        base_config = getDBConfig(app_label="convictional", modules=modules)
        base_connection = base_config["connections"]["convictional"]

        config = {
            "connections": {"default": base_connection, "auxiliary": base_connection},
            "apps": {
                "convictional": {"default_connection": "default", "models": modules},
                "migrations": {"models": ["aerich.models"]},
            },
        }

        await _init_db(config)

    yield _configure
    await Tortoise._drop_databases()
