from app.channels.base import Channel, ChannelRouter
from app.channels.live_documents import LiveDocumentSyncMessage, YjsAwarenessMessage, document_manager
from app.models.workspaces.meetings import Meeting

router = ChannelRouter()


@router.on_subscribe("meeting_agenda")
async def meeting_agenda_stream(channel: Channel):
    meeting_id = channel.get_param("meeting_id")
    meeting = await Meeting.get_or_none(id=meeting_id).prefetch_related("workspace__collaborators__user")
    if not meeting:
        await channel.reject("Meeting not found or access denied")
        return

    if not meeting.collaboration.can_be_accessed_by(channel.current_user):
        await channel.reject("Unauthorized access to meeting agenda")
        return

    await document_manager.subscribe(channel)


@router.on_receive("meeting_agenda", LiveDocumentSyncMessage)
async def meeting_agenda_sync(channel: Channel, data: LiveDocumentSyncMessage):
    await document_manager.sync_message(channel, data)


@router.on_receive("meeting_agenda", YjsAwarenessMessage)
async def meeting_agenda_awareness(channel: Channel, data: YjsAwarenessMessage):
    await document_manager.awareness_message(channel, data)


@router.on_unsubscribe("meeting_agenda")
async def meeting_agenda_unsubscribe(channel: Channel):
    await document_manager.unsubscribe(channel)


@router.on_subscribe("meeting_bot")
async def meeting_bot_subscribe(channel: Channel):
    meeting_id = channel.get_param("meeting_id")
    meeting = await Meeting.get_or_none(id=meeting_id).prefetch_related("workspace__collaborators__user")
    if not meeting or not meeting.collaboration.can_be_accessed_by(channel.current_user):
        await channel.reject("Meeting not found or access denied")
        return
    await channel.accept()
