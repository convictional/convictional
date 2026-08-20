import re
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response

from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.workspace import LinkPreview
from app.models.workspaces.posts import Post, PostComment
from app.presenters.internal_link_previews import resolve_preview_files
from app.presenters.link_previews import prepare_link_preview_for_comment
from app.routers.api.schemas import (
    PostCommentCreateRequest,
    PostCommentEditRequest,
    PostCommentListResponse,
    PostCommentResponse,
)
from app.routers.api.serializers import (
    fetch_reaction_users,
    post_comment_response,
    serialize_reactions,
)
from app.routers.dependencies import (
    Channel,
    UnclaimedAttachments,
    create_post_indexer,
    get_current_user,
    get_post,
    handle_stream,
)
from config.enums import (
    ChannelEventAction,
    ChannelEventResource,
    EventAction,
    ReactionType,
)
from infra.db import transaction

# Reactions don't change indexable content; skip the indexer for that path.
_POST_INDEXER_SKIP_PATHS = [re.compile(r".*/reactions")]

router = APIRouter(
    dependencies=[Depends(create_post_indexer(skip_paths=_POST_INDEXER_SKIP_PATHS), scope="function")],
    tags=["posts"],
)


#
# Helpers
#


def _ensure_published(post: Post) -> None:
    # Comment endpoints follow `api_posts_show`'s draft semantics: a draft post
    # is not yet a public resource, so its comments aren't either.
    if post.is_draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


async def _get_post_comment(comment_id: UUID, post: Post = Depends(get_post)) -> PostComment:
    _ensure_published(post)
    comment = await PostComment.get_or_none(id=comment_id, post_id=post.id).prefetch_related(
        "user__avatar_file", "link_preview"
    )
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return comment


async def _serialize_with_replies(comment: PostComment, current_user: User) -> PostCommentResponse:
    # Reuse a comment the caller already has in memory. For top-level comments,
    # load the replies sub-tree; reply rows themselves don't have nested replies
    # so we skip the prefetch there.
    if comment.parent_id is None:
        await comment.fetch_related("replies__user__avatar_file", "replies__link_preview")
        replies: list[PostComment] = list(comment.replies)
    else:
        replies = []
    users_by_id = await fetch_reaction_users([comment, *replies])
    # A pasted attachment link persists only its filename; resolve content type/size for the card,
    # gated by the reader's access, then build the response with it.
    files_by_url = await resolve_preview_files(
        [c.link_preview for c in [comment, *replies] if c.link_preview_id], current_user
    )
    return post_comment_response(comment, users_by_id, replies=replies, files_by_url=files_by_url)


#
# Endpoints
#


@router.get("/posts/{post_id}/comments", response_model=PostCommentListResponse)
async def api_post_comments_index(
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
):
    _ensure_published(post)
    comments = (
        await PostComment.filter(post_id=post.id, parent_id__isnull=True)
        .order_by("created_at")
        .prefetch_related("user__avatar_file", "link_preview", "replies__user__avatar_file", "replies__link_preview")
    )
    all_comments: list[PostComment] = []
    for c in comments:
        all_comments.append(c)
        all_comments.extend(list(c.replies))
    users_by_id = await fetch_reaction_users(all_comments)
    files_by_url = await resolve_preview_files(
        [c.link_preview for c in all_comments if c.link_preview_id], current_user
    )
    responses = [
        post_comment_response(
            c, users_by_id, replies=sorted(list(c.replies), key=lambda r: r.created_at), files_by_url=files_by_url
        )
        for c in comments
    ]
    return PostCommentListResponse(comments=responses)


@router.post(
    "/posts/{post_id}/comments",
    response_model=PostCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_post_comments_create(
    body: PostCommentCreateRequest,
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
):
    _ensure_published(post)
    content = body.content.strip()
    parent_id = body.parent_id

    if parent_id is not None:
        # parent must be top-level: post threading is one level deep, so a parent
        # that is itself a reply (parent_id__isnull=False) would create a depth-2
        # comment the show endpoint can't render.
        parent_exists = await PostComment.exists(id=parent_id, post_id=post.id, parent_id__isnull=True)
        if not parent_exists:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent comment not found")

    notifier = Notifier(post, current_user)
    comment = PostComment(content=content, post_id=post.id, parent_id=parent_id, user_id=current_user.id)

    link_preview_data = await prepare_link_preview_for_comment(content, current_user) if body.unfurl_links else None
    unclaimed_attachments = await UnclaimedAttachments.resolve(body.attachment_claim_id, current_user.id)

    async with notifier.record_and_notify(recordable=comment, action=EventAction.POST_COMMENTED) as recording:
        recording.event.details.update({"comment_id": comment.id})
        await comment.save(recording.using_db)
        await recording.resolve_mentions(content)
        await LinkPreview.associate(PostComment, comment.id, link_preview_data, using_db=recording.using_db)

        await unclaimed_attachments.claim(post.workspace, comment, recording.using_db)

    await comment.broadcast_created()

    # `comment.user` was set on construction (current_user); fetch the avatar
    # and link_preview the serializer needs without re-querying the comment row.
    await comment.fetch_related("user__avatar_file", "link_preview")
    return await _serialize_with_replies(comment, current_user)


@router.patch("/posts/{post_id}/comments/{comment_id}", response_model=PostCommentResponse)
async def api_post_comments_edit(
    body: PostCommentEditRequest,
    post: Post = Depends(get_post),
    comment: PostComment = Depends(_get_post_comment),
    current_user: User = Depends(get_current_user),
):
    if not comment.editable_by(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    content = body.content.strip()
    notifier = Notifier(post, current_user)
    link_preview_data = await prepare_link_preview_for_comment(content, current_user) if body.unfurl_links else None
    unclaimed_attachments = await UnclaimedAttachments.resolve(body.attachment_claim_id, current_user.id)

    async with transaction() as connection:
        comment.content = content
        await comment.save(using_db=connection)

        mentions = await post.workspace.resolve_mentions(
            content, comment.user_id, recordable=comment, using_db=connection
        )
        await notifier.notify_mentions(mentions, using_db=connection)
        await LinkPreview.associate(PostComment, comment.id, link_preview_data, using_db=connection)

        await unclaimed_attachments.claim(post.workspace, comment, using_db=connection)

    await comment.broadcast_edited()

    # `comment` already has user + link_preview prefetched from `_get_post_comment`;
    # the link_preview association above only changed link_preview_id, so refresh
    # that relation before serializing.
    await comment.fetch_related("link_preview")
    return await _serialize_with_replies(comment, current_user)


@router.delete(
    "/posts/{post_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_post_comments_delete(
    post: Post = Depends(get_post),
    comment: PostComment = Depends(_get_post_comment),
    current_user: User = Depends(get_current_user),
):
    if not comment.deletable_by(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    await comment.soft_delete()
    await comment.broadcast_deleted()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/posts/{post_id}/comments/{comment_id}/reactions",
    response_model=PostCommentResponse,
)
async def api_post_comments_toggle_reaction(
    comment_id: UUID,
    reaction_type: ReactionType = Query(...),
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
):
    # Drop the `_get_post_comment` dependency for this endpoint — the select_for_update
    # below already loads the row, and the auth-check 404 is the same shape (id+post_id).
    _ensure_published(post)
    async with transaction() as conn:
        locked = await (
            PostComment.select_for_update()
            .using_db(conn)
            .get_or_none(id=comment_id, post_id=post.id)
            .prefetch_related("user__avatar_file", "link_preview")
        )
        if locked is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        locked.toggle_reaction(current_user.id, reaction_type)
        await locked.save(update_fields=["reactions"], using_db=conn)
    await locked.broadcast_reaction_update()
    return await _serialize_with_replies(locked, current_user)


#
# Channel handler
#


async def _send_comment_event(channel: Channel, comment_id: UUID, action: ChannelEventAction) -> None:
    comment = await PostComment.get_or_none(id=comment_id).prefetch_related(
        "user__avatar_file", "link_preview", "replies__user__avatar_file", "replies__link_preview"
    )
    if not comment or str(comment.post_id) != channel.topic.params.get("post_id"):
        return
    replies: list[PostComment] = list(comment.replies) if comment.parent_id is None else []
    users_by_id = await fetch_reaction_users([comment, *replies])
    await channel.send_event(
        resource=ChannelEventResource.POST_COMMENT,
        action=action,
        **post_comment_response(comment, users_by_id, replies=replies).model_dump(mode="json"),
    )


async def _send_reaction_event(channel: Channel, comment_id: UUID) -> None:
    comment = await PostComment.get_or_none(id=comment_id)
    if not comment or str(comment.post_id) != channel.topic.params.get("post_id"):
        return
    users_by_id = await fetch_reaction_users([comment])
    serialized = serialize_reactions(comment.reactions, users_by_id)
    await channel.send_event(
        resource=ChannelEventResource.POST_COMMENT,
        action=ChannelEventAction.REACTION_TOGGLED,
        comment_id=str(comment.id),
        reactions={k: [u.model_dump() for u in v] for k, v in serialized.items()},
    )


@handle_stream("post_comments")
async def post_comments_json_broadcast(channel: Channel, **data: dict):
    # author_id is per-user, not per-tab, so we don't skip the broadcast's author —
    # a user with two tabs open needs tab 2 to receive what tab 1 triggered.
    # Consumers must be idempotent: dedupe CREATED by comment id, treat
    # UPDATED/DELETED/REACTION_TOGGLED as last-writer-wins.

    if updated_comment_id := data.get("updated_comment_id"):
        await _send_reaction_event(channel, UUID(str(updated_comment_id)))
        return

    if new_comment_id := data.get("new_comment_id"):
        await _send_comment_event(channel, UUID(str(new_comment_id)), ChannelEventAction.CREATED)
    elif edited_comment_id := data.get("edited_comment_id"):
        await _send_comment_event(channel, UUID(str(edited_comment_id)), ChannelEventAction.UPDATED)
    elif deleted_comment_id := data.get("deleted_comment_id"):
        await channel.send_event(
            resource=ChannelEventResource.POST_COMMENT,
            action=ChannelEventAction.DELETED,
            id=str(deleted_comment_id),
        )
