from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4 as generate_uuid

import pytest
from google.api_core.exceptions import NotFound
from pycrdt import Doc, Map, Text

from app.jobs.content import IndexDocumentJob, IndexMeetingJob
from app.jobs.live_documents import MergeAndNotifyLiveDocuments
from app.jobs.maintenance import (
    BulkGrantCollaboratorAccessJob,
    CleanupUnclaimedAttachmentsJob,
    EnqueueOutboxJob,
    IndexDecisionsJob,
    TerminateDeadCloudTasksJob,
)
from app.models.collaboration.content import Content, IndexingID
from app.models.collaboration.live import LiveDocumentUpdate
from app.models.collaboration.workspace import Attachment, Collaborator, Decision, Event
from config import settings
from config.enums import CollaboratorStatus, ContentType, EventAction, Sharing
from infra.jobs import InlineJobs, Job, JobDefinition, JobsOutbox
from tests.helpers.factories import (
    create_attachment,
    create_collaborator,
    create_decision,
    create_document,
    create_job,
    create_meeting,
    create_organization,
    create_post,
    create_post_comment,
    create_user,
)


class DummyMaintenanceJob(JobDefinition):
    async def perform(self):
        return "Test job completed"


@pytest.mark.asyncio
async def test_enqueue_cloud_tasks_job_finds_unenqueued_jobs(background_jobs: InlineJobs):
    # Use job timeout + buffer to ensure jobs are considered old enough to be unenqueued
    time_before_max_job_execution = datetime.now(UTC) - timedelta(seconds=settings.job_timeout_seconds + 300)
    # Use half the timeout to ensure jobs are still within the execution window
    time_within_max_job_execution = datetime.now(UTC) - timedelta(seconds=settings.job_timeout_seconds // 2)
    maintenance_job_definition = DummyMaintenanceJob()

    old_unenqueued_job1 = await create_job(maintenance_job_definition, created_at=time_before_max_job_execution)
    old_unenqueued_job2 = await create_job(maintenance_job_definition, created_at=time_before_max_job_execution)
    recent_unenqueued_job = await create_job(maintenance_job_definition, created_at=time_within_max_job_execution)
    enqueued_job = await create_job(
        maintenance_job_definition,
        created_at=time_before_max_job_execution,
        task_name="projects/test/locations/us-central1/queues/test-queue/tasks/test-task",
    )
    started_job = await create_job(
        maintenance_job_definition, created_at=time_before_max_job_execution, started_at=time_before_max_job_execution
    )
    completed_job = await create_job(
        maintenance_job_definition,
        created_at=time_before_max_job_execution,
        completed_at=time_before_max_job_execution,
    )
    terminated_job = await create_job(
        maintenance_job_definition,
        created_at=time_before_max_job_execution,
        terminated_at=time_before_max_job_execution,
    )

    # Run the maintenance job
    maintenance_job = EnqueueOutboxJob()
    async with JobsOutbox():
        await maintenance_job.perform()

    # The background_jobs InlineJobs fixture should have captured the enqueued jobs
    # Should have enqueued exactly 2 jobs (the old unenqueued ones)
    assert len(background_jobs.completed) == 2

    # Verify the correct jobs were enqueued by checking their IDs
    enqueued_job_ids = {job.id for job in background_jobs.completed}

    assert old_unenqueued_job1.id in enqueued_job_ids
    assert old_unenqueued_job2.id in enqueued_job_ids
    # Should NOT enqueue jobs that are recent, already enqueued, or running/completed
    assert recent_unenqueued_job.id not in enqueued_job_ids
    assert enqueued_job.id not in enqueued_job_ids
    assert started_job.id not in enqueued_job_ids
    assert completed_job.id not in enqueued_job_ids
    assert terminated_job.id not in enqueued_job_ids


@pytest.mark.asyncio
async def test_by_enqueued_not_completed_query():
    maintenance_job_definition = DummyMaintenanceJob()

    enqueued_job = await create_job(
        maintenance_job_definition,
        task_name="projects/test/locations/us-central1/queues/test-queue/tasks/test-task-1",
    )
    completed_job = await create_job(
        maintenance_job_definition,
        task_name="projects/test/locations/us-central1/queues/test-queue/tasks/test-task-2",
        completed_at=datetime.now(UTC),
    )
    terminated_job = await create_job(
        maintenance_job_definition,
        task_name="projects/test/locations/us-central1/queues/test-queue/tasks/test-task-3",
        terminated_at=datetime.now(UTC),
    )
    unenqueued_job = await create_job(maintenance_job_definition)  # No task_name

    enqueued_not_completed = await Job.by_enqueued_not_completed().all()
    enqueued_job_ids = [job.id for job in enqueued_not_completed]

    # Should only include jobs with task_name that are not completed or terminated
    assert enqueued_job.id in enqueued_job_ids
    assert completed_job.id not in enqueued_job_ids
    assert terminated_job.id not in enqueued_job_ids
    assert unenqueued_job.id not in enqueued_job_ids


@pytest.mark.asyncio
async def test_terminate_dead_cloud_tasks_terminates_jobs_with_missing_tasks():
    # Regression for DECIDE-8Y3: the job fetches Jobs via `.only(...)` which omits
    # `created_at`. Saving the partial instance must not raise AttributeError in the
    # set_timestamps pre_save signal.
    settings.gcp_project = "test-project"
    settings.gcp_location = "us-central1"

    dead_job = await create_job(
        DummyMaintenanceJob(),
        task_name="projects/test/locations/us-central1/queues/test-queue/tasks/missing-task",
    )
    original_created_at = dead_job.created_at

    mock_client = MagicMock()
    mock_client.get_task.side_effect = NotFound("task does not exist")

    with patch("app.jobs.maintenance.tasks_v2.CloudTasksClient", return_value=mock_client):
        await TerminateDeadCloudTasksJob().perform()

    refreshed = await Job.get(id=dead_job.id)
    assert refreshed.terminated_at is not None
    assert refreshed.created_at == original_created_at


@pytest.mark.asyncio
async def test_cleanup_unclaimed_attachments_after_grace_period():
    user = await create_user()
    now = datetime.now(UTC)
    old_time = now - timedelta(days=8)
    old_attachment = await create_attachment(
        user_id=user.id, workspace_id=None, claim_id=generate_uuid(), comment_gid=None, created_at=old_time
    )

    job = CleanupUnclaimedAttachmentsJob()
    await job.perform()

    assert await Attachment.get_or_none(id=old_attachment.id) is None


@pytest.mark.asyncio
async def test_cleanup_preserves_valid_attachments():
    user = await create_user()
    now = datetime.now(UTC)
    old_time = now - timedelta(days=8)
    recent_time = now - timedelta(days=3)

    # Recent unclaimed attachment (should be preserved)
    recent_attachment = await create_attachment(
        user_id=user.id, workspace_id=None, claim_id=generate_uuid(), comment_gid=None, created_at=recent_time
    )

    # Old claimed attachment (should be preserved)
    post = await create_post()
    claimed_attachment = await create_attachment(
        user_id=user.id,
        workspace_id=post.workspace_id,
        claim_id=None,
        comment_gid=post.global_id,
        created_at=old_time,
    )

    job = CleanupUnclaimedAttachmentsJob()
    await job.perform()

    assert await Attachment.get_or_none(id=recent_attachment.id) is not None
    assert await Attachment.get_or_none(id=claimed_attachment.id) is not None


@pytest.mark.asyncio
async def test_cleanup_preserves_attachments_referenced_in_document_content():
    # Regression for DECIDE-96C: document images are uploaded with a non-null `claim_id`
    # that no code path ever clears, so after 7 days `CleanupUnclaimedAttachmentsJob`
    # hard-deletes them even though the Yjs document markdown still references their URL.
    # The fix wires `MergeAndNotifyLiveDocuments._notify_document_mentions` to clear
    # `claim_id` for any attachment whose UUID appears in the merged document markdown.
    user = await create_user()
    document = await create_document(creator_id=user.id, organization_id=user.organization_id)

    attachment_id = generate_uuid()
    old_time = datetime.now(UTC) - timedelta(days=8)
    attachment = await create_attachment(
        id=attachment_id,
        user_id=user.id,
        workspace_id=document.workspace_id,
        claim_id=generate_uuid(),
        comment_gid=None,
        created_at=old_time,
    )

    topic = document.live_document_topic
    stable_time = datetime.now(UTC) - timedelta(minutes=20)

    # Two updates with content older than the merge job's stability window. The merge
    # job requires more than one update before it processes a topic.
    doc1: Doc = Doc()
    text1 = doc1.get("markdown", type=Text)
    text1 += (
        f"# Project Plan\n\n![diagram](/workspaces/{document.workspace_id}/attachments/{attachment_id}/download)\n"
    )

    with doc1.transaction():
        editors1: Map = doc1.get("editors", type=Map)
        editors1[str(user.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc1.get_update(),
        created_at=stable_time,
    )

    doc2: Doc = Doc()
    doc2.apply_update(doc1.get_update())
    text2 = doc2.get("markdown", type=Text)
    text2 += "\nMore details here."

    with doc2.transaction():
        editors2: Map = doc2.get("editors", type=Map)
        editors2[str(user.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc2.get_update(doc1.get_update()),
        created_at=stable_time + timedelta(minutes=1),
    )

    # Production order: merge job runs frequently (every ~15 min), cleanup runs less often.
    async with JobsOutbox():
        await MergeAndNotifyLiveDocuments(minutes=15).perform()

    await CleanupUnclaimedAttachmentsJob().perform()

    assert await Attachment.get_or_none(id=attachment.id) is not None, (
        "Attachment referenced in document markdown was deleted by the cleanup job"
    )


@pytest.mark.asyncio
async def test_cleanup_preserves_attachments_referenced_in_meeting_agenda():
    # Meeting agendas share the document image upload flow (useAttachments with no
    # explicit claimId), so they have the same gap: claim_id is never cleared and the
    # cleanup job hard-deletes referenced attachments after 7 days. The fix wires the
    # same sweep into MergeAndNotifyLiveDocuments._notify_meeting_agenda_updates.
    user = await create_user()
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    attachment_id = generate_uuid()
    old_time = datetime.now(UTC) - timedelta(days=8)
    attachment = await create_attachment(
        id=attachment_id,
        user_id=user.id,
        workspace_id=meeting.workspace_id,
        claim_id=generate_uuid(),
        comment_gid=None,
        created_at=old_time,
    )

    topic = meeting.agenda_topic
    stable_time = datetime.now(UTC) - timedelta(minutes=20)

    doc1: Doc = Doc()
    text1 = doc1.get("markdown", type=Text)
    text1 += f"# Agenda\n\n![board](/workspaces/{meeting.workspace_id}/attachments/{attachment_id}/download)\n"

    with doc1.transaction():
        editors1: Map = doc1.get("editors", type=Map)
        editors1[str(user.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc1.get_update(),
        created_at=stable_time,
    )

    doc2: Doc = Doc()
    doc2.apply_update(doc1.get_update())
    text2 = doc2.get("markdown", type=Text)
    text2 += "\nDiscussion points."

    with doc2.transaction():
        editors2: Map = doc2.get("editors", type=Map)
        editors2[str(user.id)] = True

    await LiveDocumentUpdate.create(
        topic_name=topic.name,
        update_data=doc2.get_update(doc1.get_update()),
        created_at=stable_time + timedelta(minutes=1),
    )

    async with JobsOutbox():
        await MergeAndNotifyLiveDocuments(minutes=15).perform()

    await CleanupUnclaimedAttachmentsJob().perform()

    assert await Attachment.get_or_none(id=attachment.id) is not None, (
        "Attachment referenced in meeting agenda markdown was deleted by the cleanup job"
    )


@pytest.mark.asyncio
async def test_cleanup_preserves_attachments_referenced_in_published_post(background_jobs: InlineJobs):
    # Post drafts use the same workspace attachment upload as documents, but the
    # draft → publish path never clears claim_id on inline images, so the cleanup
    # job hard-deletes them after 7 days. The fix wires Post.publish to clear
    # claim_id on attachments referenced in the published content.
    user = await create_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id, published_at=None)

    attachment_id = generate_uuid()
    old_time = datetime.now(UTC) - timedelta(days=8)
    attachment = await create_attachment(
        id=attachment_id,
        user_id=user.id,
        workspace_id=post.workspace_id,
        claim_id=generate_uuid(),
        comment_gid=None,
        created_at=old_time,
    )

    content = f"Big news\n\n![chart](/workspaces/{post.workspace_id}/attachments/{attachment_id}/download)\n"
    async with JobsOutbox():
        await post.publish(content, user.id)

    await CleanupUnclaimedAttachmentsJob().perform()

    assert await Attachment.get_or_none(id=attachment.id) is not None, (
        "Attachment referenced in published post content was deleted by the cleanup job"
    )


@pytest.mark.asyncio
async def test_bulk_grant_collaborator_access_happy_path(background_jobs: InlineJobs):
    source = await create_user()
    target = await create_user(organization_id=source.organization_id)

    private_meeting_1 = await create_meeting(
        creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE
    )
    private_meeting_2 = await create_meeting(
        creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE
    )
    private_document = await create_document(
        creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE
    )

    # Sharing.ORGANIZATION resources should NOT be granted — caller already has org-wide access
    org_meeting = await create_meeting(
        creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.ORGANIZATION
    )

    # Already-a-collaborator on private_meeting_2 → should be skipped (idempotent)
    await create_collaborator(workspace_id=private_meeting_2.workspace_id, user_id=target.id, added_by_id=source.id)

    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(source_user_email=source.email, target_user_email=target.email).perform()

    # Target is now a collaborator on both private meetings and the document
    assert await Collaborator.filter(workspace_id=private_meeting_1.workspace_id, user_id=target.id).exists()
    assert await Collaborator.filter(workspace_id=private_meeting_2.workspace_id, user_id=target.id).exists()
    assert await Collaborator.filter(workspace_id=private_document.workspace_id, user_id=target.id).exists()

    # Org-sharing meeting must NOT have target added as collaborator
    assert not await Collaborator.filter(workspace_id=org_meeting.workspace_id, user_id=target.id).exists()

    # An ADDED_COLLABORATOR event is recorded only for newly-added collaborators (not the pre-existing one)
    added_events = await Event.filter(action=EventAction.ADDED_COLLABORATOR)
    added_workspace_ids = {event.workspace_id for event in added_events}
    assert private_meeting_1.workspace_id in added_workspace_ids
    assert private_document.workspace_id in added_workspace_ids
    assert private_meeting_2.workspace_id not in added_workspace_ids
    assert org_meeting.workspace_id not in added_workspace_ids

    # ContentIndexingJob enqueued only for the newly-granted resources
    indexing_jobs = background_jobs.all_completed_jobs_by_type(
        IndexMeetingJob
    ) + background_jobs.all_completed_jobs_by_type(IndexDocumentJob)
    indexed_source_ids = {job.job_details["indexing_id"]["source_id"] for job in indexing_jobs}
    assert str(private_meeting_1.global_id) in indexed_source_ids
    assert str(private_document.global_id) in indexed_source_ids
    assert str(private_meeting_2.global_id) not in indexed_source_ids

    # Running the job again is idempotent: no additional collaborator rows, no new events
    collaborator_count_before = await Collaborator.filter(user_id=target.id).count()
    event_count_before = await Event.filter(action=EventAction.ADDED_COLLABORATOR).count()

    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(source_user_email=source.email, target_user_email=target.email).perform()

    assert await Collaborator.filter(user_id=target.id).count() == collaborator_count_before
    assert await Event.filter(action=EventAction.ADDED_COLLABORATOR).count() == event_count_before


@pytest.mark.asyncio
async def test_bulk_grant_collaborator_access_source_user_not_found():
    target = await create_user()

    private_meeting = await create_meeting(sharing=Sharing.PRIVATE)

    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(
            source_user_email=f"missing-{generate_uuid()}@example.com",
            target_user_email=target.email,
        ).perform()

    assert not await Collaborator.filter(workspace_id=private_meeting.workspace_id, user_id=target.id).exists()
    assert await Event.filter(action=EventAction.ADDED_COLLABORATOR).count() == 0


@pytest.mark.asyncio
async def test_bulk_grant_collaborator_access_target_user_not_found():
    source = await create_user()

    private_meeting = await create_meeting(
        creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE
    )

    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(
            source_user_email=source.email,
            target_user_email=f"missing-{generate_uuid()}@example.com",
        ).perform()

    # Only the creator collaborator should exist on the workspace (auto-added by signal);
    # no collaborator should have been created for the missing target user.
    workspace_collaborators = await Collaborator.filter(workspace_id=private_meeting.workspace_id)
    assert len(workspace_collaborators) == 1
    assert workspace_collaborators[0].user_id == source.id
    assert await Event.filter(action=EventAction.ADDED_COLLABORATOR).count() == 0


@pytest.mark.asyncio
async def test_bulk_grant_collaborator_access_refuses_cross_org_and_same_user():
    source = await create_user()

    # Cross-org target — must be refused
    other_org = await create_organization()
    cross_org_target = await create_user(organization_id=other_org.id)

    private_meeting = await create_meeting(
        creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE
    )

    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(
            source_user_email=source.email, target_user_email=cross_org_target.email
        ).perform()

    assert not await Collaborator.filter(
        workspace_id=private_meeting.workspace_id, user_id=cross_org_target.id
    ).exists()

    # Same-user — must be refused (no ADDED_COLLABORATOR event recorded)
    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(source_user_email=source.email, target_user_email=source.email).perform()

    assert await Event.filter(action=EventAction.ADDED_COLLABORATOR).count() == 0


@pytest.mark.asyncio
async def test_bulk_grant_collaborator_access_upgrades_pending_to_approved(background_jobs: InlineJobs):
    source = await create_user()
    target = await create_user(organization_id=source.organization_id)

    private_meeting = await create_meeting(
        creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE
    )

    await Collaborator.create(
        workspace_id=private_meeting.workspace_id,
        user_id=target.id,
        added_by_id=source.id,
        status=CollaboratorStatus.PENDING,
    )

    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(source_user_email=source.email, target_user_email=target.email).perform()

    collab = await Collaborator.unscoped.get_queryset().get(
        workspace_id=private_meeting.workspace_id, user_id=target.id
    )
    assert collab.status == CollaboratorStatus.APPROVED

    added_events = await Event.filter(action=EventAction.ADDED_COLLABORATOR, workspace_id=private_meeting.workspace_id)
    assert len(added_events) == 1

    indexing_jobs = background_jobs.all_completed_jobs_by_type(IndexMeetingJob)
    indexed_source_ids = {job.job_details["indexing_id"]["source_id"] for job in indexing_jobs}
    assert str(private_meeting.global_id) in indexed_source_ids


@pytest.mark.asyncio
async def test_bulk_grant_collaborator_access_paginates_across_batches(background_jobs: InlineJobs):
    source = await create_user()
    target = await create_user(organization_id=source.organization_id)

    meetings = [
        await create_meeting(creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE)
        for _ in range(3)
    ]
    documents = [
        await create_document(creator_id=source.id, organization_id=source.organization_id, sharing=Sharing.PRIVATE)
        for _ in range(2)
    ]

    # batch_size=2 + 3 meetings + 2 documents forces the continuation chain to cross
    # batch boundaries within Meeting and to advance from Meeting → Document → done.
    async with JobsOutbox():
        await BulkGrantCollaboratorAccessJob(
            source_user_email=source.email, target_user_email=target.email, batch_size=2
        ).perform()

    for resource in meetings + documents:
        assert await Collaborator.filter(workspace_id=resource.workspace_id, user_id=target.id).exists()

    # Continuation chain: M[0:2] → M[2:4] → M[4:6]=empty(advance) → D[0:2] → D[2:4]=empty(advance) → done
    bulk_grant_runs = background_jobs.all_completed_jobs_by_type(BulkGrantCollaboratorAccessJob)
    assert len(bulk_grant_runs) == 5  # 5 continuations after the initial direct perform() call

    added_events = await Event.filter(action=EventAction.ADDED_COLLABORATOR)
    assert len({event.workspace_id for event in added_events}) == 5


def _decision_content_id(decision: Decision) -> IndexingID:
    return IndexingID(organization_id=decision.workspace.organization_id, source_id=str(decision.global_id))


@pytest.mark.asyncio
async def test_index_decisions_backfill_indexes_each_decision_idempotently(background_jobs: InlineJobs):
    # The backfill creates one discrete decision Content row per existing decision AND
    # re-indexes the parent resource so its facet (decision_count + decided_comment_gids)
    # reflects them. A decision whose anchor comment is soft-deleted drops its own row
    # (tombstone) but still counts in the parent facet. Re-running changes nothing.
    organization = await create_organization()
    decider = await create_user(organization_id=organization.id)
    post = await create_post(organization_id=organization.id, creator_id=decider.id)

    live_comment = await create_post_comment(post_id=post.id, user_id=decider.id, content="Keep this decision")
    tombstoned_comment = await create_post_comment(post_id=post.id, user_id=decider.id, content="Drop this decision")
    live_decision = await create_decision(post.workspace_id, live_comment, decided_by_id=decider.id)
    tombstoned_decision = await create_decision(post.workspace_id, tombstoned_comment, decided_by_id=decider.id)
    await live_decision.fetch_related("workspace")
    await tombstoned_decision.fetch_related("workspace")
    await tombstoned_comment.soft_delete()

    # batch_size=1 forces the continuation chain across both decisions.
    async with JobsOutbox():
        await IndexDecisionsJob(organization_id=organization.id, batch_size=1).perform()

    assert await Content.get_by_indexing_id(_decision_content_id(live_decision)).exists()
    assert not await Content.get_by_indexing_id(_decision_content_id(tombstoned_decision)).exists()
    decision_rows = await Content.filter(
        Content.filters.by_organization(organization.id), content_type=ContentType.DECISION
    )
    assert len(decision_rows) == 1

    # The parent resource's facet reflects both decisions (the count includes the
    # tombstoned-anchor one, which has no retrievable decision row of its own).
    post_content = await Content.get_by_indexing_id(
        IndexingID(organization_id=organization.id, source_id=str(post.global_id))
    ).first()
    assert post_content.metadata["decision_count"] == 2
    assert sorted(post_content.metadata["decided_comment_gids"]) == sorted(
        [str(live_comment.global_id), str(tombstoned_comment.global_id)]
    )

    # A second run is a no-op: still exactly one decision Content row, same source_id.
    async with JobsOutbox():
        await IndexDecisionsJob(organization_id=organization.id, batch_size=1).perform()
    decision_rows_after = await Content.filter(
        Content.filters.by_organization(organization.id), content_type=ContentType.DECISION
    )
    assert {c.source_id for c in decision_rows_after} == {str(live_decision.global_id)}
