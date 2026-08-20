from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from app.models.accounts import Group, User
from app.models.collaboration.workspace import (
    Attachment,
    Collaborator,
    Event,
)
from app.models.workspaces.chat import Chat, ChatMessage
from app.models.workspaces.documents import Document, DocumentComment
from app.models.workspaces.email.thread import EmailThread, EmailThreadComment
from app.models.workspaces.goals import Goal, GoalComment, GoalUpdate
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post, PostComment
from app.presenters.base import BasePresenter
from app.presenters.comment import CommentPresenter
from app.presenters.posts import PostCommentPresenter
from config import logger
from config.enums import EventAction
from infra.db import RecordModel

RecordableTypeMap: dict[str, type[RecordModel]] = {
    # Workspace Recordable types
    "Attachment": Attachment,
    "Collaborator": Collaborator,
    "EmailThreadComment": EmailThreadComment,
    # Goal Recordable types
    "Goal": Goal,
    "GoalComment": GoalComment,
    "GoalUpdate": GoalUpdate,
    # Other Workspace Recordable types
    "Meeting": Meeting,
    "Post": Post,
    "PostComment": PostComment,
    "EmailThread": EmailThread,
    "Document": Document,
    "DocumentComment": DocumentComment,
    "Chat": Chat,
    "ChatMessage": ChatMessage,
}
PrefetchTypeMap: dict[str, list[str]] = {
    EmailThreadComment.record_type: ["user", "email_thread"],
    Attachment.record_type: ["file", "workspace"],
    PostComment.record_type: ["user", "post"],
    GoalComment.record_type: ["user__avatar_file", "goal"],
    GoalUpdate.record_type: ["creator__avatar_file", "goal", "requested_by__avatar_file"],
}


def _detail_uuid(event: Event, field: str) -> UUID | None:
    if field in event.details and event.details[field][1]:
        return UUID(str(event.details[field][1]))
    return None


class EventPresenter(BasePresenter[Event]):
    recordable: RecordModel
    creator: User | None
    owner: User | None
    group: Group | None
    replies: list["EventPresenter"]

    @classmethod
    async def create_from_event(cls, event: Event) -> Self | None:
        from_list = await cls.create_from_list([event])
        return from_list[0] if from_list else None

    @classmethod
    async def create_from_list(cls, events: Iterable[Event]) -> list[Self]:
        creators = await User.filter(id__in=[e.creator_id for e in events]).select_related("avatar_file").all()
        creators_map = {c.id: c for c in creators}
        recordables_map = await cls.build_recordables(events)
        owners_map, groups_map = await cls._build_goal_detail_lookups(events)

        presenters = []
        for event in events:
            if event.creator_id not in creators_map and not event.is_system:
                continue

            if event.recordable_id not in recordables_map:
                continue

            presenter = cls(
                model=event,
                creator=creators_map.get(event.creator_id) if event.creator_id else None,
                recordable=recordables_map[event.recordable_id],
                owner=owners_map.get(uid) if (uid := _detail_uuid(event, "owner_id")) else None,
                group=groups_map.get(gid) if (gid := _detail_uuid(event, "group_id")) else None,
            )
            presenters.append(presenter)
        return presenters

    @classmethod
    async def _build_goal_detail_lookups(cls, events: Iterable[Event]) -> tuple[dict[UUID, User], dict[UUID, Group]]:
        owner_ids: set[UUID] = set()
        group_ids: set[UUID] = set()
        for event in events:
            if event.action != EventAction.GOAL_UPDATED:
                continue
            if uid := _detail_uuid(event, "owner_id"):
                owner_ids.add(uid)
            if gid := _detail_uuid(event, "group_id"):
                group_ids.add(gid)

        owners_map: dict[UUID, User] = {}
        if owner_ids:
            owners = await User.filter(id__in=list(owner_ids)).select_related("avatar_file").all()
            owners_map = {o.id: o for o in owners}

        groups_map: dict[UUID, Group] = {}
        if group_ids:
            groups = await Group.filter(id__in=list(group_ids)).all()
            groups_map = {g.id: g for g in groups}

        return owners_map, groups_map

    @classmethod
    async def build_recordables(cls, events: Iterable[Event]):
        recordable_types = {e.recordable_type for e in events}
        recordables_by_id: dict[UUID, RecordModel] = {}
        for recordable_type in recordable_types:
            recordable_ids = [e.recordable_id for e in events if e.recordable_type == recordable_type]
            recordables = await cls.get_recordables_by_type(recordable_type, recordable_ids)
            recordables_by_id.update(recordables)

        return recordables_by_id

    @classmethod
    async def get_recordables_by_type(cls, recordable_type: str, recordable_ids: list[UUID]):
        recordable_model = RecordableTypeMap.get(recordable_type, None)
        if not recordable_model:
            logger.error(f"Recordable type '{recordable_type}' not in RecordableTypeMap")
            return {}

        query = recordable_model.filter(id__in=recordable_ids)

        if recordable_type in PrefetchTypeMap:
            query = query.prefetch_related(*PrefetchTypeMap[recordable_type])

        recordables = await query.all()

        if recordable_model == EmailThreadComment:
            recordables = await CommentPresenter.create_from_list(recordables)  # type: ignore
        elif recordable_model == PostComment:
            recordables = await PostCommentPresenter.create_from_list(recordables)  # type: ignore
        elif recordable_model == GoalComment:
            recordables = await CommentPresenter.create_from_list(recordables)  # type: ignore

        return {r.id: r for r in recordables}


@dataclass
class TimelinePresenter:
    events: list[EventPresenter]
