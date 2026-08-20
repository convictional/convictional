import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from tortoise.functions import Max
from tortoise.queryset import QuerySet

from app.jobs.notifications import Notifier
from app.models.accounts import Group, GroupMember, User
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import (
    LinkPreview,
    SubscriberResolver,
    SubscriptionState,
    ViewStateResolver,
    Visit,
)
from app.models.workspaces.posts import Post, PostComment
from app.presenters.internal_link_previews import resolve_preview_files
from app.presenters.link_previews import prepare_link_preview_for_comment
from app.presenters.posts import PostPresenter
from app.routers.api.schemas import (
    PostCommentResponse,
    PostCreateRequest,
    PostDraftCreateRequest,
    PostDraftListResponse,
    PostDraftResponse,
    PostListDecisionResponse,
    PostListResponse,
    PostMailboxEntryResponse,
    PostPinUpdateRequest,
    PostResponse,
    PostShowResponse,
    PostUpdateRequest,
    PostViewsGroupResponse,
    PostViewsResponse,
    PostViewsTimelineEntry,
    SubscriptionResponse,
)
from app.routers.api.serializers import (
    fetch_reaction_users,
    post_comment_response,
    post_draft_response,
    post_response,
)
from app.routers.dependencies import (
    Helpers,
    UnclaimedAttachments,
    create_post_indexer,
    get_current_user,
    get_helpers,
    get_mailbox_entry_for_resource,
    get_post,
    post_context,
)
from config.enums import EventAction, PostStatusFilter, Sharing
from infra.db import Pagination, transaction
from lib.uuid import parse_uuid

# Relations the post list projection reads. Avatars are intentionally not
# prefetched: user_avatar_url reads only the scalar avatar_file_id, so an
# `__avatar_file` tail would fire a wasted batch query.
POST_SUMMARY_PREFETCH = (
    "creator",
    "group",
    "workspace__collaborators__user",
    "comments__user",
)


@dataclass
class PostFilterParams:
    queryset: QuerySet[Post]
    status: PostStatusFilter
    current_user: User
    group_id: str | None = None
    decided: bool = False
    cursor: str | None = None

    @property
    def group_uuid(self) -> UUID | None:
        return parse_uuid(self.group_id)

    def apply(self):
        if self.status == PostStatusFilter.DRAFTS:
            self.queryset = self.queryset.filter(Post.filters.drafts_visible_to(self.current_user.id))
        else:
            self.queryset = self.queryset.filter(Post.filters.published)

        if self.group_uuid and self.status != PostStatusFilter.DRAFTS:
            self.queryset = self.queryset.filter(Post.filters.by_group([self.group_uuid]))

        if self.decided and self.status != PostStatusFilter.DRAFTS:
            self.queryset = self.queryset.filter(Post.filters.decided(self.current_user.organization_id))

        # Drafts don't render a group, so they prefetch the card chain minus `group`.
        if self.status == PostStatusFilter.DRAFTS:
            draft_prefetch = [r for r in POST_SUMMARY_PREFETCH if r != "group"]
            self.queryset = self.queryset.order_by("-updated_at").prefetch_related(*draft_prefetch)
        else:
            self.queryset = (
                self.queryset.annotate(last_commented_at=Max("comments__created_at"))
                .order_by("-last_commented_at")
                .prefetch_related(*POST_SUMMARY_PREFETCH)
            )


router = APIRouter(
    dependencies=[Depends(create_post_indexer(), scope="function")],
    tags=["posts"],
)


#
# Helpers
#


def _subscription_response(state: SubscriptionState) -> SubscriptionResponse:
    return SubscriptionResponse(wants_all=state.wants_all, is_explicit=state.is_explicit)


async def _ensure_group_in_org(group_id: UUID | None, user: User) -> None:
    # A cross-org group_id would pull a foreign org's members onto the post's
    # workspace via the post-save collaborator signal (ensure_post_group_collaborators).
    if group_id is not None and not await Group.exists(id=group_id, organization_id=user.organization_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="group_id does not belong to this organization",
        )


async def _post_presenter(post: Post, current_user: User) -> PostPresenter:
    # Build the post projection (comment_count, participants, whats_new, etc.) from
    # an already-loaded post — get_post prefetches the comments/creator/group this
    # needs, so create_for_list only adds the visit + decision + reaction-user +
    # link-preview batch (no comment re-fetch).
    presenters = await PostPresenter.create_for_list([post], current_user.id)
    return presenters[0]


async def _fetch_post_presenter(post_id: UUID, current_user: User) -> PostPresenter:
    # Re-fetch a just-created post through the list projection (it isn't loaded with
    # the prefetch chain after a bare save), then serialize it the same way.
    post = await Post.get(id=post_id).prefetch_related(*POST_SUMMARY_PREFETCH)
    return await _post_presenter(post, current_user)


#
# Endpoints
#


# Published posts only; the cursor paginates `posts`. `pinned` filters the same
# collection (true → the featured rail, false → the feed body, omitted → all) —
# the index fetches the rail and feed in parallel. Drafts and search are separate
# endpoints (GET /api/posts/drafts, GET /api/search?content_type=post).
@router.get("/posts", response_model=PostListResponse)
async def api_posts_index(
    current_user: User = Depends(get_current_user),
    group_id: str | None = Query(None),
    decided: bool = Query(False),
    pinned: bool | None = Query(None),
    cursor: str | None = Query(None),
):
    filters = PostFilterParams(
        queryset=Post.filter(Post.filters.by_organization(current_user.organization_id)),
        status=PostStatusFilter.OPEN,
        current_user=current_user,
        group_id=group_id,
        decided=decided,
        cursor=cursor,
    )

    # The drafts-toggle badge is first-page-only — cursor pages don't recount.
    # Use `not cursor` (not `is None`) to match Pagination's own first-page test:
    # an empty `?cursor=` is the first page, and must still carry draft_count.
    is_first_page = not cursor
    draft_count = 0
    if is_first_page:
        drafts_filter = Post.filters.drafts_visible_to(current_user.id)
        draft_count = await Post.filter(
            Post.filters.by_organization(current_user.organization_id) & drafts_filter
        ).count()

    filters.apply()
    if pinned is True:
        # Pinned posts sort by pin recency, not comment activity.
        filters.queryset = filters.queryset.filter(Post.filters.pinned()).order_by("-pinned_at")
    elif pinned is False:
        filters.queryset = filters.queryset.filter(Post.filters.not_pinned())

    pagination = await Pagination.create(Post, cursor=cursor, queryset=filters.queryset)
    presenters = await PostPresenter.create_for_list(list(pagination), current_user.id)

    return PostListResponse(
        posts=[post_response(p, current_user) for p in presenters],
        decisions=[
            PostListDecisionResponse(
                post_id=str(p.model.id), count=p.decision.count, comment_preview=p.decision.comment_content
            )
            for p in presenters
            if p.decision is not None
        ],
        draft_count=draft_count,
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


# Drafts are scoped only by visibility (no group/decided filtering) and sorted
# by -updated_at.
@router.get("/posts/drafts", response_model=PostDraftListResponse)
async def api_posts_drafts_index(
    current_user: User = Depends(get_current_user),
    cursor: str | None = Query(None),
):
    filters = PostFilterParams(
        queryset=Post.filter(Post.filters.by_organization(current_user.organization_id)),
        status=PostStatusFilter.DRAFTS,
        current_user=current_user,
        cursor=cursor,
    )
    filters.apply()

    pagination = await Pagination.create(Post, cursor=cursor, queryset=filters.queryset)
    presenters = await PostPresenter.create_for_list(list(pagination), current_user.id)

    return PostDraftListResponse(
        drafts=[post_draft_response(p) for p in presenters],
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@router.post("/posts", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
async def api_posts_create(
    body: PostCreateRequest,
    current_user: User = Depends(get_current_user),
):
    # Announcements are admin-only; silently downgrade for non-admins rather than
    # rejecting (matches the long-standing create behavior).
    is_announcement = body.is_announcement and current_user.is_admin
    group_id = None if is_announcement else body.group_id
    await _ensure_group_in_org(group_id, current_user)
    post = Post(
        title=body.title,
        organization_id=current_user.organization_id,
        creator_id=current_user.id,
        group_id=group_id,
        is_announcement=is_announcement,
        published_at=datetime.now(UTC),
    )
    notifier = Notifier(post, current_user)
    link_preview_data = (
        await prepare_link_preview_for_comment(body.content, current_user) if body.unfurl_links else None
    )
    unclaimed_attachments = await UnclaimedAttachments.resolve(body.attachment_claim_id, current_user.id)

    action = EventAction.POST_ANNOUNCED if is_announcement else EventAction.POST_CREATED
    async with notifier.record_and_notify(recordable=post, action=action) as recording:
        await post.save(recording.using_db)
        await recording.event.workspace.fetch_related("collaborators", using_db=recording.using_db)
        comment = await PostComment.create(
            content=body.content, user_id=current_user.id, post_id=post.id, using_db=recording.using_db
        )
        await recording.resolve_mentions(body.content, recordable=comment)
        await LinkPreview.associate(PostComment, comment.id, link_preview_data, using_db=recording.using_db)
        recording.event.details["content"] = body.content
        post_context.set(post)
        await unclaimed_attachments.claim(post.workspace, comment, using_db=recording.using_db)

    return post_response(await _fetch_post_presenter(post.id, current_user), current_user)


@router.post("/posts/drafts", response_model=PostDraftResponse, status_code=status.HTTP_201_CREATED)
async def api_posts_drafts_create(
    body: PostDraftCreateRequest,
    current_user: User = Depends(get_current_user),
):
    # A draft is a distinct flow from publishing: blank-tolerant, Sharing.PRIVATE,
    # content stored as a LiveDocument (not a PostComment), and no
    # Notifier/mentions/link-preview/attachment claim.
    is_announcement = body.is_announcement and current_user.is_admin
    group_id = None if is_announcement else body.group_id
    # Validated even though the collaborator signal skips drafts — the group_id
    # persists and would fire the cross-org leak when the draft is published.
    await _ensure_group_in_org(group_id, current_user)
    async with transaction() as connection:
        post = Post(
            title=body.title.strip() or "Untitled draft",
            organization_id=current_user.organization_id,
            creator_id=current_user.id,
            sharing=Sharing.PRIVATE,
            group_id=group_id,
            is_announcement=is_announcement,
        )
        await post.save(using_db=connection)

        if body.content.strip():
            await LiveDocument.set_initial_content(post.live_document_topic, body.content, using_db=connection)
    post_context.set(post)

    return post_draft_response(await _fetch_post_presenter(post.id, current_user))


@router.get("/posts/{post_id}", response_model=PostShowResponse)
async def api_posts_show(
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
    mailbox_entry: MailboxEntry | None = Depends(get_mailbox_entry_for_resource),
):
    if post.is_draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    view_state = await ViewStateResolver.for_user_in_workspace(current_user.id, post.workspace_id)
    last_visit_at = view_state.last_viewed_at

    # Single comment-fetch with prefetched replies + link previews, sorted by created_at.
    # Bypasses the post-presenter machinery (which doesn't add value at the API layer here).
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

    # Resolve file-card metadata for every attachment-link preview in the payload — the post body
    # (the original comment's preview) and every comment/reply — in one batch, gated by the
    # requesting user's access, then build each response with it.
    files_by_url = await resolve_preview_files(
        [c.link_preview for c in all_comments if c.link_preview_id], current_user
    )

    original = post.original_comment
    original_response: PostCommentResponse | None = None
    top_level_responses: list[PostCommentResponse] = []
    for comment in comments:
        replies = sorted(list(comment.replies), key=lambda r: r.created_at)
        response = post_comment_response(comment, users_by_id, replies=replies, files_by_url=files_by_url)
        if original and comment.id == original.id:
            original_response = response
        else:
            top_level_responses.append(response)

    subscription_state = await SubscriberResolver(workspace=post.workspace).state_for(current_user.id)

    post_resp = post_response(await _post_presenter(post, current_user), current_user, files_by_url)

    return PostShowResponse(
        post=post_resp,
        original_comment=original_response,
        top_level_comments=top_level_responses,
        # Clients diff comment.created_at and post.decided_at against this to
        # render "what's new since I was last here."
        last_visit_at=last_visit_at,
        mailbox_entry=PostMailboxEntryResponse.from_entry(mailbox_entry) if mailbox_entry else None,
        subscription=_subscription_response(subscription_state),
    )


# Number of timeline buckets returned by GET /posts/{id}/views. Seven keeps the
# response small and matches the existing sparkline; adjust if the UI changes.
_VIEW_BUCKET_COUNT = 7


@router.get("/posts/{post_id}/views", response_model=PostViewsResponse)
async def api_posts_views(
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
):
    # Restricted to people who can act on the post (creator + admin); everyone
    # else gets 403, not an empty body.
    if current_user.id != post.creator_id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    # Reads raw Visit rows directly (not ViewStateResolver): this is view *analytics* over the
    # whole audience — per-row first-seen/last-seen timestamps for the sparkline buckets — not a
    # per-collaborator view-state lookup, so the resolver's CollaboratorViewState shape doesn't fit.
    queries: list = [
        Visit.filter(workspace_id=post.workspace_id).only("id", "created_at", "updated_at", "user_id").all(),
        User.active.get_queryset().filter(organization_id=current_user.organization_id).count(),
    ]
    if post.group_id:
        queries.append(GroupMember.filter(group_id=post.group_id).all())

    results = await asyncio.gather(*queries)
    visits = results[0]
    total_audience = results[1]

    group_response: PostViewsGroupResponse | None = None
    if post.group_id and isinstance(post.group, Group):
        members = results[2]
        member_ids = {m.user_id for m in members}
        visitor_ids = {v.user_id for v in visits}
        group_response = PostViewsGroupResponse(
            id=str(post.group.id),
            name=post.group.name,
            seen_count=len(visitor_ids & member_ids),
            total_audience=len(member_ids),
        )

    first_seen_at = min((v.created_at for v in visits), default=None)
    last_seen_at = max((v.updated_at for v in visits), default=None)

    return PostViewsResponse(
        seen_count=len(visits),
        total_audience=total_audience,
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        group=group_response,
        views=_view_buckets(visits, post.published_at, _VIEW_BUCKET_COUNT),
    )


def _view_buckets(
    visits: list[Visit], published_at: datetime | None, bucket_count: int
) -> list[PostViewsTimelineEntry]:
    if not published_at:
        return []
    now = datetime.now(UTC)
    total_seconds = (now - published_at).total_seconds()
    if total_seconds <= 0:
        return []

    duration = total_seconds / bucket_count
    counts = [0] * bucket_count
    for visit in visits:
        elapsed = (visit.created_at - published_at).total_seconds()
        if elapsed < 0:
            continue
        idx = min(int(elapsed / duration), bucket_count - 1)
        counts[idx] += 1

    return [
        PostViewsTimelineEntry(
            window_start=published_at + timedelta(seconds=i * duration),
            count=counts[i],
        )
        for i in range(bucket_count)
    ]


@router.post("/posts/{post_id}/publish", response_model=PostResponse)
async def api_posts_publish(
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
):
    # Publishing is an irreversible lifecycle action (creates the original
    # comment, claims attachments, clears draft comments, fires notifications),
    # so it's a POST action rather than a PATCH toggle. Any collaborator may
    # publish; get_post already scopes access. Re-publishing is idempotent.
    if post.is_published:
        return post_response(await _fetch_post_presenter(post.id, current_user), current_user)

    if post.title.strip() in ("", "Untitled draft"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Please give your post a title before publishing",
        )

    content = await post.get_live_document_markdown()
    if not content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot publish a draft with no content",
        )

    action = EventAction.POST_ANNOUNCED if post.is_announcement else EventAction.POST_CREATED
    notifier = Notifier(post, current_user)
    link_preview_data = await prepare_link_preview_for_comment(content, current_user)
    async with notifier.record_and_notify(action, recordable=post) as recording:
        comment = await post.publish(content, current_user.id, using_db=recording.using_db)
        await LinkPreview.associate(PostComment, comment.id, link_preview_data, using_db=recording.using_db)

    post_context.set(post)
    # publish() created the original comment in the DB; re-fetch so the projection
    # sees it (the in-memory post.comments from get_post is now stale).
    return post_response(await _fetch_post_presenter(post.id, current_user), current_user)


@router.patch("/posts/{post_id}/pin", response_model=PostResponse)
async def api_posts_pin_update(
    body: PostPinUpdateRequest,
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
):
    if not Post.pinnable_by(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    if body.pinned:
        notifier = Notifier(post, current_user)
        async with notifier.record_and_notify(EventAction.POST_PINNED) as recording:
            await post.pin(recording.using_db)
    else:
        await post.unpin()

    post_context.set(post)
    return post_response(await _post_presenter(post, current_user), current_user)


@router.patch("/posts/{post_id}", response_model=PostResponse)
async def api_posts_update(
    body: PostUpdateRequest,
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
):
    if not post.editable_by(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    post_changed = body.title is not None or body.clear_group_id or body.group_id is not None

    if not body.clear_group_id:
        await _ensure_group_in_org(body.group_id, current_user)

    original_comment = post.original_comment if body.content is not None else None
    if body.content is not None and original_comment is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Post has no original comment to edit",
        )

    link_preview_data = (
        await prepare_link_preview_for_comment(body.content, current_user)
        if body.content is not None and body.unfurl_links
        else None
    )
    # Claimed only inside the content-edit branch below; a claim-only PATCH never
    # reaches that branch (and at_least_one_edit rejects it as a no-op edit).
    unclaimed_attachments = await UnclaimedAttachments.resolve(body.attachment_claim_id, current_user.id)

    notifier = Notifier(post, current_user)
    async with transaction() as connection:
        if body.title is not None:
            post.title = body.title
        if body.clear_group_id:
            post.group_id = None
        elif body.group_id is not None:
            post.group_id = body.group_id
        if post_changed:
            await post.save(using_db=connection)

        if body.content is not None and original_comment is not None:
            original_comment.content = body.content
            await original_comment.save(using_db=connection)
            # Mirror api_post_comments_edit: resolve @mentions, notify, associate the
            # link preview, then broadcast so other tabs see the body update live.
            mentions = await post.workspace.resolve_mentions(
                body.content, original_comment.user_id, recordable=original_comment, using_db=connection
            )
            await notifier.notify_mentions(mentions, using_db=connection)
            await LinkPreview.associate(PostComment, original_comment.id, link_preview_data, using_db=connection)
            await unclaimed_attachments.claim(post.workspace, original_comment, using_db=connection)

    if body.content is not None and original_comment is not None:
        await original_comment.broadcast_edited()

    await post.fetch_related("group")
    post_context.set(post)
    return post_response(await _post_presenter(post, current_user), current_user)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_posts_delete(
    post: Post = Depends(get_post),
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
):
    if not post.deletable_by(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)

    was_draft = post.is_draft
    await post.soft_delete()

    if was_draft:
        next_url = str(helpers.url_for("posts_index").include_query_params(status=PostStatusFilter.DRAFTS.value))
    else:
        next_url = str(helpers.url_for("posts_index"))
    # Location header tells clients where to navigate after delete; body stays
    # empty so this is a clean 204 (per `CLAUDE.md` API contract).
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"Location": next_url})
