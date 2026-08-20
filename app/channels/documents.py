from app.models.workspaces.documents import Document

from .base import Channel, ChannelRouter
from .live_documents import LiveDocumentSyncMessage, YjsAwarenessMessage, document_manager

router = ChannelRouter()


@router.on_subscribe("document")
async def subscribe_to_document(channel: Channel):
    document_id = channel.get_param("document_id")
    document = await Document.get_or_none(
        id=document_id, organization_id=channel.current_user.organization_id
    ).prefetch_related("workspace__collaborators__user")

    if not document:
        await channel.reject("Document not found or access denied")
        return

    # Only collaborators get Yjs write access — org members who aren't collaborators
    # see the readonly show page and must not be able to sync edits via WebSocket
    if not document.collaboration.is_collaborator(channel.current_user):
        await channel.reject("Unauthorized")
        return

    await document_manager.subscribe(channel)


@router.on_receive("document", LiveDocumentSyncMessage)
async def document_sync(channel: Channel, data: LiveDocumentSyncMessage):
    await document_manager.sync_message(channel, data)


@router.on_receive("document", YjsAwarenessMessage)
async def document_awareness(channel: Channel, data: YjsAwarenessMessage):
    await document_manager.awareness_message(channel, data)


@router.on_unsubscribe("document")
async def document_unsubscribe(channel: Channel):
    await document_manager.unsubscribe(channel)
