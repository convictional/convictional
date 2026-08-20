from typing import Any
from uuid import UUID

from app.helpers.url import url_for_content
from app.helpers.users import user_avatar_url
from app.models.accounts import Group, User
from app.models.collaboration.content import Content
from app.models.collaboration.workspace import LinkPreview
from app.models.workspaces.chat import ChatMessage
from app.models.workspaces.email.thread import EmailAttachment, EmailThreadComment
from app.models.workspaces.goals import GoalComment, GoalUpdate
from app.models.workspaces.posts import Post, PostComment
from app.presenters.activity import EventPresenter
from app.presenters.comment import CommentPresenter
from app.presenters.goals import GoalTimelinePresenter
from app.presenters.internal_link_previews import internal_resource_kind
from app.presenters.posts import PostPresenter
from app.routers.api.schemas import (
    ContentResponse,
    DetailedContentResponse,
    EmailDraftAttachmentResponse,
    GroupResponse,
    LinkPreviewFileResponse,
    LinkPreviewResponse,
    OrganizationUserResponse,
    PostCommentResponse,
    PostDraftResponse,
    PostPermissionsResponse,
    PostResponse,
    ProfileResponse,
    ReactionUserResponse,
    ReplyPreview,
    TimelineCommentResponse,
    TimelineEventResponse,
    TimelineGoalUpdateResponse,
    TimelineResponse,
    UserResponse,
)
from app.routers.dependencies import Helpers
from config.enums import EventAction, LinkPreviewStatus, ReactionType
from lib.markdown import markdown_to_plain_text
from lib.strings import truncate

REPLY_PREVIEW_MAX_LENGTH = 200


def _required_user_response(user: User) -> UserResponse:
    # For relations the caller guarantees are non-null (a post's creator, a commenter).
    return UserResponse(id=str(user.id), display_name=user.display_name, picture=user_avatar_url(user))


def user_response(user: User | None) -> UserResponse | None:
    return _required_user_response(user) if user else None


def group_response(group: Group | None) -> GroupResponse | None:
    if not group:
        return None
    return GroupResponse(id=str(group.id), name=group.name)


def profile_response(user: User) -> ProfileResponse:
    return ProfileResponse(
        name=user.name,
        bio=user.bio,
        time_zone=user.time_zone,
        picture=user_avatar_url(user),
        has_custom_avatar=user.avatar_file_id is not None,
    )


def organization_user_response(user: User, groups: list[Group]) -> OrganizationUserResponse:
    return OrganizationUserResponse(
        id=str(user.id),
        display_name=user.display_name,
        picture=user_avatar_url(user),
        email=user.email,
        bio=user.bio,
        is_admin=user.is_admin,
        active=not user.is_deleted,
        groups=[GroupResponse(id=str(g.id), name=g.name) for g in groups],
    )


def attachment_response(attachment: EmailAttachment, helpers: Helpers) -> EmailDraftAttachmentResponse:
    return EmailDraftAttachmentResponse(
        id=str(attachment.id),
        filename=attachment.file.filename,
        content_type=attachment.file.content_type,
        is_inline=attachment.is_inline,
        download_url=str(
            helpers.url_for(
                "email_attachments_download",
                email_thread_id=attachment.thread_id,
                attachment_id=attachment.id,
            )
        ),
    )


def serialize_reactions(
    reactions: dict[ReactionType, list[UUID]], users_by_id: dict[UUID, User]
) -> dict[str, list[ReactionUserResponse]]:
    result: dict[str, list[ReactionUserResponse]] = {}
    for reaction_type, user_ids in reactions.items():
        users = [
            ReactionUserResponse(id=str(uid), display_name=users_by_id[uid].display_name)
            for uid in user_ids
            if uid in users_by_id
        ]
        if users:
            result[str(reaction_type)] = users
    return result


async def fetch_reaction_users(comments: list[Any]) -> dict[UUID, User]:
    all_user_ids = {uid for c in comments for uids in c.reactions.values() for uid in uids}
    if not all_user_ids:
        return {}
    users = await User.filter(id__in=all_user_ids)
    return {u.id: u for u in users}


_SEARCH_METADATA_ALLOWLIST = {
    "scheduled_at",
    "reaction_count",
    "message_count",
    "comment_count",
    "has_calendar_invite",
    # Decision metadata: lets a consumer pivot from a decision search hit to its
    # parent resource, originating comment, and decider (all mirror parent access).
    "decided_by_id",
    "comment_gid",
    "resource_gid",
    # Parent-resource decision metadata: how many decisions a Post/Document/Chat/Email
    # thread contains, so a get_content on the parent reveals its decision_count.
    "decision_count",
}


def _filter_search_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {k: v for k, v in metadata.items() if k in _SEARCH_METADATA_ALLOWLIST}


def _is_shared_with_user(content: Content, user: User | None) -> bool:
    if not user or content.content_type.value != "email_thread":
        return False
    owner_id = (content.metadata or {}).get("owner_user_id")
    return owner_id is not None and str(user.id) != str(owner_id)


def content_response(
    content: Content,
    relevance_scores: dict[UUID, float] | None = None,
    user: User | None = None,
) -> ContentResponse:
    return ContentResponse(
        id=str(content.id),
        title=content.title,
        author=content.author,
        content_type=content.content_type.value,
        category=content.category.value,
        source_url=url_for_content(None, content),
        preview_content=content.preview_content,
        created_at=content.created_at,
        updated_at=content.updated_at,
        relevance_score=relevance_scores.get(content.id) if relevance_scores else None,
        metadata=_filter_search_metadata(content.metadata),
        shared_with_me=_is_shared_with_user(content, user),
    )


def content_responses(
    contents: list[Content],
    relevance_scores: dict[UUID, float] | None = None,
    user: User | None = None,
) -> list[ContentResponse]:
    return [content_response(c, relevance_scores, user) for c in contents]


def detailed_content_response(content: Content) -> DetailedContentResponse:
    base = content_response(content)
    return DetailedContentResponse(**base.model_dump(), index_content=content.index_content)


def timeline_comment_response(comment: GoalComment) -> TimelineCommentResponse:
    return TimelineCommentResponse(
        id=str(comment.id),
        content=comment.content,
        user=user_response(comment.user) if comment.user else None,
    )


def timeline_goal_update_response(update: GoalUpdate) -> TimelineGoalUpdateResponse:
    return TimelineGoalUpdateResponse(
        id=str(update.id),
        question_text=update.question_text,
        answer_text=update.answer_text,
        status=update.status.value,
        progress=update.progress,
        requested_by=user_response(update.requested_by) if update.requested_by else None,
    )


def timeline_event_response(event: EventPresenter) -> TimelineEventResponse:
    comment = None
    goal_update = None
    if event.model.action == EventAction.GOAL_COMMENTED:
        recordable = event.recordable
        model = recordable.model if isinstance(recordable, CommentPresenter) else recordable
        if isinstance(model, GoalComment):
            comment = timeline_comment_response(model)
    elif event.model.action == EventAction.GOAL_UPDATE_POSTED:
        if isinstance(event.recordable, GoalUpdate):
            goal_update = timeline_goal_update_response(event.recordable)

    return TimelineEventResponse(
        id=str(event.model.id),
        action=event.model.action.value,
        created_at=event.model.created_at,
        creator=user_response(event.creator),
        details=event.model.details,
        owner=user_response(event.owner) if event.owner else None,
        group=group_response(event.group) if event.group else None,
        replies=[timeline_event_response(reply) for reply in event.replies],
        comment=comment,
        goal_update=goal_update,
    )


def build_timeline_response(timeline: GoalTimelinePresenter) -> TimelineResponse:
    # Content only. Seen-by and the viewer's last-seen cursor are derived client-side from
    # the shared collaborators view_state query, so nothing view-state-related is computed here.
    return TimelineResponse(events=[timeline_event_response(event) for event in timeline.events])


def reply_preview(parent: ChatMessage | EmailThreadComment) -> ReplyPreview:
    # A soft-deleted target still loads (callers prefetch under allow_soft_deleted) so the
    # quote renders a tombstone instead of vanishing.
    content_preview = (
        "This message was deleted"
        if parent.is_deleted
        else truncate(markdown_to_plain_text(parent.content), REPLY_PREVIEW_MAX_LENGTH)
    )
    return ReplyPreview(
        id=str(parent.id),
        user_name=parent.user.display_name if parent.user else "",
        content_preview=content_preview,
        is_deleted=parent.is_deleted,
    )


def link_preview_response(
    link_preview: LinkPreview | None, files_by_url: dict[str, dict[str, Any]] | None = None
) -> LinkPreviewResponse | None:
    if not link_preview or link_preview.status != LinkPreviewStatus.READY:
        return None
    # A pasted attachment link persists only its filename; content type/size come from
    # files_by_url (resolve_preview_files), keyed by URL and gated by the reader's access.
    return LinkPreviewResponse(
        url=link_preview.url,
        title=link_preview.title,
        description=link_preview.description,
        image_url=link_preview.image_url,
        resource_kind=internal_resource_kind(link_preview.url),
        file=LinkPreviewFileResponse.from_attrs((files_by_url or {}).get(link_preview.url)),
    )


def post_comment_response(
    comment: PostComment,
    users_by_id: dict[UUID, User],
    replies: list[PostComment] | None = None,
    files_by_url: dict[str, dict[str, Any]] | None = None,
) -> PostCommentResponse:
    user = comment.user
    reply_responses = (
        [post_comment_response(reply, users_by_id, files_by_url=files_by_url) for reply in replies] if replies else []
    )
    link_preview = comment.link_preview if comment.link_preview_id else None
    return PostCommentResponse(
        id=str(comment.id),
        global_id=str(comment.global_id),
        content=comment.content,
        parent_id=str(comment.parent_id) if comment.parent_id else None,
        created_at=comment.created_at,
        updated_at=comment.updated_at,
        user=UserResponse(id=str(user.id), display_name=user.display_name, picture=user_avatar_url(user)),
        reactions=serialize_reactions(comment.reactions, users_by_id),
        replies=reply_responses,
        link_preview=link_preview_response(link_preview, files_by_url),
    )


def post_response(
    presenter: PostPresenter, current_user: User, files_by_url: dict[str, dict[str, Any]] | None = None
) -> PostResponse:
    # Serialize entirely from the presenter — it batch-loaded visits and flattened
    # all comments (with reaction-users + link-previews) in create_for_list, so
    # nothing here touches data the presenter didn't already load (no N+1).
    post = presenter.model
    original = presenter.original_comment
    comment_count = presenter.comment_count

    content_preview = None
    if original and original.model.content:
        content_preview = original.preview_text or None

    return PostResponse(
        id=str(post.id),
        title=post.title,
        creator=_required_user_response(post.creator),
        group=group_response(post.group) if post.group_id else None,
        workspace_id=str(post.workspace_id),
        is_announcement=post.is_announcement,
        is_pinned=post.is_pinned,
        pinned_at=post.pinned_at,
        content_preview=content_preview,
        link_preview=link_preview_response(original.link_preview, files_by_url) if original else None,
        comment_count=comment_count,
        new_comment_count=presenter.whats_new.total_count if presenter.whats_new else 0,
        # Null when there are no comments (the presenter falls back to the post's
        # own timestamp otherwise, which isn't a "last commented" time).
        last_commented_at=presenter.last_commented_at if comment_count > 0 else None,
        participants=[_required_user_response(u) for u in presenter.participants],
        permissions=PostPermissionsResponse(
            edit=post.editable_by(current_user),
            pin=Post.pinnable_by(current_user),
            delete=post.deletable_by(current_user),
        ),
    )


def post_draft_response(presenter: PostPresenter) -> PostDraftResponse:
    post = presenter.model
    return PostDraftResponse(
        id=str(post.id),
        title=post.title,
        creator=_required_user_response(post.creator),
        collaborators=[_required_user_response(c.user) for c in post.workspace.collaborators],
        updated_at=post.updated_at,
    )
