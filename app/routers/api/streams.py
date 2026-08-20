from dataclasses import dataclass
from typing import Any
from uuid import UUID

from app.channels.base import BaseChannelMessage
from app.routers.api.serializers import fetch_reaction_users, serialize_reactions
from app.routers.dependencies import Channel, handle_stream
from config.enums import ChannelEventAction, ChannelEventResource


def is_from_current_user(channel: Channel, data: dict[str, Any]) -> bool:
    author_id = data.get("author_id")
    return bool(author_id and str(author_id) == str(channel.current_user.id))


def register_live_document_handler(stream: str) -> None:
    """Register the broadcast handler for a collaborative live-document stream.

    These streams (documents, email drafts, post drafts, meeting agendas) carry
    raw Yjs sync/awareness data, sent verbatim to every subscriber. Each surface
    handles it identically, so each feature's api router registers its own stream
    here rather than duplicating the handler body or keeping a central registry
    of consumers.
    """

    @handle_stream(stream)
    async def handle_live_document(channel: Channel, **data: Any) -> None:
        await channel.session.send(BaseChannelMessage.from_dict(data))


@dataclass
class CommentMarkStream:
    """Channel stream helpers for comment-mark-based systems (documents, post drafts)."""

    model_class: Any
    parent_id_field: str
    resource: ChannelEventResource
    comment_response_fn: Any

    def _belongs_to_channel(self, comment: Any, channel: Channel) -> bool:
        return str(getattr(comment, self.parent_id_field)) == channel.topic.params.get(self.parent_id_field)

    async def send_comment(self, channel: Channel, comment_id: UUID, action: ChannelEventAction) -> None:
        comment = await self.model_class.get_or_none(id=comment_id).prefetch_related("user__avatar_file")
        if not comment or not self._belongs_to_channel(comment, channel):
            return
        users_by_id = await fetch_reaction_users([comment])
        await channel.send_event(
            resource=self.resource,
            action=action,
            **self.comment_response_fn(comment, users_by_id).model_dump(mode="json"),
        )

    async def send_resolved(self, channel: Channel, comment_mark_id: str) -> None:
        parent_id = channel.topic.params.get(self.parent_id_field)
        comments = (
            await self.model_class.filter(**{self.parent_id_field: parent_id, "comment_mark_id": comment_mark_id})
            .order_by("created_at")
            .prefetch_related("user__avatar_file")
        )
        users_by_id = await fetch_reaction_users(comments)
        await channel.send_event(
            resource=self.resource,
            action=ChannelEventAction.RESOLVED,
            comment_mark_id=comment_mark_id,
            comments=[self.comment_response_fn(c, users_by_id).model_dump(mode="json") for c in comments],
        )

    async def send_reaction(self, channel: Channel, comment_id: UUID) -> None:
        comment = await self.model_class.get_or_none(id=comment_id)
        if not comment or not self._belongs_to_channel(comment, channel):
            return
        users_by_id = await fetch_reaction_users([comment])
        serialized = serialize_reactions(comment.reactions, users_by_id)
        await channel.send_event(
            resource=self.resource,
            action=ChannelEventAction.REACTION_TOGGLED,
            comment_id=str(comment.id),
            reactions={k: [u.model_dump() for u in v] for k, v in serialized.items()},
        )
