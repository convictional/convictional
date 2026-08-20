from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.workspaces.goals import Goal, GoalComment
from app.presenters.accounts import GroupMCPPresenter
from app.presenters.activity import EventPresenter, TimelinePresenter
from app.presenters.comment import CommentPresenter
from config.enums import EventAction, GoalStatus


@dataclass
class GoalTimelinePresenter(TimelinePresenter):
    goal_status: GoalStatus = GoalStatus.ON_TRACK

    def __post_init__(self):
        for event in self.events:
            event.replies = []

        reply_events_by_parent: dict[UUID, list[EventPresenter]] = defaultdict(list)
        parent_event_by_comment: dict[UUID, EventPresenter] = {}

        for event in self.events:
            if event.action != EventAction.GOAL_COMMENTED:
                continue
            recordable = event.recordable.model if isinstance(event.recordable, CommentPresenter) else event.recordable
            if not isinstance(recordable, GoalComment):
                continue
            if recordable.parent_id is not None:
                reply_events_by_parent[recordable.parent_id].append(event)
            else:
                parent_event_by_comment[recordable.id] = event

        grouped_reply_ids: set[UUID] = set()
        for comment_id, replies in reply_events_by_parent.items():
            parent_event = parent_event_by_comment.get(comment_id)
            if not parent_event:
                continue
            parent_event.replies = sorted(replies, key=lambda e: e.model.created_at)
            grouped_reply_ids.update(e.model.id for e in replies)

        self.events = [e for e in self.events if e.model.id not in grouped_reply_ids]


class GoalCommentMCPPresenter(BaseModel):
    model_config = ConfigDict(title="Comment")

    id: str = Field(description="Unique ID")
    content: str = Field(description="Comment text")
    author_name: str | None = Field(description="Author's display name")
    created_at: datetime = Field(description="Post time")
    replies: list["GoalCommentMCPPresenter"] = Field(description="Nested replies")

    @classmethod
    def from_comment(
        cls, comment: GoalComment, replies_by_parent: dict[UUID, list[GoalComment]]
    ) -> "GoalCommentMCPPresenter":
        return cls(
            id=str(comment.id),
            content=comment.content,
            author_name=comment.user.name if comment.user else None,
            created_at=comment.created_at,
            replies=[cls.from_comment(r, replies_by_parent) for r in replies_by_parent.get(comment.id, [])],
        )

    @classmethod
    def from_comments(
        cls, comments: list[GoalComment], replies_by_parent: dict[UUID, list[GoalComment]]
    ) -> list["GoalCommentMCPPresenter"]:
        return [cls.from_comment(c, replies_by_parent) for c in comments]


class GoalMCPPresenter(BaseModel):
    model_config = ConfigDict(title="Goal")

    id: str = Field(description="Unique ID")
    global_id: str = Field(
        description="Global ID for use with the content search API (e.g. gid://convictional/Goal/<id>)"
    )
    title: str = Field(description="Goal title")
    description: str = Field(description="Goal description")
    status: str = Field(description="on_track, at_risk, or off_track")
    progress: float | None = Field(description="0.0 to 1.0, or null when progress isn't tracked")
    target_date: date | None = Field(description="Due date")
    start_date: date | None = Field(description="When the goal was started")
    created_at: datetime = Field(description="When the goal was created")
    owner_id: str | None = Field(description="Owner user ID")
    owner_name: str | None = Field(description="Owner's display name")
    group: GroupMCPPresenter | None = Field(description="Assigned group")
    is_subgoal: bool = Field(description="Whether this is a child of another goal")
    parent_id: str | None = Field(description="Parent goal ID if this is a subgoal")
    subgoal_count: int = Field(description="Number of direct subgoals")
    comment_count: int = Field(description="Number of top-level comments")
    comments: list[GoalCommentMCPPresenter] = Field(description="Top level comments")
    subgoals: list["GoalMCPPresenter"] = Field(description="Child goals")

    @classmethod
    def from_goal(cls, goal: Goal, include_subgoals: bool = True) -> "GoalMCPPresenter":
        replies_by_parent: dict[UUID, list[GoalComment]] = {}
        top_level: list[GoalComment] = []

        for c in goal.comments:
            if c.is_top_level:
                top_level.append(c)
            elif c.parent_id:
                replies_by_parent.setdefault(c.parent_id, []).append(c)

        if include_subgoals:
            subgoals_list = list(goal.subgoals)
            subgoal_count = len(subgoals_list)
            subgoals = cls.from_goals(subgoals_list, include_subgoals=False)
        else:
            subgoal_count = 0
            subgoals = []

        return cls(
            id=str(goal.id),
            global_id=str(goal.global_id),
            title=goal.title,
            description=goal.description,
            status=goal.status.value,
            progress=goal.progress,
            target_date=goal.target_date,
            start_date=goal.start_date,
            created_at=goal.created_at,
            owner_id=str(goal.owner_id) if goal.owner_id else None,
            owner_name=goal.owner.name if goal.owner else None,
            group=GroupMCPPresenter.from_group(goal.group) if goal.group else None,
            is_subgoal=goal.is_subgoal,
            parent_id=str(goal.parent_id) if goal.parent_id else None,
            subgoal_count=subgoal_count,
            comment_count=len(top_level),
            comments=GoalCommentMCPPresenter.from_comments(top_level, replies_by_parent),
            subgoals=subgoals,
        )

    @classmethod
    def from_goals(cls, goals: list[Goal], include_subgoals: bool = True) -> list["GoalMCPPresenter"]:
        return [cls.from_goal(g, include_subgoals) for g in goals]
