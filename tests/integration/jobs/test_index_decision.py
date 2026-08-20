import pytest
from fastapi import status

from app.jobs.content import (
    IndexChatJob,
    IndexDecisionJob,
    IndexDocumentJob,
    IndexEmailThreadJob,
    IndexPostJob,
)
from app.models.collaboration.content import (
    SERP_DEFAULT_CONTENT_TYPES,
    Content,
    ContentLookupQuery,
    ContentResearchQuery,
    IndexingID,
)
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import Mailbox
from app.models.collaboration.workspace import Collaborator, Decision
from app.models.workspaces.documents import DocumentComment
from app.models.workspaces.email.thread import EmailThread
from app.routers.api.serializers import detailed_content_response
from config import settings
from config.enums import ContentType
from infra.jobs import JobsOutbox
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_chat,
    create_chat_message,
    create_collaborator,
    create_decision,
    create_document,
    create_email_message,
    create_email_thread,
    create_email_thread_comment,
    create_organization,
    create_post,
    create_post_comment,
    create_user,
)


def _resource_indexing_id(organization_id, resource) -> IndexingID:
    return IndexingID(organization_id=organization_id, source_id=str(resource.global_id))


def _decision_indexing_id(decision: Decision) -> IndexingID:
    return IndexingID(organization_id=decision.workspace.organization_id, source_id=str(decision.global_id))


@pytest.mark.asyncio
async def test_index_decision_across_anchor_types():
    # A post comment anchor and a generic Comment anchor (email thread) both index
    # into a discrete decision Content row carrying the comment body + decider, with
    # access copied from the parent. The thread decision's decider is cleared
    # (SET_NULL) to confirm a deleted decider still indexes with author None.
    organization = await create_organization()
    decider = await create_user(organization_id=organization.id, name="Roger Decider")

    post = await create_post(organization_id=organization.id, creator_id=decider.id)
    post_comment = await create_post_comment(
        post_id=post.id, user_id=decider.id, content="We will migrate analytics to Postgres"
    )
    post_decision = await create_decision(post.workspace_id, post_comment, decided_by_id=decider.id)
    await post_decision.fetch_related("workspace")

    thread = await create_email_thread(organization_id=organization.id, creator_id=decider.id)
    thread_comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, organization_id=organization.id, content="Hire the new recruiter"
    )
    thread_decision = await create_decision(thread.workspace_id, thread_comment, decided_by_id=decider.id)
    await Decision.filter(id=thread_decision.id).update(decided_by_id=None)
    await thread_decision.fetch_related("workspace")

    # decider present on the post, cleared on the thread.
    for decision, comment, resource, expected_author in (
        (post_decision, post_comment, post, decider.display_name),
        (thread_decision, thread_comment, thread, None),
    ):
        indexing_id = _decision_indexing_id(decision)
        await IndexDecisionJob(indexing_id=indexing_id).perform()

        content = await Content.get_by_indexing_id(indexing_id).first()
        assert content.content_type == ContentType.DECISION
        assert content.source_id == str(decision.global_id)
        assert content.source_url == str(resource.global_id)
        assert content.author == expected_author
        assert comment.content in content.index_content
        assert content.metadata["comment_gid"] == str(decision.comment_gid)
        assert content.metadata["resource_gid"] == str(resource.global_id)
        expected_accessors = {str(c.user_id) for c in await Collaborator.filter(workspace_id=resource.workspace_id)}
        assert sorted(content.allowed_user_ids) == sorted(expected_accessors)

    # Retrievable via research, filtered to decisions.
    results = await ContentResearchQuery(
        organization=organization, query="Postgres", content_types={ContentType.DECISION}
    ).execute()
    assert [c.source_id for c in results] == [str(post_decision.global_id)]


@pytest.mark.asyncio
async def test_index_decision_access_matches_parent():
    # A private document: only its collaborators may retrieve the decision.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)
    member = await create_user(organization_id=organization.id)
    outsider = await create_user(organization_id=organization.id)

    document = await create_document(organization_id=organization.id, creator_id=owner.id)
    await create_collaborator(workspace_id=document.workspace_id, user_id=member.id)
    comment = await DocumentComment.create(
        content="Adopt the secret pricing model",
        quoted_text="quoted",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=owner.id,
    )
    decision = await create_decision(document.workspace_id, comment, decided_by_id=owner.id)
    await decision.fetch_related("workspace")

    indexing_id = _decision_indexing_id(decision)
    await IndexDecisionJob(indexing_id=indexing_id).perform()
    content = await Content.get_by_indexing_id(indexing_id).first()

    assert content.can_be_accessed_by(owner.id)
    assert content.can_be_accessed_by(member.id)
    assert not content.can_be_accessed_by(outsider.id)

    member_results = await ContentResearchQuery(
        organization=organization, query="pricing", user=member, content_types={ContentType.DECISION}
    ).execute()
    assert [c.source_id for c in member_results] == [str(decision.global_id)]

    outsider_results = await ContentResearchQuery(
        organization=organization, query="pricing", user=outsider, content_types={ContentType.DECISION}
    ).execute()
    assert outsider_results == []


@pytest.mark.asyncio
async def test_index_decision_clear_and_tombstone():
    organization = await create_organization()
    decider = await create_user(organization_id=organization.id)
    post = await create_post(organization_id=organization.id, creator_id=decider.id)
    comment = await create_post_comment(post_id=post.id, user_id=decider.id, content="Ship on Friday")
    decision = await create_decision(post.workspace_id, comment, decided_by_id=decider.id)
    await decision.fetch_related("workspace")
    indexing_id = _decision_indexing_id(decision)

    await IndexDecisionJob(indexing_id=indexing_id).perform()
    assert await Content.get_by_indexing_id(indexing_id).exists()

    # Tombstone: a soft-deleted anchor drops the decision row, Decision retained.
    await comment.soft_delete()
    await IndexDecisionJob(indexing_id=indexing_id).perform()
    assert not await Content.get_by_indexing_id(indexing_id).exists()
    assert await Decision.filter(id=decision.id).exists()

    # Clear: deleting the Decision then re-running removes the (already absent) row.
    await comment.restore()
    await IndexDecisionJob(indexing_id=indexing_id).perform()
    assert await Content.get_by_indexing_id(indexing_id).exists()
    await decision.delete()
    await IndexDecisionJob(indexing_id=indexing_id).perform()
    assert not await Content.get_by_indexing_id(indexing_id).exists()


@pytest.mark.asyncio
async def test_soft_deleting_decided_comment_on_notification_thread_drops_decision_index(background_jobs):
    # Regression: IndexEmailThreadJob short-circuits for an app-notification thread with no
    # active comments. It must still refresh the workspace's decisions on that path, otherwise
    # a decision anchored to a just-soft-deleted comment keeps its stale body searchable
    # (previously the hard-delete post_delete hook cleaned this up unconditionally).
    organization = await create_organization()
    decider = await create_user(organization_id=organization.id)
    message = await create_email_message(
        user_id=decider.id,
        organization_id=organization.id,
        external_thread_id="notification_decided_comment",
        sender=settings.email_from,
    )
    thread = await EmailThread.get(id=message.thread_id)
    comment = await create_email_thread_comment(
        email_thread_id=thread.id, user_id=decider.id, content="Acquire the vendor"
    )
    decision = await create_decision(thread.workspace_id, comment, decided_by_id=decider.id)
    await decision.fetch_related("workspace")
    decision_indexing_id = _decision_indexing_id(decision)
    thread_indexing_id = _resource_indexing_id(organization.id, thread)

    # Index once with the comment live: the decision's Content exists and holds its body.
    async with JobsOutbox():
        await IndexEmailThreadJob(indexing_id=thread_indexing_id).perform()
    assert await Content.get_by_indexing_id(decision_indexing_id).exists()

    # Soft-delete the comment, then re-index the thread. It early-returns (notification email,
    # no active comments) but must still drop the decision's stale search Content.
    await comment.soft_delete()
    async with JobsOutbox():
        await IndexEmailThreadJob(indexing_id=thread_indexing_id).perform()
    assert not await Content.get_by_indexing_id(decision_indexing_id).exists()
    assert await Decision.filter(id=decision.id).exists()


@pytest.mark.asyncio
async def test_index_decision_perform_enqueues_no_jobs(background_jobs):
    # No-loop invariant: the decision job must never enqueue the parent, which
    # would create a cycle with the parent job re-enqueuing the decision.
    organization = await create_organization()
    decider = await create_user(organization_id=organization.id)
    post = await create_post(organization_id=organization.id, creator_id=decider.id)
    comment = await create_post_comment(post_id=post.id, user_id=decider.id, content="Adopt the new logo")
    decision = await create_decision(post.workspace_id, comment, decided_by_id=decider.id)
    await decision.fetch_related("workspace")

    background_jobs.reset()
    # Flush any enqueues on exit: if perform() enqueued the parent it would run
    # here and land in completed, so an empty list proves the job enqueues nothing.
    async with JobsOutbox():
        await IndexDecisionJob(indexing_id=_decision_indexing_id(decision)).perform()
    assert background_jobs.completed == []
    assert background_jobs.scheduled == []


@pytest.mark.asyncio
async def test_decision_router_hooks_index_and_clean_up(client: AppClient, background_jobs):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="Launch in Q3")

    background_jobs.reset()
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
    )
    assert response.status_code == status.HTTP_201_CREATED
    decision_id = response.json()["id"]
    decision = await Decision.get(id=decision_id).prefetch_related("workspace")

    assert background_jobs.has_completed_job(IndexDecisionJob)
    assert background_jobs.has_completed_job(IndexPostJob)
    assert await Content.get_by_indexing_id(_decision_indexing_id(decision)).exists()

    background_jobs.reset()
    response = await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert background_jobs.has_completed_job(IndexDecisionJob)
    assert background_jobs.has_completed_job(IndexPostJob)
    assert not await Content.get_by_indexing_id(_decision_indexing_id(decision)).exists()


@pytest.mark.asyncio
async def test_orphaned_decision_content_cleaned_up(background_jobs):
    # Deleting a Decision instance (any path) fires the DELETE observer, which
    # enqueues the cleanup job and drops the orphaned Content row. Covers both
    # comment hard-delete (across anchor types) and the Post.publish bulk cleanup.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)

    # DocumentComment anchor.
    document = await create_document(organization_id=organization.id, creator_id=owner.id)
    doc_comment = await DocumentComment.create(
        content="Pick vendor B", quoted_text="q", comment_mark_id="m1", document_id=document.id, user_id=owner.id
    )
    doc_decision = await create_decision(document.workspace_id, doc_comment, decided_by_id=owner.id)
    await doc_decision.fetch_related("workspace")
    doc_indexing_id = _decision_indexing_id(doc_decision)
    await IndexDecisionJob(indexing_id=doc_indexing_id).perform()
    assert await Content.get_by_indexing_id(doc_indexing_id).exists()

    # Generic Comment anchor (email thread).
    thread = await create_email_thread(organization_id=organization.id, creator_id=owner.id)
    generic_comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, organization_id=organization.id, content="Sign the lease"
    )
    thread_decision = await create_decision(thread.workspace_id, generic_comment, decided_by_id=owner.id)
    await thread_decision.fetch_related("workspace")
    thread_indexing_id = _decision_indexing_id(thread_decision)
    await IndexDecisionJob(indexing_id=thread_indexing_id).perform()
    assert await Content.get_by_indexing_id(thread_indexing_id).exists()

    # Hard-deleting the comments fires delete_decision_for_comment; the cleanup
    # IndexDecisionJob runs when the outbox flushes on context exit.
    async with JobsOutbox():
        await doc_comment.delete()
        await generic_comment.delete()

    assert not await Decision.filter(id__in=[doc_decision.id, thread_decision.id]).exists()
    assert not await Content.get_by_indexing_id(doc_indexing_id).exists()
    assert not await Content.get_by_indexing_id(thread_indexing_id).exists()

    # Post.publish bulk-deletes the post's comments, orphaning their decisions.
    post = await create_post(organization_id=organization.id, creator_id=owner.id)
    post_comment = await create_post_comment(post_id=post.id, user_id=owner.id, content="Draft decision body")
    post_decision = await create_decision(post.workspace_id, post_comment, decided_by_id=owner.id)
    await post_decision.fetch_related("workspace")
    post_indexing_id = _decision_indexing_id(post_decision)
    await IndexDecisionJob(indexing_id=post_indexing_id).perform()
    assert await Content.get_by_indexing_id(post_indexing_id).exists()

    await post.fetch_related("workspace")
    async with JobsOutbox():
        await post.publish(content="Final published content", user_id=owner.id)

    assert not await Decision.filter(id=post_decision.id).exists()
    assert not await Content.get_by_indexing_id(post_indexing_id).exists()


@pytest.mark.asyncio
async def test_decision_excluded_from_typeahead_and_serp():
    organization = await create_organization()
    decider = await create_user(organization_id=organization.id)
    post = await create_post(organization_id=organization.id, creator_id=decider.id)
    comment = await create_post_comment(post_id=post.id, user_id=decider.id, content="Distinctive typeahead phrase")
    decision = await create_decision(post.workspace_id, comment, decided_by_id=decider.id)
    await decision.fetch_related("workspace")
    await IndexDecisionJob(indexing_id=_decision_indexing_id(decision)).perform()

    results = await ContentLookupQuery(organization=organization, query="Distinctive", current_user=decider).execute()
    assert all(c.content_type != ContentType.DECISION for c in results)

    # Decisions never appear in the default ("all") SERP results; they are filter-only (PR 4).
    assert ContentType.DECISION not in SERP_DEFAULT_CONTENT_TYPES


@pytest.mark.asyncio
async def test_parent_metadata_count_and_freshness(background_jobs):
    # A Post's Content row reflects how many decisions it contains and which comments
    # they anchor; the count surfaces through get_content; re-indexing the parent
    # re-enqueues each decision row, so a comment edit refreshes the decision's text
    # (its indexed body). A Post with none records an explicit zero, not an absent key.
    organization = await create_organization()
    decider = await create_user(organization_id=organization.id)

    post = await create_post(organization_id=organization.id, creator_id=decider.id)
    first = await create_post_comment(post_id=post.id, user_id=decider.id, content="Original body")
    second = await create_post_comment(post_id=post.id, user_id=decider.id, content="Decision two")
    first_decision = await create_decision(post.workspace_id, first, decided_by_id=decider.id)
    await create_decision(post.workspace_id, second, decided_by_id=decider.id)
    await first_decision.fetch_related("workspace")

    indexing_id = _resource_indexing_id(organization.id, post)
    async with JobsOutbox():
        await IndexPostJob(indexing_id=indexing_id).perform()

    content = await Content.get_by_indexing_id(indexing_id).first()
    assert content.metadata["decision_count"] == 2
    assert sorted(content.metadata["decided_comment_gids"]) == sorted([str(first.global_id), str(second.global_id)])
    # The decision count surfaces through get_content on the parent resource.
    assert detailed_content_response(content).metadata["decision_count"] == 2
    # The parent re-index re-enqueues each decision row (one per decision).
    assert background_jobs.has_completed_job(IndexDecisionJob, count=2)

    decision_content_id = _decision_indexing_id(first_decision)
    indexed = await Content.get_by_indexing_id(decision_content_id).first()
    assert "Original body" in indexed.index_content

    # Editing a decided comment and re-indexing the parent refreshes the decision text.
    first.content = "Revised body"
    await first.save()
    async with JobsOutbox():
        await IndexPostJob(indexing_id=indexing_id).perform()
    refreshed = await Content.get_by_indexing_id(decision_content_id).first()
    assert "Revised body" in refreshed.index_content
    assert "Original body" not in refreshed.index_content

    decisionless = await create_post(organization_id=organization.id, creator_id=decider.id)
    decisionless_id = _resource_indexing_id(organization.id, decisionless)
    async with JobsOutbox():
        await IndexPostJob(indexing_id=decisionless_id).perform()
    decisionless_content = await Content.get_by_indexing_id(decisionless_id).first()
    assert decisionless_content.metadata["decision_count"] == 0
    assert decisionless_content.metadata["decided_comment_gids"] == []


@pytest.mark.asyncio
async def test_parent_metadata_across_anchor_types():
    # The decision metadata rides every parent indexing job, not just Posts.
    organization = await create_organization()
    owner = await create_user(organization_id=organization.id)

    document = await create_document(organization_id=organization.id, creator_id=owner.id)
    await LiveDocument.set_initial_content(document.live_document_topic, "Document body text.")
    doc_comment = await DocumentComment.create(
        content="Adopt vendor B", quoted_text="q", comment_mark_id="m1", document_id=document.id, user_id=owner.id
    )
    await create_decision(document.workspace_id, doc_comment, decided_by_id=owner.id)

    email_message = await create_email_message(
        user_id=owner.id,
        organization_id=organization.id,
        external_thread_id="metadata_test",
        subject="Lease terms",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=email_message.thread_id)
    await Mailbox.sync(thread)
    thread_comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, organization_id=organization.id, content="Sign the lease"
    )
    await create_decision(thread.workspace_id, thread_comment, decided_by_id=owner.id)

    chat = await create_chat(organization_id=organization.id, creator_id=owner.id)
    chat_message = await create_chat_message(chat_id=chat.id, user_id=owner.id, content="Use the blue palette")
    await create_decision(chat.workspace_id, chat_message, decided_by_id=owner.id)

    for job_cls, resource in (
        (IndexDocumentJob, document),
        (IndexEmailThreadJob, thread),
        (IndexChatJob, chat),
    ):
        indexing_id = _resource_indexing_id(organization.id, resource)
        async with JobsOutbox():
            await job_cls(indexing_id=indexing_id).perform()
        content = await Content.get_by_indexing_id(indexing_id).first()
        assert content.metadata["decision_count"] == 1
