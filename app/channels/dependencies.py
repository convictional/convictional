from typing import ClassVar

from app.models.collaboration.workspace import Workspace
from config.enums import ChannelMessageType

from .base import Channel, ChannelMessage


class TypingMessage(ChannelMessage):
    _message_type: ClassVar[ChannelMessageType] = ChannelMessageType.TYPING
    is_typing: bool


async def is_current_user_authorized(channel: Channel) -> bool:
    user_id = channel.get_param("user_id")
    if user_id != str(channel.current_user.id):
        await channel.reject("Unauthorized access to channel")
        return False
    return True


def is_org_authorized(channel: Channel) -> bool:
    org_id = channel.get_param("organization_id")
    return str(channel.current_user.organization_id) == str(org_id)


async def is_workspace_authorized(channel: Channel) -> bool:
    # A missing workspace or a soft-deleted/absent underlying resource (e.g. an email thread
    # deleted while a client still tries to subscribe) is unauthorized, not an error — return
    # False so the handler rejects cleanly. fetch_resource() raises DoesNotExist in that case,
    # which the subscribe machinery would surface to Sentry as a spurious error, so use the
    # _or_none variant to fail closed quietly.
    workspace = await Workspace.get_or_none(id=channel.get_param("workspace_id")).prefetch_related(
        "collaborators__user"
    )
    if workspace is None:
        return False
    resource = await workspace.fetch_resource_or_none()
    if resource is None:
        return False
    return resource.collaboration.can_be_accessed_by(channel.current_user)
