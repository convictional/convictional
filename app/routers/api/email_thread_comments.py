import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from tortoise.query_utils import Prefetch

from app.jobs.notifications import Notifier
from app.models.accounts import User
from app.models.collaboration.workspace import Attachment, LinkPreview, Workspace
from app.models.workspaces.email.thread import EmailThread, EmailThreadComment
from app.presenters.internal_link_previews import previewed_attachment_id, resolve_preview_files
from app.presenters.link_previews import prepare_link_preview_for_comment
from app.routers.api.schemas import (
    EmailMessageAttachmentResponse,
    EmailThreadCommentCreateRequest,
    EmailThreadCommentEditRequest,
    EmailThreadCommentListResponse,
    EmailThreadCommentResponse,
)
from app.routers.api.serializers import (
    fetch_reaction_users,
    link_preview_response,
    reply_preview,
    serialize_reactions,
    user_response,
)
from app.routers.api.streams import is_from_current_user
from app.routers.dependencies import (
    Channel,
    UnclaimedAttachments,
    create_email_thread_comment_indexer,
    email_thread_comment_context,
    get_current_user,
    handle_stream,
)
from config.enums import (
    ChannelEventAction,
    ChannelEventResource,
    EventAction,
    ReactionType,
)
from infra.db import allow_soft_deleted, transaction
from lib.mime_types import is_browser_supported_image

# Reactions don't change indexable content; skip the indexer for that path.
_EMAIL_THREAD_COMMENT_INDEXER_SKIP_PATHS = [re.compile(r".*/reactions")]

router = APIRouter(
    dependencies=[
        Depends(
            create_email_thread_comment_indexer(skip_paths=_EMAIL_THREAD_COMMENT_INDEXER_SKIP_PATHS),
            scope="function",
        )
    ],
    tags=["email thread comments"],
)

_COMMENT_PREFETCH = ("user__avatar_file", "link_preview")


async def reply_to_prefetch() -> Prefetch:
    # allow_soft_deleted so a soft-deleted reply target still loads and its quote can
    # render a tombstone rather than vanish (the default manager would exclude it).
    async with allow_soft_deleted():
        return Prefetch("reply_to", queryset=EmailThreadComment.filter().select_related("user"))


async def _load_reply_to(comment: EmailThreadComment) -> None:
    # Instance .fetch_related() can't take a Prefetch, so single-comment serialize paths
    # load the reply target directly under allow_soft_deleted and cache it on the instance.
    if not comment.reply_to_id:
        return
    async with allow_soft_deleted():
        comment.reply_to = await EmailThreadComment.filter(id=comment.reply_to_id).select_related("user").first()


#
# Serialization
#


def _attachment_response(attachment: Attachment, previewed_url: str | None = None) -> EmailMessageAttachmentResponse:
    is_inline = attachment.is_image
    # A non-image attachment referenced inline unfurls into the file-card preview
    # (LinkPreviewCard) and must not also appear in the attachments list, or the same
    # file renders twice — the card plus a list row. The card is its single representation.
    is_previewed = previewed_url is not None and previewed_attachment_id(previewed_url) == attachment.id
    show_in_list = not is_previewed and not (is_inline and is_browser_supported_image(attachment.file.content_type))
    return EmailMessageAttachmentResponse(
        id=str(attachment.id),
        filename=attachment.file.filename,
        content_type=attachment.file.content_type,
        is_inline=is_inline,
        download_url=attachment.download_urls[-1],
        show_in_list=show_in_list,
    )


def _build_response(
    comment: EmailThreadComment,
    users_by_id: dict[UUID, User],
    attachments: list[Attachment],
    files_by_url: dict[str, dict[str, Any]] | None = None,
) -> EmailThreadCommentResponse:
    preview = comment.link_preview if comment.link_preview_id else None
    link_preview = link_preview_response(preview, files_by_url)
    previewed_url = preview.url if preview else None
    reply_to = reply_preview(comment.reply_to) if comment.reply_to_id and comment.reply_to else None
    return EmailThreadCommentResponse(
        id=str(comment.id),
        global_id=str(comment.global_id),
        content=comment.content,
        user=user_response(comment.user) if comment.user else None,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        reactions=serialize_reactions(comment.reactions, users_by_id),
        link_preview=link_preview,
        attachments=[_attachment_response(a, previewed_url) for a in attachments],
        reply_to=reply_to,
    )


async def _serialize_one(comment: EmailThreadComment, current_user: User) -> EmailThreadCommentResponse:
    users_by_id = await fetch_reaction_users([comment])
    attachments = await Attachment.filter(comment_gid=comment.global_id).prefetch_related("file")
    # A pasted attachment link persists only its filename; resolve content type/size for the card,
    # gated by the reader's access, then build the response with it.
    files_by_url = await resolve_preview_files(
        [comment.link_preview if comment.link_preview_id else None], current_user
    )
    return _build_response(comment, users_by_id, attachments, files_by_url)


async def serialize_email_thread_comments(
    comments: list[EmailThreadComment], current_user: User
) -> list[EmailThreadCommentResponse]:
    users_by_id = await fetch_reaction_users(comments)
    gids = [str(c.global_id) for c in comments]
    attachments_by_comment: dict[UUID, list[Attachment]] = {c.id: [] for c in comments}
    if gids:
        for attachment in await Attachment.filter(comment_gid__in=gids).prefetch_related("file"):
            attachments_by_comment.setdefault(attachment.comment_gid.record_id, []).append(attachment)
    files_by_url = await resolve_preview_files([c.link_preview for c in comments if c.link_preview_id], current_user)
    return [_build_response(c, users_by_id, attachments_by_comment.get(c.id, []), files_by_url) for c in comments]


#
# Dependencies
#


async def get_email_thread_workspace(
    email_thread_id: UUID,
    current_user: User = Depends(get_current_user),
) -> Workspace:
    thread = await EmailThread.get_or_none(id=email_thread_id).prefetch_related("workspace__collaborators__user")
    if not thread or not thread.collaboration.can_be_accessed_by(current_user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    workspace = thread.workspace
    workspace.resource = thread
    return workspace


async def _get_email_thread_comment(
    comment_id: UUID,
    workspace: Workspace = Depends(get_email_thread_workspace),
) -> EmailThreadComment:
    comment = await EmailThreadComment.get_or_none(
        id=comment_id, email_thread_id=workspace.resource.id
    ).prefetch_related(*_COMMENT_PREFETCH)
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    # Hand the resolved comment to the content indexer via the dependency, like get_post.
    # The reaction path also lands here but is skipped by _EMAIL_THREAD_COMMENT_INDEXER_SKIP_PATHS.
    # Create can't use this — the comment doesn't exist yet — so it sets the context itself.
    email_thread_comment_context.set(comment)
    return comment


async def _get_owned_comment(
    comment: EmailThreadComment = Depends(_get_email_thread_comment),
    current_user: User = Depends(get_current_user),
) -> EmailThreadComment:
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)
    return comment


#
# Endpoints
#


@router.get("/email_threads/{email_thread_id}/comments", response_model=EmailThreadCommentListResponse)
async def api_email_thread_comments_index(
    workspace: Workspace = Depends(get_email_thread_workspace),
    current_user: User = Depends(get_current_user),
):
    comments = (
        await EmailThreadComment.filter(email_thread_id=workspace.resource.id)
        .order_by("created_at")
        .prefetch_related(*_COMMENT_PREFETCH, await reply_to_prefetch())
    )
    return EmailThreadCommentListResponse(comments=await serialize_email_thread_comments(comments, current_user))


@router.post(
    "/email_threads/{email_thread_id}/comments",
    response_model=EmailThreadCommentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_email_thread_comments_create(
    body: EmailThreadCommentCreateRequest,
    workspace: Workspace = Depends(get_email_thread_workspace),
    current_user: User = Depends(get_current_user),
):
    content = body.content.strip()

    if body.reply_to_id:
        reply_exists = await EmailThreadComment.filter(
            id=body.reply_to_id, email_thread_id=workspace.resource.id
        ).exists()
        if not reply_exists:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="reply_to_id not found in this thread",
            )

    # workspace.resource is the thread the dependency resolved, so its id is the email_thread_id.
    comment = EmailThreadComment(
        email_thread_id=workspace.resource.id,
        user_id=current_user.id,
        content=content,
        reply_to_id=body.reply_to_id,
    )

    link_preview_data = await prepare_link_preview_for_comment(content, current_user) if body.unfurl_links else None
    unclaimed_attachments = await UnclaimedAttachments.resolve(body.attachment_claim_id, current_user.id)

    notifier = Notifier(workspace.resource, current_user)
    async with notifier.record_and_notify(recordable=comment, action=EventAction.COMMENTED) as recording:
        await comment.save(recording.using_db)
        await recording.resolve_mentions(content, recordable=comment)
        await LinkPreview.associate(EmailThreadComment, comment.id, link_preview_data, using_db=recording.using_db)
        await unclaimed_attachments.claim(workspace, comment, using_db=recording.using_db)

    await comment.broadcast_created()

    # LinkPreview.associate updates the row's link_preview_id directly, so refresh the
    # in-memory FK before fetching the relation for serialization.
    await comment.refresh_from_db(fields=["link_preview_id"])
    comment.user = current_user
    await comment.fetch_related("user__avatar_file", "link_preview")
    await _load_reply_to(comment)
    # Create sets the indexer context here because the comment didn't exist when the
    # dependencies ran. Edit/delete set it in _get_email_thread_comment instead.
    email_thread_comment_context.set(comment)
    return await _serialize_one(comment, current_user)


@router.patch("/email_threads/{email_thread_id}/comments/{comment_id}", response_model=EmailThreadCommentResponse)
async def api_email_thread_comments_edit(
    body: EmailThreadCommentEditRequest,
    workspace: Workspace = Depends(get_email_thread_workspace),
    comment: EmailThreadComment = Depends(_get_owned_comment),
    current_user: User = Depends(get_current_user),
):
    content = body.content.strip()
    link_preview_data = await prepare_link_preview_for_comment(content, current_user) if body.unfurl_links else None
    unclaimed_attachments = await UnclaimedAttachments.resolve(body.attachment_claim_id, current_user.id)

    notifier = Notifier(workspace.resource, current_user)
    async with transaction() as connection:
        # Recording the edit as an event lets SyncMailboxJob refresh rows without re-alerting
        # caught-up collaborators; only a user pulled in by a newly-added @mention is surfaced
        # (InboxUpdate.for_event). Resolving mentions inside the recording adds them as
        # collaborators and pushes them (no email — email-thread comment @mentions don't email).
        async with notifier.record_and_notify(
            EventAction.EMAIL_THREAD_COMMENT_EDITED, recordable=comment, using_db=connection
        ) as recording:
            comment.content = content
            await comment.save(using_db=connection)
            await recording.resolve_mentions(content, recordable=comment)
            await LinkPreview.associate(EmailThreadComment, comment.id, link_preview_data, using_db=connection)
            await unclaimed_attachments.claim(workspace, comment, using_db=connection)

    await comment.broadcast_edited()

    await comment.refresh_from_db(fields=["link_preview_id"])
    await comment.fetch_related("user__avatar_file", "link_preview")
    await _load_reply_to(comment)
    return await _serialize_one(comment, current_user)


@router.delete(
    "/email_threads/{email_thread_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def api_email_thread_comments_delete(
    workspace: Workspace = Depends(get_email_thread_workspace),
    comment: EmailThreadComment = Depends(_get_owned_comment),
    current_user: User = Depends(get_current_user),
):
    await comment.cleanup_unreferenced_attachments()
    # Recording the delete as an event lets SyncMailboxJob refresh the row preview for everyone
    # (it falls back to the prior content) without re-alerting caught-up collaborators.
    notifier = Notifier(workspace.resource, current_user)
    async with transaction() as connection:
        async with notifier.record_and_notify(
            EventAction.EMAIL_THREAD_COMMENT_DELETED, recordable=comment, using_db=connection
        ):
            await comment.soft_delete(using_db=connection)
    await comment.broadcast_deleted()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/email_threads/{email_thread_id}/comments/{comment_id}/reactions",
    response_model=EmailThreadCommentResponse,
)
async def api_email_thread_comments_toggle_reaction(
    reaction_type: ReactionType = Query(...),
    comment: EmailThreadComment = Depends(_get_email_thread_comment),
    current_user: User = Depends(get_current_user),
):
    async with transaction() as conn:
        locked = await EmailThreadComment.select_for_update().using_db(conn).get(id=comment.id)
        locked.toggle_reaction(current_user.id, reaction_type)
        await locked.save(update_fields=["reactions"], using_db=conn)
    await locked.fetch_related("user__avatar_file", "link_preview")
    await _load_reply_to(locked)
    await locked.broadcast_reaction_update()
    return await _serialize_one(locked, current_user)


#
# Channel handler
#


def _belongs_to_topic(comment: EmailThreadComment, channel: Channel) -> bool:
    return str(comment.email_thread_id) == channel.topic.params.get("email_thread_id")


@handle_stream("email_thread_comments")
async def email_thread_comments_json_broadcast(channel: Channel, **data) -> None:
    if not channel.current_user:
        return

    for key, action in (
        ("new_comment_id", ChannelEventAction.CREATED),
        ("edited_comment_id", ChannelEventAction.UPDATED),
    ):
        if comment_id := data.get(key):
            if is_from_current_user(channel, data):
                return
            comment = await EmailThreadComment.get_or_none(id=UUID(str(comment_id))).prefetch_related(
                *_COMMENT_PREFETCH, await reply_to_prefetch()
            )
            if not comment or not _belongs_to_topic(comment, channel):
                return
            await channel.send_event(
                ChannelEventResource.EMAIL_THREAD_COMMENT,
                action,
                comment=(await _serialize_one(comment, channel.current_user)).model_dump(mode="json"),
            )
            return

    # Reaction toggle — delivered to everyone (including the actor) for cross-tab sync.
    if updated_id := data.get("updated_comment_id"):
        comment = await EmailThreadComment.get_or_none(id=UUID(str(updated_id))).prefetch_related(*_COMMENT_PREFETCH)
        if not comment or not _belongs_to_topic(comment, channel):
            return
        users_by_id = await fetch_reaction_users([comment])
        await channel.send_event(
            ChannelEventResource.EMAIL_THREAD_COMMENT,
            ChannelEventAction.REACTION_TOGGLED,
            comment_id=str(updated_id),
            reactions={
                k: [u.model_dump() for u in v] for k, v in serialize_reactions(comment.reactions, users_by_id).items()
            },
        )
        return

    if deleted_id := data.get("deleted_comment_id"):
        if is_from_current_user(channel, data):
            return
        await channel.send_event(
            ChannelEventResource.EMAIL_THREAD_COMMENT,
            ChannelEventAction.REMOVED,
            comment_id=str(deleted_id),
        )
        return

    typing_user_ids: Any = data.get("typing_user_ids", [])
    if not isinstance(typing_user_ids, list):
        typing_user_ids = []

    # The actor's local UI tracks its own typing intent without a round-trip.
    typing_user_ids = [uid for uid in typing_user_ids if str(uid) != str(channel.current_user.id)]

    typing_users: list[User] = []
    if typing_user_ids:
        typing_users = await User.filter(id__in=typing_user_ids).select_related("avatar_file").all()

    serialized_typing = [resp.model_dump(mode="json") for u in typing_users if (resp := user_response(u))]
    await channel.send_event(
        ChannelEventResource.EMAIL_THREAD_COMMENT,
        ChannelEventAction.TYPING,
        typing_users=serialized_typing,
    )
