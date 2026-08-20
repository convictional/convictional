from app.models.workspaces.email.thread import EmailThread

from .base import Channel, ChannelRouter

#
# Helpers
#
#


async def is_authorized(channel: Channel) -> bool:
    thread_id = channel.get_param("thread_id")
    if not thread_id:
        await channel.reject("Missing thread_id parameter")
        return False

    email_thread = await EmailThread.get(id=thread_id).prefetch_related("workspace__collaborators__user")

    # Check if user can access this thread
    if email_thread.collaboration.can_be_accessed_by(channel.current_user):
        return True

    await channel.reject("Access denied to thread")
    return False


#
# Router
#
#

router = ChannelRouter()


@router.on_subscribe("email_thread")
async def email_thread_subscribe(channel: Channel):
    if await is_authorized(channel):
        await channel.accept()
