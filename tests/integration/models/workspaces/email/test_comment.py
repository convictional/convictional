import pytest

from app.models.workspaces.email.thread import EmailThreadComment
from tests.helpers.factories import create_email_thread, create_email_thread_comment, create_user


@pytest.mark.asyncio
async def test_comment_scoped_to_thread():
    user = await create_user()
    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    comment = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id)

    assert comment.email_thread_id == thread.id


@pytest.mark.asyncio
async def test_thread_comments_reverse_relation_ordered_by_created_at():
    user = await create_user()
    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    first = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, content="first")
    second = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, content="second")

    await thread.fetch_related("comments")
    # The reverse relation surfaces both comments ordered by created_at (Meta.ordering).
    assert {c.id for c in thread.comments} == {first.id, second.id}
    by_created_at = sorted(thread.comments, key=lambda c: c.created_at)
    assert [c.id for c in thread.comments] == [c.id for c in by_created_at]


@pytest.mark.asyncio
async def test_most_recent_comment_skips_soft_deleted():
    user = await create_user()
    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    first = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, content="first")
    second = await create_email_thread_comment(email_thread_id=thread.id, user_id=user.id, content="second")

    # The reverse relation bypasses the NonDeletedManager, so most_recent_comment must skip
    # soft-deleted comments itself — a deleted comment should never be the thread's latest activity.
    await second.soft_delete()
    await thread.fetch_related("comments")
    assert thread.most_recent_comment.id == first.id

    await first.soft_delete()
    await thread.fetch_related("comments")
    assert thread.most_recent_comment is None


@pytest.mark.asyncio
async def test_factory_derives_thread_from_workspace():
    user = await create_user()
    thread = await create_email_thread(organization_id=user.organization_id, creator_id=user.id)

    # Given a workspace_id, the factory resolves the thread and scopes the comment to it.
    comment = await create_email_thread_comment(workspace_id=thread.workspace_id, user_id=user.id)

    persisted = await EmailThreadComment.get(id=comment.id)
    assert persisted.email_thread_id == thread.id
