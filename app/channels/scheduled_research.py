from app.channels.base import Channel, ChannelRouter
from app.channels.dependencies import is_current_user_authorized
from infra.messaging import Topic

router = ChannelRouter()


@router.on_subscribe("scheduled_research")
async def scheduled_research_subscribe(channel: Channel):
    if not await is_current_user_authorized(channel):
        return
    await channel.accept()


@router.on_subscribe("scheduled_research_preview")
async def scheduled_research_preview_subscribe(channel: Channel):
    if channel.get_param("user_id") != str(channel.current_user.id):
        await channel.reject("Unauthorized access to preview channel")
        return

    await channel.accept()

    preview_id = channel.get_param("preview_id")
    if not preview_id:
        return

    await Topic("scheduled_research_preview", preview_id=preview_id, user_id=str(channel.current_user.id)).broadcast(
        action="start"
    )
