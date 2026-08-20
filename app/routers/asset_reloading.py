from fastapi import APIRouter

from app.channels.base import AssetVersionChangedMessage, AssetVersionInfoMessage, Channel
from app.routers.dependencies import handle_stream
from config import logger
from config.enums import ChannelMessageType

router = APIRouter()


@handle_stream("version_refresh")
async def handle_version_broadcast(channel: Channel, **data: dict):
    message_type = data.get("type")
    version = data.get("version")

    if not version:
        logger.warning(f"Received version_refresh broadcast without version: {data}")
        return

    if message_type == ChannelMessageType.ASSET_VERSION_CHANGED:
        await channel.session.send(
            AssetVersionChangedMessage(
                topic_stream=channel.topic.stream, topic_params=channel.topic.params, version=version
            )
        )
    elif message_type == ChannelMessageType.ASSET_VERSION_INFO:
        await channel.session.send(
            AssetVersionInfoMessage(
                topic_stream=channel.topic.stream, topic_params=channel.topic.params, version=version
            )
        )
