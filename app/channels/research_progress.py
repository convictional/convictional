from app.channels.base import Channel, ChannelRouter
from app.channels.dependencies import is_current_user_authorized

router = ChannelRouter()


@router.on_subscribe("research_progress")
async def research_progress_subscribe(channel: Channel):
    if await is_current_user_authorized(channel):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to research progress")
