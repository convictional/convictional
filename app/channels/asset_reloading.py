from datetime import timedelta

from app.helpers.assets import asset_version_hash
from config import logger
from infra.cache import cache
from infra.messaging import Topic

from .base import AssetVersionChangedMessage, AssetVersionInfoMessage, Channel, ChannelMessageType, ChannelRouter

router = ChannelRouter()

CACHE_KEY = "version_refresh:last_broadcast"


async def get_last_broadcasted_version() -> str | None:
    return await cache.read(CACHE_KEY)


async def has_asset_version_changed(current_version: str) -> bool:
    last_broadcast_version = await get_last_broadcasted_version()
    return bool(last_broadcast_version) and last_broadcast_version != current_version


@router.on_subscribe("version_refresh")
async def asset_version_refresh_subscribe(channel: Channel):
    await channel.accept()
    current_version = asset_version_hash()

    if await has_asset_version_changed(current_version):
        await channel.session.send(
            AssetVersionChangedMessage(
                topic_stream=channel.topic.stream, topic_params=channel.topic.params, version=current_version
            )
        )

    await channel.session.send(
        AssetVersionInfoMessage(
            topic_stream=channel.topic.stream, topic_params=channel.topic.params, version=current_version
        )
    )


async def asset_version_broadcast_on_startup() -> None:
    current_version = asset_version_hash()

    if await has_asset_version_changed(current_version):
        logger.info("Asset version changed, broadcasting to all connected clients")

        topic = Topic("version_refresh")
        await topic.broadcast(type=ChannelMessageType.ASSET_VERSION_CHANGED, version=current_version)

        await cache.write(CACHE_KEY, current_version, timedelta(days=30))
