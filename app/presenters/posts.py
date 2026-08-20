from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from uuid import UUID

from tortoise.functions import Count, Max

from app.models.accounts import User
from app.models.collaboration.workspace import Decision, ViewStateResolver
from app.models.workspaces.posts import Post, PostComment
from app.presenters.base import BasePresenter
from app.presenters.comment import CommentPresenter


@dataclass
class PostDecision:
    # The most-recent decision on a post's workspace — the 1-of-N projection the
    # legacy single-decision Post columns used to hold. Posts can carry multiple
    # decisions (uniform with the other surfaces); the list card and what's-new
    # surface the latest one, plus `count` so the card can read "N decisions".
    decided_at: datetime
    decided_by: User | None
    comment_content: str | None
    count: int


async def latest_decisions_by_workspace(workspace_ids: list[UUID]) -> dict[UUID, PostDecision]:
    if not workspace_ids:
        return {}

    # Count + latest timestamp per workspace in one grouped query, so we never
    # load every decision row just to project the latest one. order_by("workspace_id")
    # clears the model's default decided_at ordering, which a GROUP BY rejects.
    aggregates = (
        await Decision.filter(workspace_id__in=workspace_ids)
        .annotate(count=Count("id"), latest_at=Max("decided_at"))
        .group_by("workspace_id")
        .order_by("workspace_id")
        .values("workspace_id", "count", "latest_at")
    )
    if not aggregates:
        return {}

    counts = {row["workspace_id"]: row["count"] for row in aggregates}
    # Fetch only the latest decision per workspace (the row whose decided_at is its
    # workspace's max), keyed by the (workspace_id, decided_at) pairs — bounded to
    # ~len(workspace_ids) rows rather than every decision. The pair set guards against
    # a max timestamp coinciding across workspaces.
    latest_pairs = {(row["workspace_id"], row["latest_at"]) for row in aggregates}
    candidates = await Decision.filter(
        workspace_id__in=workspace_ids, decided_at__in=[row["latest_at"] for row in aggregates]
    ).prefetch_related("decided_by")
    latest: dict[UUID, Decision] = {
        decision.workspace_id: decision
        for decision in candidates
        if (decision.workspace_id, decision.decided_at) in latest_pairs
    }

    # Post decisions always anchor to a PostComment; resolve bodies in one query.
    # Scoped (NonDeletedManager), so a soft-deleted anchor yields no preview — the
    # card still shows the decision, matching the legacy SET_NULL/soft-delete behaviour.
    comment_ids = [decision.comment_gid.record_id for decision in latest.values()]
    comments = await PostComment.filter(id__in=comment_ids) if comment_ids else []
    content_by_id = {comment.id: comment.content for comment in comments}

    return {
        workspace_id: PostDecision(
            decided_at=decision.decided_at,
            decided_by=decision.decided_by,
            comment_content=content_by_id.get(decision.comment_gid.record_id),
            count=counts[workspace_id],
        )
        for workspace_id, decision in latest.items()
    }


@dataclass
class WhatsNew:
    new_comments: list["PostCommentPresenter"] = field(default_factory=list)
    last_visit_at: datetime | None = None
    has_new_decision: bool = False

    @property
    def total_count(self) -> int:
        return len(self.new_comments) + (1 if self.has_new_decision else 0)

    @classmethod
    def compute(
        cls,
        all_comments: list["PostCommentPresenter"],
        original_comment: "PostCommentPresenter | None",
        last_visit_at: datetime | None,
        current_user_id: "UUID | None" = None,
    ) -> "WhatsNew":
        if not last_visit_at:
            return cls()

        # Comments created after last visit, excluding the original post content and
        # the current user's own comments. total_count drives the index "{n} new" badge.
        new_comments = [
            c
            for c in all_comments
            if c.model.created_at > last_visit_at
            and (original_comment is None or c.model.id != original_comment.model.id)
            and (current_user_id is None or c.model.user_id != current_user_id)
        ]
        return cls(new_comments=new_comments, last_visit_at=last_visit_at)


class PostCommentPresenter(CommentPresenter[PostComment]):
    replies: list["PostCommentPresenter"]


class PostPresenter(BasePresenter[Post]):
    original_comment: PostCommentPresenter | None
    top_level_comments: list[PostCommentPresenter]
    whats_new: WhatsNew | None
    decision: PostDecision | None

    @classmethod
    async def create(cls, model: Post):
        comments = list(model.comments)
        if model.original_comment and model.original_comment not in comments:
            comments.append(model.original_comment)

        all_comment_presenters = await PostCommentPresenter.create_from_list(comments)
        presenters_by_comment_id = {p.model.id: p for p in all_comment_presenters}
        presenter = cls._create_from_comment_presenters(model, presenters_by_comment_id)
        decisions = await latest_decisions_by_workspace([model.workspace_id])
        presenter.decision = decisions.get(model.workspace_id)
        return presenter

    @classmethod
    async def create_for_list(cls, posts: list[Post], current_user_id: UUID) -> list["PostPresenter"]:
        if not posts:
            return []

        workspace_ids = [p.workspace_id for p in posts]
        # "What's new" is derived read state keyed on when the user last saw the workspace
        # (last_viewed_at == Visit.updated_at). Read it through the shared resolver.
        view_states = await ViewStateResolver.for_user(current_user_id, workspace_ids)
        decisions_by_workspace_id = await latest_decisions_by_workspace(workspace_ids)

        # Batch all comments across all posts to avoid N+1 queries
        all_comments: list[PostComment] = []
        for post in posts:
            all_comments.extend(post.comments)
            if post.original_comment and post.original_comment not in post.comments:
                all_comments.append(post.original_comment)

        all_comment_presenters = await PostCommentPresenter.create_from_list(all_comments)
        presenters_by_comment_id = {p.model.id: p for p in all_comment_presenters}

        presenters = []
        for post in posts:
            presenter = cls._create_from_comment_presenters(post, presenters_by_comment_id)
            presenter.decision = decisions_by_workspace_id.get(post.workspace_id)
            presenter.whats_new = presenter.compute_whats_new(
                view_states[post.workspace_id].last_viewed_at, current_user_id
            )
            presenters.append(presenter)
        return presenters

    @classmethod
    def _create_from_comment_presenters(
        cls, post: Post, presenters_by_comment_id: dict[UUID, PostCommentPresenter]
    ) -> "PostPresenter":
        comment_presenters = [
            presenters_by_comment_id[c.id] for c in post.comments if c.id in presenters_by_comment_id
        ]

        original_comment = next(
            (p for p in comment_presenters if p.model == post.original_comment),
            None,
        )
        if original_comment is None and post.original_comment and post.original_comment.id in presenters_by_comment_id:
            original_comment = presenters_by_comment_id[post.original_comment.id]

        top_level_comments = [
            p for p in comment_presenters if original_comment and p != original_comment and not p.model.is_reply
        ]
        for comment in top_level_comments:
            comment.replies = [p for p in comment_presenters if p.model.parent_id == comment.model.id]

        return cls(
            model=post,
            original_comment=original_comment,
            top_level_comments=top_level_comments,
            whats_new=None,
            decision=None,
        )

    @cached_property
    def comment_count(self) -> int:
        return len(self._all_comments())

    @property
    def participants(self) -> list[User]:
        seen_ids: set[UUID] = set()
        users = []
        for comment in self._all_comments():
            if comment.user.id not in seen_ids:
                seen_ids.add(comment.user.id)
                users.append(comment.user)
        return users

    @property
    def last_commented_at(self) -> datetime:
        comments_by_date = sorted(self.top_level_comments, key=lambda comment: comment.model.created_at, reverse=True)
        if not comments_by_date:
            return self.original_comment.model.created_at if self.original_comment else self.model.created_at

        return comments_by_date[0].model.created_at

    def _all_comments(self) -> list[PostCommentPresenter]:
        comments = list(self.top_level_comments)
        for comment in self.top_level_comments:
            comments.extend(comment.replies)
        return comments

    def compute_whats_new(self, last_visit_at: datetime | None, current_user_id: UUID | None = None) -> WhatsNew:
        whats_new = WhatsNew.compute(self._all_comments(), self.original_comment, last_visit_at, current_user_id)
        decision = self.decision
        if (
            last_visit_at
            and decision
            and decision.decided_at > last_visit_at
            and (current_user_id is None or decision.decided_by is None or decision.decided_by.id != current_user_id)
        ):
            whats_new.has_new_decision = True
        return whats_new
