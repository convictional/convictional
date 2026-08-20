from app.channels.base import Channel, ChannelRouter
from app.channels.dependencies import is_current_user_authorized

#
# Router
#
#

router = ChannelRouter()


@router.on_subscribe("inbox_progress")
async def inbox_progress_subscribe(channel: Channel):
    if await is_current_user_authorized(channel):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to inbox progress")
