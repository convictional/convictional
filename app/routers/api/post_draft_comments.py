from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.helpers.users import user_avatar_url
from app.models.accounts import User
from app.models.workspaces.posts import Post, PostDraftComment
from app.routers.api.schemas import (
    CommentEditRequest,
    CommentMarkCreateRequest,
    CommentMarkListResponse,
    CommentMarkResponse,
    CommentThreadResponse,
    UserResponse,
)
from app.routers.api.serializers import fetch_reaction_users, serialize_reactions
from app.routers.api.streams import CommentMarkStream, is_from_current_user
from app.routers.dependencies import Channel as BroadcastChannel
from app.routers.dependencies import get_current_user, get_draft_post, handle_stream
from config.enums import ChannelEventAction, ChannelEventResource, ReactionType
from infra.db import transaction

router = APIRouter(tags=["posts"])


def _comment_response(comment: PostDraftComment, users_by_id: dict[UUID, User]) -> CommentMarkResponse:
    return CommentMarkResponse(
        id=str(comment.id),
        global_id=str(comment.global_id),
        content=comment.content,
        quoted_text=comment.quoted_text,
        comment_mark_id=comment.comment_mark_id,
        resolved_at=comment.resolved_at,
        created_at=comment.created_at,
        user=UserResponse(
            id=str(comment.user.id), display_name=comment.user.display_name, picture=user_avatar_url(comment.user)
        ),
        reactions=serialize_reactions(comment.reactions, users_by_id),
    )


async def get_post_draft_comment(comment_id: UUID, post: Post = Depends(get_draft_post)):
    comment = await PostDraftComment.get_or_none(id=comment_id, post_id=post.id)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return comment


async def get_owned_post_draft_comment(
    comment: PostDraftComment = Depends(get_post_draft_comment),
    current_user: User = Depends(get_current_user),
):
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return comment


@router.get(
    "/posts/{post_id}/draft/comments",
    response_model=CommentMarkListResponse,
)
async def api_post_draft_comments_index(
    post: Post = Depends(get_draft_post),
):
    comments = (
        await PostDraftComment.filter(
            post_id=post.id,
            resolved_at__isnull=True,
        )
        .order_by("created_at")
        .prefetch_related("user__avatar_file")
    )

    users_by_id = await fetch_reaction_users(comments)
    return CommentMarkListResponse(
        comments=[_comment_response(c, users_by_id) for c in comments],
    )


# Draft comments don't trigger notifications or resolve @-mentions — drafts are
# private collaboration, and the author hasn't published yet.
@router.post(
    "/posts/{post_id}/draft/comments",
    response_model=CommentMarkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_post_draft_comments_create(
    body: CommentMarkCreateRequest,
    post: Post = Depends(get_draft_post),
    current_user: User = Depends(get_current_user),
):
    comment = await PostDraftComment.create(
        content=body.content.strip(),
        quoted_text=body.quoted_text,
        comment_mark_id=body.comment_mark_id,
        post_id=post.id,
        user_id=current_user.id,
    )

    comment.user = current_user
    await comment.broadcast_created()
    return _comment_response(comment, {})


# Content edits require the comment author; resolve/unresolve is open to any
# draft collaborator since it's a collaborative workflow action.
@router.patch("/posts/{post_id}/draft/comments/{comment_id}")
async def api_post_draft_comments_edit(
    body: CommentEditRequest,
    comment: PostDraftComment = Depends(get_post_draft_comment),
    post: Post = Depends(get_draft_post),
    current_user: User = Depends(get_current_user),
) -> CommentMarkResponse | CommentThreadResponse:
    if body.content is not None and comment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    edited: CommentMarkResponse | None = None
    if body.content is not None:
        edited = await _edit_content(comment, body.content)

    if body.resolved is not None:
        return await _set_thread_resolved(post, comment, body.resolved, current_user)

    assert edited is not None  # validator guarantees at least one of content/resolved
    return edited


async def _edit_content(comment: PostDraftComment, content: str) -> CommentMarkResponse:
    comment.content = content.strip()
    await comment.save(update_fields=["content"])

    await comment.fetch_related("user__avatar_file")
    users_by_id = await fetch_reaction_users([comment])
    await comment.broadcast_edited()
    return _comment_response(comment, users_by_id)


async def _set_thread_resolved(
    post: Post, comment: PostDraftComment, resolved: bool, current_user: User
) -> CommentThreadResponse:
    target = datetime.now(UTC) if resolved else None
    await PostDraftComment.filter(
        post_id=post.id,
        comment_mark_id=comment.comment_mark_id,
    ).update(resolved_at=target)

    comments = (
        await PostDraftComment.filter(
            post_id=post.id,
            comment_mark_id=comment.comment_mark_id,
        )
        .order_by("created_at")
        .prefetch_related("user__avatar_file")
    )

    users_by_id = await fetch_reaction_users(comments)
    await comment.broadcast_resolved(current_user.id)
    return CommentThreadResponse(
        comment_mark_id=comment.comment_mark_id,
        resolved_at=target,
        comments=[_comment_response(c, users_by_id) for c in comments],
    )


@router.delete(
    "/posts/{post_id}/draft/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_post_draft_comments_delete(
    comment: PostDraftComment = Depends(get_owned_post_draft_comment),
):
    await comment.delete()
    await comment.broadcast_deleted()


# Any draft collaborator can react — same as resolve
@router.post(
    "/posts/{post_id}/draft/comments/{comment_id}/reactions",
    response_model=CommentMarkResponse,
)
async def api_post_draft_comments_toggle_reaction(
    reaction_type: ReactionType = Query(...),
    comment: PostDraftComment = Depends(get_post_draft_comment),
    current_user: User = Depends(get_current_user),
):
    async with transaction() as conn:
        locked = await PostDraftComment.select_for_update().using_db(conn).get(id=comment.id)
        locked.toggle_reaction(current_user.id, reaction_type)
        await locked.save(update_fields=["reactions"], using_db=conn)
    await locked.fetch_related("user__avatar_file")
    users_by_id = await fetch_reaction_users([locked])
    await locked.broadcast_reaction_update()
    return _comment_response(locked, users_by_id)


_stream = CommentMarkStream(
    model_class=PostDraftComment,
    parent_id_field="post_id",
    resource=ChannelEventResource.POST_DRAFT_COMMENT,
    comment_response_fn=_comment_response,
)


@handle_stream("post_draft_comments")
async def handle_post_draft_comments_stream(channel: BroadcastChannel, **data: dict):
    is_own = is_from_current_user(channel, data)

    # Reaction updates go to everyone (including the author, for optimistic sync).
    # All other events skip the author since they already have local state.
    if updated_comment_id := data.get("updated_comment_id"):
        await _stream.send_reaction(channel, UUID(str(updated_comment_id)))
    elif is_own:
        return
    elif new_comment_id := data.get("new_comment_id"):
        await _stream.send_comment(channel, UUID(str(new_comment_id)), ChannelEventAction.CREATED)
    elif edited_comment_id := data.get("edited_comment_id"):
        await _stream.send_comment(channel, UUID(str(edited_comment_id)), ChannelEventAction.UPDATED)
    elif deleted_comment_id := data.get("deleted_comment_id"):
        await channel.send_event(
            resource=_stream.resource, action=ChannelEventAction.DELETED, id=str(deleted_comment_id)
        )
    elif resolved_thread_mark_id := data.get("resolved_thread_mark_id"):
        await _stream.send_resolved(channel, str(resolved_thread_mark_id))
