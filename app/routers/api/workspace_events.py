from fastapi import APIRouter

from app.models.collaboration.workspace import Event
from app.presenters.activity import EventPresenter
from app.routers.dependencies import Channel, handle_stream
from config.enums import ChannelEventAction, ChannelEventResource

router = APIRouter(tags=["workspace events"])


@handle_stream("workspace_events")
async def workspace_events_json_broadcast(channel: Channel, **data) -> None:
    event_id = data.get("event_id")
    if not event_id or not channel.current_user:
        return

    event = await Event.get_or_none(id=event_id)
    if not event:
        return

    presenter = await EventPresenter.create_from_event(event)
    if not presenter:
        return

    await channel.send_event(
        ChannelEventResource.WORKSPACE_EVENT,
        ChannelEventAction.ADDED,
        event_id=str(event.id),
        event_action=event.action.value,
        recordable_type=event.recordable_type,
        recordable_id=str(event.recordable_id),
        creator_id=str(event.creator_id) if event.creator_id else None,
    )
