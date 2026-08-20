from app.models.workspaces.posts import Post

from .base import Channel, ChannelRouter

router = ChannelRouter()


@router.on_subscribe("post_draft_comments")
async def subscribe_to_post_draft_comments(channel: Channel):
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

    await channel.accept()
