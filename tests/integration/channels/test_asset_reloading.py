from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.asset_reloading import CACHE_KEY, asset_version_broadcast_on_startup
from config.enums import ChannelMessageType
from infra.cache import cache
from infra.messaging import Topic
from tests.helpers.app import AppClient


@pytest.mark.asyncio
async def test_version_refresh_subscribe_sends_version_info(client: AppClient, use_postgres_cache):
    with patch("app.channels.asset_reloading.asset_version_hash", return_value="abc123"):
        await cache.delete(CACHE_KEY)

        topic = Topic("version_refresh")

        async with client.connect_websocket("/channels") as ws:
            await ws.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})

            response = await ws.receive_json()
            assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED
            assert response["topic_stream"] == topic.stream

            version_info = await ws.receive_json()
            assert version_info["type"] == ChannelMessageType.ASSET_VERSION_INFO
            assert version_info["version"] == "abc123"
            assert version_info["topic_stream"] == topic.stream


@pytest.mark.asyncio
async def test_version_refresh_unsigned_subscribe_sends_version_info(client: AppClient, use_postgres_cache):
    """An unsigned subscribe (topic_stream/topic_params) is accepted and routed, like the signed form."""
    with patch("app.channels.asset_reloading.asset_version_hash", return_value="abc123"):
        await cache.delete(CACHE_KEY)

        async with client.connect_websocket("/channels") as ws:
            await ws.send_json({"type": "subscribe", "topic_stream": "version_refresh", "topic_params": {}})

            response = await ws.receive_json()
            assert response["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED

            version_info = await ws.receive_json()
            assert version_info["type"] == ChannelMessageType.ASSET_VERSION_INFO
            assert version_info["version"] == "abc123"


@pytest.mark.asyncio
async def test_version_refresh_detects_version_change_on_subscribe(client: AppClient, use_postgres_cache):
    """Verify VERSION_CHANGED sent when cached version differs from current"""
    with patch("app.channels.asset_reloading.asset_version_hash", return_value="new456"):
        await cache.write(CACHE_KEY, "old123", timedelta(days=30))

        topic = Topic("version_refresh")

        async with client.connect_websocket("/channels") as ws:
            await ws.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})

            await ws.receive_json()

            version_changed = await ws.receive_json()
            assert version_changed["type"] == ChannelMessageType.ASSET_VERSION_CHANGED
            assert version_changed["version"] == "new456"
            assert version_changed["topic_stream"] == topic.stream

            version_info = await ws.receive_json()
            assert version_info["type"] == ChannelMessageType.ASSET_VERSION_INFO
            assert version_info["version"] == "new456"
            assert version_info["topic_stream"] == topic.stream


@pytest.mark.asyncio
async def test_broadcast_version_on_startup_with_version_change(client: AppClient, use_postgres_cache):
    with patch("app.channels.asset_reloading.asset_version_hash", return_value="deploy789"):
        await cache.write(CACHE_KEY, "old456", timedelta(days=30))

        with patch("infra.messaging.Topic.broadcast", new_callable=AsyncMock) as mock_broadcast:
            await asset_version_broadcast_on_startup()

            cached = await cache.read(CACHE_KEY)
            assert cached == "deploy789"

            mock_broadcast.assert_called_once()
            call_kwargs = mock_broadcast.call_args[1]
            assert call_kwargs["type"] == "asset_version_changed"
            assert call_kwargs["version"] == "deploy789"


@pytest.mark.asyncio
async def test_version_refresh_no_version_changed_when_same_version(client: AppClient, use_postgres_cache):
    """Verify VERSION_CHANGED not sent when cached version matches current"""
    with patch("app.channels.asset_reloading.asset_version_hash", return_value="same789"):
        await cache.write(CACHE_KEY, "same789", timedelta(days=30))

        topic = Topic("version_refresh")

        async with client.connect_websocket("/channels") as ws:
            await ws.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})

            subscription_confirmed = await ws.receive_json()
            assert subscription_confirmed["type"] == ChannelMessageType.SUBSCRIPTION_CONFIRMED

            version_info = await ws.receive_json()
            assert version_info["type"] == ChannelMessageType.ASSET_VERSION_INFO
            assert version_info["version"] == "same789"


@pytest.mark.asyncio
async def test_version_refresh_resubscribe_after_version_change(client: AppClient, use_postgres_cache):
    """Verify resubscription after version change still receives current version"""
    await cache.write(CACHE_KEY, "initial789", timedelta(days=30))

    topic = Topic("version_refresh")

    with patch("app.channels.asset_reloading.asset_version_hash", return_value="initial789"):
        async with client.connect_websocket("/channels") as ws:
            await ws.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})
            await ws.receive_json()
            version_info_1 = await ws.receive_json()
            assert version_info_1["type"] == ChannelMessageType.ASSET_VERSION_INFO
            assert version_info_1["version"] == "initial789"

    with patch("app.channels.asset_reloading.asset_version_hash", return_value="updated999"):
        async with client.connect_websocket("/channels") as ws:
            await ws.send_json({"type": "subscribe", "topic_stream": topic.stream, "topic_params": topic.params})
            await ws.receive_json()

            version_changed = await ws.receive_json()
            assert version_changed["type"] == ChannelMessageType.ASSET_VERSION_CHANGED
            assert version_changed["version"] == "updated999"

            version_info_2 = await ws.receive_json()
            assert version_info_2["type"] == ChannelMessageType.ASSET_VERSION_INFO
            assert version_info_2["version"] == "updated999"
