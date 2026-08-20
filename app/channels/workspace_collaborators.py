from uuid import UUID

from app.channels.dependencies import is_workspace_authorized
from app.models.collaboration.live import Presence, workspace_scope_key

from .base import Channel, ChannelRouter

#
# Helpers
#
#


async def ensure_presence(channel: Channel, workspace_id: UUID):
    presence = Presence(scope_key=workspace_scope_key(workspace_id))
    present_user_ids = await presence.add_user(channel.current_user.id)
    await channel.topic.broadcast(present_user_ids=present_user_ids)


async def remove_presence(channel: Channel, workspace_id: UUID):
    presence = Presence(scope_key=workspace_scope_key(workspace_id))
    present_user_ids = await presence.remove_user(channel.current_user.id)
    await channel.topic.broadcast(present_user_ids=present_user_ids)


#
# Router
#
#

router = ChannelRouter()


@router.on_subscribe("workspace_collaborators")
async def workspace_collaborators_subscribe(channel: Channel):
    if not await is_workspace_authorized(channel):
        await channel.reject("Unauthorized access to workspace collaborators.")
        return

    await channel.accept()  # Accept first to allow presence broadcast to update the current user's page
    await ensure_presence(channel, channel.get_param("workspace_id"))


@router.on_keepalive("workspace_collaborators")
async def workspace_collaborators_keepalive(channel: Channel):
    await ensure_presence(channel, channel.get_param("workspace_id"))


@router.on_unsubscribe("workspace_collaborators")
async def workspace_collaborators_unsubscribe(channel: Channel):
    if not await is_workspace_authorized(channel):
        return

    await remove_presence(channel, channel.get_param("workspace_id"))
