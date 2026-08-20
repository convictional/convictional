from app.models.workspaces.email.thread import EmailMessage, EmailThread

from .base import Channel, ChannelRouter
from .live_documents import LiveDocumentSyncMessage, YjsAwarenessMessage, document_manager

#
# Router
#
#

router = ChannelRouter()


@router.on_subscribe("email_thread_draft")
async def subscribe_to_draft_updates(channel: Channel):
    """Subscribe to draft updates for a specific email thread."""
    thread_id = channel.get_param("thread_id")
    if not thread_id:
        await channel.reject("Missing thread_id parameter")
        return

    thread = await EmailThread.get(
        id=thread_id, organization_id=channel.current_user.organization_id
    ).prefetch_related("workspace__collaborators__user")

    # Only thread collaborators can subscribe to draft updates
    if thread.collaboration.can_be_accessed_by(channel.current_user):
        await channel.accept()
    else:
        await channel.reject("Unauthorized access to thread draft updates")


@router.on_subscribe("email_draft")
async def subscribe_to_email_draft_live_document(channel: Channel):
    """Subscribe to live document updates for email draft collaboration."""
    message_id = channel.get_param("message_id")
    if not message_id:
        await channel.reject("Missing message_id parameter")
        return

    message = await EmailMessage.get(
        id=message_id, organization_id=channel.current_user.organization_id
    ).prefetch_related("thread__workspace__collaborators__user")

    # Only thread collaborators can subscribe to live document updates
    if message.thread.collaboration.can_be_accessed_by(channel.current_user):
        await document_manager.subscribe(channel)
    else:
        await channel.reject("Unauthorized access to email draft live document")


@router.on_unsubscribe("email_draft")
async def unsubscribe_from_email_draft_live_document(channel: Channel):
    """Unsubscribe from live document updates for email draft collaboration."""
    await document_manager.unsubscribe(channel)


@router.on_receive("email_draft", LiveDocumentSyncMessage)
async def email_draft_sync_message(channel: Channel, data: LiveDocumentSyncMessage):
    """Handle live document sync messages for email draft collaboration."""
    await document_manager.sync_message(channel, data)


@router.on_receive("email_draft", YjsAwarenessMessage)
async def email_draft_awareness_message(channel: Channel, data: YjsAwarenessMessage):
    """Handle awareness messages for email draft collaboration."""
    await document_manager.awareness_message(channel, data)
