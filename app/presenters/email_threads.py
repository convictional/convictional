from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.models.accounts import User
from app.models.collaboration.workspace import Event
from app.models.workspaces.email.thread import EmailMessage, EmailThread
from app.presenters.activity import EventPresenter
from app.presenters.base import BasePresenter
from config.enums import EventAction


@dataclass
class MessageTimelineItem:
    type: Literal["message"]
    item: EmailMessage
    created_at: datetime
    is_last_message: bool = False


@dataclass
class EventTimelineItem:
    type: Literal["event"]
    item: EventPresenter
    created_at: datetime


type TimelineItem = MessageTimelineItem | EventTimelineItem


class EmailThreadPresenter(BasePresenter[EmailThread]):
    current_user: User | None = None

    @property
    def sendable_by(self) -> str:
        current_user = self.current_user
        assert current_user is not None
        thread = self.model
        assignee = thread.workspace.assignee if thread.workspace.assignee_id else None
        is_new_thread = thread.external_thread_id is None

        if assignee and is_new_thread:
            is_creator = thread.creator_id == current_user.id
            is_assignee = assignee.id == current_user.id
            if is_creator and is_assignee:
                return "Sendable by you"
            elif is_creator:
                return f"Sendable by you or {assignee.display_name}"
            elif is_assignee:
                return f"Sendable by you or {thread.creator.display_name}"
            else:
                return f"Sendable by {thread.creator.display_name} or {assignee.display_name}"
        else:
            if thread.can_reply(current_user):
                return "Sendable by you (owner)"
            else:
                return f"Sendable by {thread.creator.display_name} (owner)"

    @property
    def send_button_tooltip(self) -> str:
        if self.model.external_thread_id is not None:
            return "Only the owner can send this draft"
        return "Only the owner or assignee can send this draft"

    async def build_timeline(self) -> list[TimelineItem]:
        messages_timeline = self._build_messages_timeline()
        events_timeline = await self._build_events_timeline()
        return self._merge_timelines(messages_timeline, events_timeline)

    def _build_messages_timeline(self):
        timeline = [
            MessageTimelineItem(
                type="message", item=message, created_at=message.received_at or message.sent_at or message.created_at
            )
            for message in self.model.sorted_conversation
        ]
        if len(timeline) > 0:
            timeline[-1].is_last_message = True
        return timeline

    # Comment edits/deletes record events so the mailbox engine can sync them, but they are
    # mailbox-only signals, not thread activity — never render them as activity rows.
    _TIMELINE_EXCLUDED_ACTIONS = [
        EventAction.EMAIL_THREAD_COMMENT_EDITED,
        EventAction.EMAIL_THREAD_COMMENT_DELETED,
    ]

    async def _build_events_timeline(self):
        events = await Event.filter(
            Event.filters.by_workspace(self.model.workspace_id),
            ~Event.filters.by_actions(self._TIMELINE_EXCLUDED_ACTIONS),
        ).order_by("created_at")
        event_presenters = await EventPresenter.create_from_list(events)
        event_timeline = [
            EventTimelineItem(type="event", item=event_presenter, created_at=event_presenter.model.created_at)
            for event_presenter in event_presenters
        ]
        return event_timeline

    def _merge_timelines(
        self, messages: list[MessageTimelineItem], events: list[EventTimelineItem]
    ) -> list[TimelineItem]:
        """
        Merges messages and events into a single timeline, sorted by created_at while preserving the order of each type
        """
        merged_timeline: list[TimelineItem] = []
        messages_index, events_index = 0, 0

        while messages_index < len(messages) and events_index < len(events):
            if messages[messages_index].created_at <= events[events_index].created_at:
                merged_timeline.append(messages[messages_index])
                messages_index += 1
            else:
                merged_timeline.append(events[events_index])
                events_index += 1

        # Append any remaining items from either timeline
        merged_timeline.extend(messages[messages_index:])
        merged_timeline.extend(events[events_index:])

        return merged_timeline
