from app.channels.base import Channel, ChannelRouter
from app.channels.dependencies import is_current_user_authorized

#
# Router
#
#

router = ChannelRouter()


@router.on_subscribe("mailbox_sync")
async def mailbox_sync_subscribe(channel: Channel):
    if await is_current_user_authorized(channel):
        await channel.accept()
