from app.models.collaboration.live import Typing, email_thread_scope_key
from app.models.workspaces.email.thread import EmailThread

from .base import Channel, ChannelRouter
from .dependencies import TypingMessage

#
# Router
#
#

router = ChannelRouter()


@router.on_subscribe("email_thread_comments")
async def email_thread_comments_subscribe(channel: Channel):
    # A missing thread (e.g. deleted while a client still tries to subscribe) is unauthorized,
    # not an error — reject cleanly instead of raising DoesNotExist. Scope by org so a cross-org
    # id fails fast at the query rather than leaking existence through the access check.
    thread = await EmailThread.get_or_none(
        id=channel.get_param("email_thread_id"), organization_id=channel.current_user.organization_id
    ).prefetch_related("workspace__collaborators__user")
    if thread and thread.collaboration.can_be_accessed_by(channel.current_user):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to email thread comments.")


@router.on_receive("email_thread_comments", TypingMessage)
async def receive_typing_message(channel: Channel, message: TypingMessage):
    email_thread_id = channel.get_param("email_thread_id")
    user_id = channel.current_user.id

    typing = Typing(scope_key=email_thread_scope_key(email_thread_id))
    if message.is_typing:
        typing_user_ids = await typing.add_user(user_id)
    else:
        typing_user_ids = await typing.remove_user(user_id)

    await channel.topic.broadcast(typing_user_ids=typing_user_ids)


@router.on_unsubscribe("email_thread_comments")
async def email_thread_comments_unsubscribe(channel: Channel):
    email_thread_id = channel.get_param("email_thread_id")
    user_id = channel.current_user.id

    typing = Typing(scope_key=email_thread_scope_key(email_thread_id))
    typing_user_ids = await typing.remove_user(user_id)
    await channel.topic.broadcast(typing_user_ids=typing_user_ids)
