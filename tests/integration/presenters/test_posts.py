from datetime import UTC, datetime

import pytest

from app.models.collaboration.workspace import Decision, Visit
from app.models.workspaces.posts import Post, PostComment
from app.presenters.posts import PostPresenter
from tests.helpers.factories import create_decision, create_post, create_post_comment, create_user


@pytest.mark.asyncio
async def test_compute_whats_new():
    user = await create_user()
    other_user = await create_user(organization_id=user.organization_id)
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    # Backdate the original comment so it's clearly the oldest
    await PostComment.filter(post_id=post.id).update(created_at=datetime(2024, 1, 1, tzinfo=UTC))

    last_visit = datetime(2024, 6, 1, tzinfo=UTC)

    # Old comment (before visit)
    old_comment = await create_post_comment(post_id=post.id, user_id=other_user.id, content="Old comment")
    await PostComment.filter(id=old_comment.id).update(created_at=datetime(2024, 3, 1, tzinfo=UTC))

    # New comment from other user (after visit)
    new_comment = await create_post_comment(post_id=post.id, user_id=other_user.id, content="New comment")
    await PostComment.filter(id=new_comment.id).update(created_at=datetime(2024, 7, 1, tzinfo=UTC))

    # New reply to old_comment from other user
    new_reply = await create_post_comment(
        post_id=post.id, user_id=other_user.id, parent_id=old_comment.id, content="New reply"
    )
    await PostComment.filter(id=new_reply.id).update(created_at=datetime(2024, 7, 2, tzinfo=UTC))

    # New comment from current user (should be excluded)
    own_comment = await create_post_comment(post_id=post.id, user_id=user.id, content="My own comment")
    await PostComment.filter(id=own_comment.id).update(created_at=datetime(2024, 7, 3, tzinfo=UTC))

    post = await Post.get(id=post.id).prefetch_related("comments__user", "workspace__collaborators")
    presenter = await PostPresenter.create(post)
    whats_new = presenter.compute_whats_new(last_visit, current_user_id=user.id)

    assert whats_new.total_count == 2
    assert not whats_new.has_new_decision
    # The two after-visit comments from another user count; the pre-visit comment and
    # the current user's own comment are excluded.
    new_ids = {str(c.model.id) for c in whats_new.new_comments}
    assert new_ids == {str(new_comment.id), str(new_reply.id)}


@pytest.mark.asyncio
async def test_compute_whats_new_with_decision():
    user = await create_user()
    other_user = await create_user(organization_id=user.organization_id)
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=other_user.id, content="Let's do it")
    await PostComment.filter(post_id=post.id).update(created_at=datetime(2024, 1, 1, tzinfo=UTC))

    last_visit = datetime(2024, 6, 1, tzinfo=UTC)

    async def whats_new_for_visit():
        # The presenter batch-loads the latest workspace decision; reload so the
        # projection reflects the row just created/updated.
        reloaded = await Post.get(id=post.id).prefetch_related("comments__user", "workspace__collaborators")
        presenter = await PostPresenter.create(reloaded)
        return presenter.compute_whats_new(last_visit, current_user_id=user.id)

    # Decision marked after last visit by another user
    decision = await create_decision(
        workspace_id=post.workspace_id,
        comment=comment,
        decided_by_id=other_user.id,
        decided_at=datetime(2024, 7, 1, tzinfo=UTC),
    )
    whats_new = await whats_new_for_visit()
    assert whats_new.has_new_decision
    assert whats_new.total_count == 1  # decision counts in total
    assert len(whats_new.new_comments) == 0  # no new comments

    # Decision marked by current user should be excluded
    await Decision.filter(id=decision.id).update(decided_by_id=user.id)
    whats_new = await whats_new_for_visit()
    assert not whats_new.has_new_decision
    assert whats_new.total_count == 0

    # Decision marked before last visit should not show
    await Decision.filter(id=decision.id).update(
        decided_by_id=other_user.id, decided_at=datetime(2024, 3, 1, tzinfo=UTC)
    )
    whats_new = await whats_new_for_visit()
    assert not whats_new.has_new_decision
    assert whats_new.total_count == 0


@pytest.mark.asyncio
async def test_create_for_list_whats_new_clears_after_visit_to_show_page():
    # Regression: the index counter must compare against the most recent visit
    # (Visit.updated_at), not the visit before it (Visit.last_visit_at). Visit.touch()
    # writes last_visit_at = previous updated_at, so reading last_visit_at would leave
    # the counter stuck for a full extra visit after the user actually read the comments.
    user = await create_user()
    other_user = await create_user(organization_id=user.organization_id)
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    await PostComment.filter(post_id=post.id).update(created_at=datetime(2024, 1, 1, tzinfo=UTC))

    comment = await create_post_comment(post_id=post.id, user_id=other_user.id, content="A new comment")
    await PostComment.filter(id=comment.id).update(created_at=datetime(2024, 6, 15, tzinfo=UTC))

    visit = await Visit.create(user_id=user.id, workspace_id=post.workspace_id)
    await Visit.filter(id=visit.id).update(
        last_visit_at=datetime(2024, 6, 1, tzinfo=UTC),
        updated_at=datetime(2024, 6, 20, tzinfo=UTC),
    )

    post = await Post.get(id=post.id).prefetch_related("comments__user", "workspace__collaborators")
    [presenter] = await PostPresenter.create_for_list([post], user.id)

    assert presenter.whats_new is not None
    assert presenter.whats_new.total_count == 0
