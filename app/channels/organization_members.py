from app.channels.dependencies import is_org_authorized

from .base import Channel, ChannelRouter

router = ChannelRouter()


@router.on_subscribe("organization_members")
async def organization_members_subscribe(channel: Channel):
    if not is_org_authorized(channel):
        await channel.reject("Unauthorized access to organization members.")
        return
    await channel.accept()
