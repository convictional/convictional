from app.channels.dependencies import is_workspace_authorized

from .base import Channel, ChannelRouter

#
# Router
#
#

router = ChannelRouter()


@router.on_subscribe("workspace_events")
async def workspace_events_subscribe(channel: Channel):
    if await is_workspace_authorized(channel):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to workspace events.")
