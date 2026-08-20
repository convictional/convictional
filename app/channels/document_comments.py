from app.models.workspaces.documents import Document

from .base import Channel, ChannelRouter

router = ChannelRouter()


@router.on_subscribe("document_comments")
async def subscribe_to_document_comments(channel: Channel):
    document_id = channel.get_param("document_id")
    document = await Document.get_or_none(
        id=document_id, organization_id=channel.current_user.organization_id
    ).prefetch_related("workspace__collaborators__user")

    if not document:
        await channel.reject("Document not found or access denied")
        return

    if not document.collaboration.is_collaborator(channel.current_user):
        await channel.reject("Unauthorized")
        return

    await channel.accept()
