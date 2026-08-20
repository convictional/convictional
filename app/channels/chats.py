from app.channels.dependencies import TypingMessage, is_org_authorized, is_workspace_authorized
from app.models.collaboration.live import Typing

from .base import Channel, ChannelRouter

router = ChannelRouter()


def chat_scope_key(chat_id: str) -> str:
    return f"chat:{chat_id}"


@router.on_subscribe("chats_index")
async def chats_index_subscribe(channel: Channel):
    if not is_org_authorized(channel):
        await channel.reject("Unauthorized access to chats index.")
        return
    await channel.accept()


@router.on_subscribe("chat")
async def chat_subscribe(channel: Channel):
    if not channel.get_param("chat_id"):
        await channel.reject("Missing chat_id parameter")
        return

    if await is_workspace_authorized(channel):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to chat")


@router.on_receive("chat", TypingMessage)
async def receive_typing(channel: Channel, message: TypingMessage):
    chat_id = channel.get_param("chat_id")
    user_id = channel.current_user.id

    typing = Typing(scope_key=chat_scope_key(chat_id))
    if message.is_typing:
        typing_user_ids = await typing.add_user(user_id)
    else:
        typing_user_ids = await typing.remove_user(user_id)

    await channel.topic.broadcast(typing_user_ids=typing_user_ids)


@router.on_unsubscribe("chat")
async def chat_unsubscribe(channel: Channel):
    chat_id = channel.get_param("chat_id")
    user_id = channel.current_user.id

    typing = Typing(scope_key=chat_scope_key(chat_id))
    typing_user_ids = await typing.remove_user(user_id)
    await channel.topic.broadcast(typing_user_ids=typing_user_ids)
