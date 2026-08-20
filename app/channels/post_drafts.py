from app.models.workspaces.posts import Post

from .base import Channel, ChannelRouter
from .live_documents import LiveDocumentSyncMessage, YjsAwarenessMessage, document_manager

router = ChannelRouter()


@router.on_subscribe("post_draft")
async def subscribe_to_post_draft(channel: Channel):
    post_id = channel.get_param("post_id")
    post = await Post.get_or_none(id=post_id, organization_id=channel.current_user.organization_id).prefetch_related(
        "workspace__collaborators__user"
    )

    if not post:
        await channel.reject("Post not found or access denied")
        return

    if not post.collaboration.can_be_accessed_by(channel.current_user):
        await channel.reject("Unauthorized")
        return

    await document_manager.subscribe(channel)


@router.on_receive("post_draft", LiveDocumentSyncMessage)
async def post_draft_sync(channel: Channel, data: LiveDocumentSyncMessage):
    await document_manager.sync_message(channel, data)


@router.on_receive("post_draft", YjsAwarenessMessage)
async def post_draft_awareness(channel: Channel, data: YjsAwarenessMessage):
    await document_manager.awareness_message(channel, data)


@router.on_unsubscribe("post_draft")
async def post_draft_unsubscribe(channel: Channel):
    await document_manager.unsubscribe(channel)
