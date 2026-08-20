from datetime import datetime
from typing import Self
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.helpers.users import user_avatar_url
from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.workspace import Visit
from app.models.workspaces.goals import Goal, GoalComment
from app.routers.api.schemas import PaginatedResponse, ReactionUserResponse, UserResponse
from app.routers.api.serializers import fetch_reaction_users, serialize_reactions
from app.routers.api.streams import is_from_current_user
from app.routers.dependencies import Channel, get_current_user, handle_stream
from config.enums import ChannelEventAction, ChannelEventResource, EventAction, ReactionType
from infra.db import transaction

router = APIRouter(tags=["goal comments"])


#
# Response models
#


class GoalCommentResponse(BaseModel):
    id: str
    global_id: str = Field(description="GlobalID used to reference this comment across resources.")
    content: str
    parent_id: str | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    user: UserResponse
    reactions: dict[str, list[ReactionUserResponse]]
    replies: list["GoalCommentResponse"]


class GoalCommentListResponse(PaginatedResponse):
    comments: list[GoalCommentResponse]


#
# Request models
#


class CommentCreateRequest(BaseModel):
    content: str = Field(min_length=1)
    parent_id: UUID | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be blank")
        return v


# Goal comments have their own request model because they toggle `closed`, not
# the `resolved` field used by document/post comments.
class GoalCommentEditRequest(BaseModel):
    content: str | None = None
    closed: bool | None = None

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not v.strip():
            raise ValueError("content must not be blank")
        return v

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if self.content is None and self.closed is None:
            raise ValueError("must set content and/or closed")
        return self


#
# Dependencies
#


async def get_goal_for_comments(goal_id: UUID, current_user: User = Depends(get_current_user)) -> Goal:
    return await Goal.get(id=goal_id, organization_id=current_user.organization_id).prefetch_related(
        "workspace__collaborators__user"
    )


async def get_goal_comment(comment_id: UUID, goal: Goal = Depends(get_goal_for_comments)):
    return await GoalComment.get(id=comment_id, goal_id=goal.id).prefetch_related("user", "goal", "link_preview")


async def get_goal_notifier(
    goal: Goal = Depends(get_goal_for_comments), current_user: User = Depends(get_current_user)
):
    return Notifier(goal, current_user)


#
# Mutations
#


async def save_new_comment(
    goal: Goal,
    current_user: User,
    content: str,
    parent_id: UUID | None,
    notifier: Notifier,
) -> GoalComment:
    comment = GoalComment(content=content, goal_id=goal.id, parent_id=parent_id, user_id=current_user.id)
    async with notifier.record_and_notify(recordable=comment, action=EventAction.GOAL_COMMENTED) as recording:
        recording.event.details.update({"comment_id": comment.id})
        await comment.save(recording.using_db)
        await recording.resolve_mentions(comment.content, recordable=comment)
        await Visit.record(current_user.id, goal.workspace_id, recording.event.id, using_db=recording.using_db)

    await comment.broadcast_created()
    await goal.broadcast_update()
    return comment


async def save_comment_edit(
    goal: Goal,
    comment: GoalComment,
    content: str,
    notifier: Notifier,
) -> None:
    async with transaction() as connection:
        comment.content = content
        await comment.save(using_db=connection)

        mentions = await goal.workspace.resolve_mentions(
            content, comment.user_id, recordable=comment, using_db=connection
        )
        await notifier.notify_mentions(mentions, using_db=connection)

    await comment.broadcast_edited()


async def delete_comment(comment: GoalComment) -> None:
    await comment.soft_delete()
    await comment.broadcast_deleted()
    await comment.goal.broadcast_update()


async def set_comment_closed(comment: GoalComment, closed: bool) -> bool:
    """Sets the closed state explicitly. Returns False if the comment is a reply."""
    if comment.is_reply:
        return False

    if closed and not comment.is_closed:
        await comment.close()
    elif not closed and comment.is_closed:
        await comment.open()
    else:
        return True

    await comment.goal.broadcast_comments_update(panel_updated=True)
    return True


#
# Helpers
#


def _comment_response(comment: GoalComment, users_by_id: dict[UUID, User]) -> GoalCommentResponse:
    user = comment.user
    replies = (
        [_comment_response(r, users_by_id) for r in comment.replies]
        if comment.is_top_level and comment.replies
        else []
    )
    return GoalCommentResponse(
        id=str(comment.id),
        global_id=str(comment.global_id),
        content=comment.content,
        parent_id=str(comment.parent_id) if comment.parent_id else None,
        closed_at=comment.closed_at,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        user=UserResponse(id=str(user.id), display_name=user.display_name, picture=user_avatar_url(user)),
        reactions=serialize_reactions(comment.reactions, users_by_id),
        replies=replies,
    )


async def _fetch_comment_threads(goal_id: UUID) -> list[GoalComment]:
    return (
        await GoalComment.filter(
            goal_id=goal_id,
            parent_id__isnull=True,
            closed_at__isnull=True,
        )
        .order_by("created_at")
        .prefetch_related("user__avatar_file", "replies__user__avatar_file")
    )


async def _build_comment_list_response(goal_id: UUID) -> GoalCommentListResponse:
    comments = await _fetch_comment_threads(goal_id)
    users_by_id = await fetch_reaction_users([c for thread in comments for c in [thread, *thread.replies]])
    return GoalCommentListResponse(
        comments=[_comment_response(c, users_by_id) for c in comments],
    )


async def _build_single_comment_response(comment_id: UUID) -> GoalCommentResponse:
    comment = await GoalComment.get(id=comment_id).prefetch_related("user__avatar_file", "replies__user__avatar_file")
    all_comments = [comment, *comment.replies]
    users_by_id = await fetch_reaction_users(all_comments)
    return _comment_response(comment, users_by_id)


#
# Endpoints
#


@router.get(
    "/goals/{goal_id}/comments",
    response_model=GoalCommentListResponse,
)
async def api_goal_comments_index(
    goal: Goal = Depends(get_goal_for_comments),
):
    return await _build_comment_list_response(goal.id)


@router.post(
    "/goals/{goal_id}/comments",
    response_model=GoalCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_goal_comments_create(
    body: CommentCreateRequest,
    goal: Goal = Depends(get_goal_for_comments),
    current_user: User = Depends(get_current_user),
    notifier: Notifier = Depends(get_goal_notifier),
):
    comment = await save_new_comment(goal, current_user, body.content.strip(), body.parent_id, notifier)
    return await _build_single_comment_response(comment.id)


# Content edits require the comment author; close/reopen is open to any
# goal collaborator since it's a collaborative workflow action.
@router.patch("/goals/{goal_id}/comments/{comment_id}")
async def api_goal_comments_edit(
    body: GoalCommentEditRequest,
    goal: Goal = Depends(get_goal_for_comments),
    comment: GoalComment = Depends(get_goal_comment),
    current_user: User = Depends(get_current_user),
    notifier: Notifier = Depends(get_goal_notifier),
) -> GoalCommentResponse | GoalCommentListResponse:
    if body.content is not None and comment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    if body.content is not None:
        await save_comment_edit(goal, comment, body.content.strip(), notifier)

    if body.closed is not None:
        if not await set_comment_closed(comment, body.closed):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Reply comments cannot be closed",
            )
        # Broadcast the goal update once here rather than inside each mutation
        # helper, so a combined content+closed PATCH fires a single timeline event.
        await goal.broadcast_update()
        return await _build_comment_list_response(goal.id)

    await goal.broadcast_update()
    return await _build_single_comment_response(comment.id)


@router.delete(
    "/goals/{goal_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_goal_comments_delete(
    comment: GoalComment = Depends(get_goal_comment),
    current_user: User = Depends(get_current_user),
):
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    await delete_comment(comment)


@router.post(
    "/goals/{goal_id}/comments/{comment_id}/reactions",
    response_model=GoalCommentResponse,
)
async def api_goal_comments_toggle_reaction(
    reaction_type: ReactionType = Query(...),
    comment: GoalComment = Depends(get_goal_comment),
    current_user: User = Depends(get_current_user),
):
    async with transaction() as conn:
        locked = await GoalComment.select_for_update().using_db(conn).get(id=comment.id)
        locked.toggle_reaction(current_user.id, reaction_type)
        await locked.save(update_fields=["reactions"], using_db=conn)
    await locked.broadcast_reaction_update()
    return await _build_single_comment_response(locked.id)


#
# Channel handler
#


async def _send_comment_event(channel: Channel, comment_id: UUID, action: ChannelEventAction) -> None:
    comment = await GoalComment.get_or_none(id=comment_id).prefetch_related(
        "user__avatar_file", "replies__user__avatar_file"
    )
    if not comment or str(comment.goal_id) != channel.topic.params.get("goal_id"):
        return
    all_comments = [comment, *comment.replies]
    users_by_id = await fetch_reaction_users(all_comments)
    await channel.send_event(
        resource=ChannelEventResource.GOAL_COMMENT,
        action=action,
        **_comment_response(comment, users_by_id).model_dump(mode="json"),
    )


async def _send_reaction_event(channel: Channel, comment_id: UUID) -> None:
    comment = await GoalComment.get_or_none(id=comment_id)
    if not comment or str(comment.goal_id) != channel.topic.params.get("goal_id"):
        return
    users_by_id = await fetch_reaction_users([comment])
    serialized = serialize_reactions(comment.reactions, users_by_id)
    await channel.send_event(
        resource=ChannelEventResource.GOAL_COMMENT,
        action=ChannelEventAction.REACTION_TOGGLED,
        comment_id=str(comment.id),
        reactions={k: [u.model_dump() for u in v] for k, v in serialized.items()},
    )


async def _send_panel_event(channel: Channel) -> None:
    goal_id = channel.get_param("goal_id")
    comments = await _fetch_comment_threads(UUID(str(goal_id)))
    all_flat = [c for thread in comments for c in [thread, *thread.replies]]
    users_by_id = await fetch_reaction_users(all_flat)
    await channel.send_event(
        resource=ChannelEventResource.GOAL_COMMENT,
        action=ChannelEventAction.PANEL_UPDATED,
        comments=[_comment_response(c, users_by_id).model_dump(mode="json") for c in comments],
    )


@handle_stream("goal_comments")
async def handle_goal_comments_stream(channel: Channel, **data: dict):
    is_own = is_from_current_user(channel, data)

    # Reaction updates go to everyone (including author for optimistic sync)
    if updated_comment_id := data.get("updated_comment_id"):
        await _send_reaction_event(channel, UUID(str(updated_comment_id)))
    elif is_own:
        return
    elif new_comment_id := data.get("new_comment_id"):
        await _send_comment_event(channel, UUID(str(new_comment_id)), ChannelEventAction.CREATED)
    elif edited_comment_id := data.get("edited_comment_id"):
        await _send_comment_event(channel, UUID(str(edited_comment_id)), ChannelEventAction.UPDATED)
    elif deleted_comment_id := data.get("deleted_comment_id"):
        await channel.send_event(
            resource=ChannelEventResource.GOAL_COMMENT,
            action=ChannelEventAction.DELETED,
            id=str(deleted_comment_id),
        )
    elif data.get("panel_updated"):
        await _send_panel_event(channel)
