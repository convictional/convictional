from datetime import UTC, datetime

import pytest
from tortoise.exceptions import IntegrityError

from app.models.collaboration.workspace import Decision
from app.models.workspaces.documents import DocumentComment
from app.models.workspaces.posts import PostDraftComment
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_decision,
    create_document,
    create_email_thread,
    create_email_thread_comment,
    create_post,
    create_post_comment,
    create_user,
)


@pytest.mark.asyncio
async def test_decision_creation_and_unique_comment_gid():
    user = await create_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=user.id)

    decision = await create_decision(post.workspace_id, comment, decided_by_id=user.id)

    fetched = await Decision.get(id=decision.id)
    assert fetched.comment_gid == comment.global_id
    assert fetched.workspace_id == post.workspace_id
    assert fetched.decided_by_id == user.id
    assert fetched.decided_at is not None

    # One decision per comment
    with pytest.raises(IntegrityError):
        await Decision.create(
            workspace_id=post.workspace_id,
            comment_gid=comment.global_id,
            decided_at=datetime.now(UTC),
        )

    # Multiple decisions per workspace, on different comments
    second_comment = await create_post_comment(post_id=post.id, user_id=user.id)
    await create_decision(post.workspace_id, second_comment, decided_by_id=user.id)
    assert await Decision.filter(workspace_id=post.workspace_id).count() == 2


@pytest.mark.asyncio
async def test_clearable_by_allows_decider_and_admin_only():
    decider = await create_user()
    admin = await create_user(organization_id=decider.organization_id, is_admin=True)
    bystander = await create_user(organization_id=decider.organization_id)
    post = await create_post(creator_id=decider.id, organization_id=decider.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=decider.id)
    decision = await create_decision(post.workspace_id, comment, decided_by_id=decider.id)

    assert decision.clearable_by(decider) is True
    assert decision.clearable_by(admin) is True
    assert decision.clearable_by(bystander) is False

    # decided_by_id is null once the decider's account is deleted (SET_NULL):
    # only admins may clear it from then on.
    decision.decided_by_id = None
    assert decision.clearable_by(decider) is False
    assert decision.clearable_by(admin) is True


@pytest.mark.asyncio
async def test_hard_deleted_comment_cleans_up_its_decision():
    # EmailThreadComment (the email-thread decision anchor) is not soft-deletable
    thread = await create_email_thread()
    comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, organization_id=thread.organization_id
    )
    comment_decision = await create_decision(thread.workspace_id, comment)

    # Neither is DocumentComment
    document = await create_document()
    document_comment = await DocumentComment.create(
        content="What do you think?",
        quoted_text="some quoted text",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=document.creator_id,
    )
    document_decision = await create_decision(document.workspace_id, document_comment)

    # Neither is PostDraftComment
    user = await create_user()
    post = await create_post(published_at=None, creator_id=user.id, organization_id=user.organization_id)
    draft_annotation = await PostDraftComment.create(
        content="inline annotation",
        quoted_text="some quoted text",
        comment_mark_id="mark-1",
        post_id=post.id,
        user_id=user.id,
    )
    draft_annotation_decision = await create_decision(post.workspace_id, draft_annotation)

    await comment.delete()
    await document_comment.delete()
    await draft_annotation.delete()

    assert await Decision.get_or_none(id=comment_decision.id) is None
    assert await Decision.get_or_none(id=document_decision.id) is None
    assert await Decision.get_or_none(id=draft_annotation_decision.id) is None


@pytest.mark.asyncio
async def test_soft_deleted_comment_retains_its_decision():
    user = await create_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    post_comment = await create_post_comment(post_id=post.id, user_id=user.id)
    post_decision = await create_decision(post.workspace_id, post_comment, decided_by_id=user.id)

    chat = await create_chat()
    chat_message = await create_chat_message(chat_id=chat.id)
    chat_decision = await create_decision(chat.workspace_id, chat_message)

    await post_comment.soft_delete()
    await chat_message.soft_delete()

    assert await Decision.get_or_none(id=post_decision.id) is not None
    assert await Decision.get_or_none(id=chat_decision.id) is not None


@pytest.mark.asyncio
async def test_publish_cleans_up_decisions_on_bulk_deleted_comments():
    # Post.publish bulk-deletes draft-phase comments, which bypasses the
    # post_delete signal — the explicit cleanup in the publish transaction
    # must remove their decisions
    user = await create_user()
    post = await create_post(published_at=None, creator_id=user.id, organization_id=user.organization_id)
    draft_phase_comment = await create_post_comment(post_id=post.id, user_id=user.id)
    comment_decision = await create_decision(post.workspace_id, draft_phase_comment, decided_by_id=user.id)

    draft_annotation = await PostDraftComment.create(
        content="inline annotation",
        quoted_text="some quoted text",
        comment_mark_id="mark-1",
        post_id=post.id,
        user_id=user.id,
    )
    annotation_decision = await create_decision(post.workspace_id, draft_annotation, decided_by_id=user.id)

    await post.fetch_related("workspace")
    await post.publish("The final content", user.id)

    assert await Decision.get_or_none(id=comment_decision.id) is None
    assert await Decision.get_or_none(id=annotation_decision.id) is None
    # The canonical published comment exists and is undecided
    assert await Decision.filter(workspace_id=post.workspace_id).count() == 0
