from datetime import UTC, datetime, timedelta
from uuid import UUID

from google.api_core.exceptions import NotFound
from google.cloud import tasks_v2
from tortoise import Tortoise
from tortoise.functions import Count
from tortoise.queryset import QuerySet

from app.jobs.content import ContentIndexingJob, IndexDecisionJob
from app.jobs.goals import GenerateGoalTitleJob
from app.models.accounts import User
from app.models.collaboration.content import Content
from app.models.collaboration.workspace import (
    Attachment,
    Decision,
    WorkspaceMixin,
    WorkspaceMixinFilters,
    workspace_registry,
)
from app.models.workspaces.documents import Document
from app.models.workspaces.email.contact import EmailContact
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import Goal
from app.models.workspaces.meetings import Meeting
from config import logger, settings
from config.enums import ContentType, EventAction, JobQueue, JobStatus, Sharing
from config.logging import LoggingContext
from infra.cache import cache
from infra.db import allow_soft_deleted, transaction
from infra.jobs import JOB_RUNNERS, Job, JobDefinition, JobGroup, enqueue_job

if settings.sentry_dsn:
    import sentry_sdk

UNCLAIMED_ATTACHMENTS_GRACE_PERIOD_DAYS = 7


class IndexSearchJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    organization_id: UUID | None = None
    model_types: list[str] = ["User", "EmailContact"]
    workspace_types: list[str] = [
        "Document",
        "Post",
        "EmailThread",
        "Goal",
        "Meeting",
        "Chat",
    ]

    async def perform(self):
        for workspace_type in self.workspace_types:
            await enqueue_job(IndexWorkspacesJob(organization_id=self.organization_id, workspace_type=workspace_type))

        for model_type in self.model_types:
            await enqueue_job(IndexModelsJob(organization_id=self.organization_id, model_type=model_type))


class IndexWorkspacesJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    organization_id: UUID | None = None
    workspace_type: str
    batch_size: int = 100
    records_processed_so_far: int = 0

    async def perform(self):
        model_class = workspace_registry.get(self.workspace_type)
        if not model_class:
            raise ValueError(f"Invalid workspace type: {self.workspace_type}")

        async with allow_soft_deleted():
            queryset = model_class.all()
            if self.organization_id:
                queryset = queryset.filter(WorkspaceMixinFilters.by_organization(self.organization_id))

            models = await queryset.limit(self.batch_size).offset(self.records_processed_so_far)

        if not models:
            logger.info(
                f"Indexing complete for {self.workspace_type}. Total processed: {self.records_processed_so_far}"
            )
            return

        for model in models:
            await enqueue_job(ContentIndexingJob.from_model(model.organization_id, model))

        new_total = self.records_processed_so_far + len(models)
        logger.info(f"Indexed batch of {len(models)} {self.workspace_type} records. Total so far: {new_total}")

        await enqueue_job(
            IndexWorkspacesJob(
                organization_id=self.organization_id,
                workspace_type=self.workspace_type,
                batch_size=self.batch_size,
                records_processed_so_far=new_total,
                unique=True,
            )
        )


class IndexModelsJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    organization_id: UUID | None = None
    model_type: str
    batch_size: int = 100
    records_processed_so_far: int = 0

    async def perform(self):
        model_class: type[User | EmailContact]
        if self.model_type == "User":
            model_class = User
        elif self.model_type == "EmailContact":
            model_class = EmailContact
        else:
            raise ValueError(f"Invalid model type: {self.model_type}")

        queryset = model_class.all()
        if self.organization_id:
            queryset = queryset.filter(model_class.filters.by_organization(self.organization_id))
        models = await queryset.limit(self.batch_size).offset(self.records_processed_so_far)

        if not models:
            logger.info(f"Indexing complete for {self.model_type}. Total processed: {self.records_processed_so_far}")
            return

        for model in models:
            await enqueue_job(ContentIndexingJob.from_model(model.organization_id, model))

        new_total = self.records_processed_so_far + len(models)
        logger.info(f"Indexed batch of {len(models)} {self.model_type} records. Total so far: {new_total}")

        await enqueue_job(
            IndexModelsJob(
                organization_id=self.organization_id,
                model_type=self.model_type,
                batch_size=self.batch_size,
                records_processed_so_far=new_total,
                unique=True,
            )
        )


class IndexDecisionsJob(JobDefinition):
    # Standalone backfill for the existing decision corpus, run once on rollout (plus
    # ad-hoc reconciliation). Deliberately NOT wired into IndexSearchJob: a full reindex
    # already re-indexes every decision via the parent cascade (IndexWorkspacesJob → parent
    # job → _index_workspace_decisions), so wiring this in too would double-index every row
    # (harmless — idempotent upsert by source_id — but wasteful).
    default_queue = JobQueue.MAINTENANCE
    organization_id: UUID | None = None
    batch_size: int = 100
    records_processed_so_far: int = 0

    async def perform(self):
        # Decision has no organization_id of its own; the prefetch is required so resolving
        # the org per row is not an N+1 that times out at scale.
        queryset = Decision.all().prefetch_related("workspace")
        if self.organization_id:
            queryset = queryset.filter(workspace__organization_id=self.organization_id)

        decisions = await queryset.limit(self.batch_size).offset(self.records_processed_so_far)

        if not decisions:
            logger.info(f"Decision backfill complete. Total processed: {self.records_processed_so_far}")
            return

        for decision in decisions:
            organization_id = decision.workspace.organization_id
            # Mirror the live mark path (decisions router): index the discrete decision row
            # AND re-index the parent resource so its Content facet (decision_count +
            # decided_comment_gids) reflects the decision — IndexDecisionJob alone never
            # touches the parent. The explicit decision enqueue is the safety net for a
            # parent whose index short-circuits on empty content (the facet helper runs only
            # after that early return); unique collapses the parent re-index when a workspace
            # holds several decisions.
            await enqueue_job(IndexDecisionJob.from_model(organization_id, decision))
            resource = await decision.workspace.fetch_resource_or_none()
            if resource:
                parent_job = ContentIndexingJob.from_model(organization_id, resource)
                parent_job.unique = True
                await enqueue_job(parent_job)

        new_total = self.records_processed_so_far + len(decisions)
        logger.info(f"Indexed batch of {len(decisions)} decisions. Total so far: {new_total}")

        await enqueue_job(
            IndexDecisionsJob(
                organization_id=self.organization_id,
                batch_size=self.batch_size,
                records_processed_so_far=new_total,
                unique=True,
            )
        )


class CacheCleanupJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    is_recurring = True
    retry_count = 0

    async def perform(self):
        await cache.store.cleanup_expired()


class ReindexEmailThreadsForUserJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    batch_size: int = 100
    threads_processed_so_far: int = 0
    user_email: str

    async def perform(self):
        user = await User.get_or_none(email=self.user_email)
        if not user:
            logger.warning(f"User with email {self.user_email} not found. Aborting reindex.")
            return

        threads = (
            await EmailThread.filter(creator_id=user.id).limit(self.batch_size).offset(self.threads_processed_so_far)
        )
        if not threads:
            logger.info(f"Reindex complete. Total processed: {self.threads_processed_so_far}")
            return

        already_indexed = await Content.filter(
            content_type=ContentType.EMAIL_THREAD, source_id__in=[str(thread.global_id) for thread in threads]
        ).values_list("source_id", flat=True)

        for thread in threads:
            if str(thread.global_id) in already_indexed:
                continue
            await ContentIndexingJob.from_model(thread.organization_id, thread).perform()

        new_total = self.threads_processed_so_far + len(threads)
        logger.info(f"Indexed batch of {len(threads)} email threads. Total so far: {new_total}")

        await enqueue_job(
            ReindexEmailThreadsForUserJob(
                batch_size=self.batch_size, threads_processed_so_far=new_total, user_email=self.user_email, unique=True
            )
        )


class EnqueueOutboxJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0

    async def perform(self):
        unenqueued_jobs = await Job.by_unenqueued().all()

        if not unenqueued_jobs:
            return

        logger.info(f"Found {len(unenqueued_jobs)} jobs that need to be enqueued")

        successfully_enqueued = 0
        for job in unenqueued_jobs:
            with LoggingContext(
                job_id=job.id,
                job_type=job.job_type,
                job_queue=job.queue.value,
            ):
                try:
                    await JOB_RUNNERS[settings.job_runner].enqueue(job)
                    logger.info("Enqueued previously unenqueued job")
                    successfully_enqueued += 1
                except Exception:
                    logger.exception("Failed to enqueue job")

        logger.info(f"Successfully enqueued {successfully_enqueued} of {len(unenqueued_jobs)} jobs")


class TerminateDeadCloudTasksJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    is_recurring = True
    retry_count = 0
    batch_size: int = 100
    jobs_processed_so_far: int = 0
    successfully_checked: int = 0
    terminated_jobs: int = 0

    async def perform(self):
        if not settings.has_cloud_tasks:
            return

        enqueued_jobs = (
            await Job.by_enqueued_not_completed()
            .order_by("created_at")
            .only("id", "job_type", "queue", "task_name")
            .limit(self.batch_size)
            .offset(self.jobs_processed_so_far)
        )

        if not enqueued_jobs:
            if self.jobs_processed_so_far > 0:
                logger.info(
                    f"Successfully checked {self.successfully_checked} of {self.jobs_processed_so_far} jobs, "
                    f"terminated {self.terminated_jobs} jobs"
                )
            return

        client = tasks_v2.CloudTasksClient()

        for job in enqueued_jobs:
            if settings.sentry_dsn:
                sentry_sdk.set_context(
                    "Job",
                    {
                        "id": str(job.id),
                        "type": job.job_type,
                        "queue": job.queue.value,
                        "task_name": job.task_name,
                    },
                )

            with LoggingContext(
                job_id=job.id,
                job_type=job.job_type,
                job_queue=job.queue.value,
                task_name=job.task_name,
            ):
                try:
                    client.get_task(name=job.task_name)
                    self.successfully_checked += 1
                except NotFound:
                    # Refresh from DB to check if completed/terminated since we queried.
                    # Only refresh the columns we check — the job loaded above is partial
                    # (.only) and we don't need the wide JSONB/TEXT columns to terminate.
                    await job.refresh_from_db(fields=["completed_at", "terminated_at"])
                    if job.completed_at or job.terminated_at:
                        self.successfully_checked += 1
                        continue
                    await self.terminate_job(job)
                    self.successfully_checked += 1
                except Exception:
                    logger.exception("Failed to check Cloud Tasks status for job")

        new_total = self.jobs_processed_so_far + len(enqueued_jobs)

        if len(enqueued_jobs) == self.batch_size:
            await enqueue_job(
                TerminateDeadCloudTasksJob(
                    batch_size=self.batch_size,
                    jobs_processed_so_far=new_total,
                    successfully_checked=self.successfully_checked,
                    terminated_jobs=self.terminated_jobs,
                    unique=True,
                )
            )
        else:
            logger.info(
                f"Successfully checked {self.successfully_checked} of {new_total} jobs, "
                f"terminated {self.terminated_jobs} jobs"
            )

    async def terminate_job(self, job: Job) -> None:
        try:
            logger.warning("Cloud Tasks job not found, terminating job in database")
            if settings.sentry_dsn:
                sentry_sdk.capture_message("Cloud Tasks job not found, terminating job in database", level="warning")

            job.set_status(JobStatus.TERMINATED)
            await job.save(update_fields=["terminated_at"])
            self.terminated_jobs += 1
        except Exception:
            logger.exception("Failed to terminate job")


class HardDeleteUserJob(JobDefinition):
    """
    Completely and permanently deletes a user and all their associated data.

    This is a destructive operation intended for customer support use cases
    (e.g., GDPR "right to erasure" requests). Use with caution.

    WARNING: This will delete all workspace resources (meetings,
    tasks, etc.) created by the user. This data cannot be recovered.
    """

    default_queue = JobQueue.MAINTENANCE
    retry_count = 0
    user_email: str
    batch_size: int = 100

    async def perform(self):
        user = await User.get_or_none(email=self.user_email)
        if not user:
            logger.warning(f"User with email {self.user_email} not found. Aborting deletion.")
            return

        async with allow_soft_deleted():
            await self._delete_workspace_content(user, self.batch_size)
            private_content_queryset = Content.filter(Content.filters.private & Content.filters.by_accessor(user.id))
            await self._cleanup_content(user, self.batch_size, private_content_queryset)
            await self._delete_user_profile_content(user)
            await self._delete_user_workspaces(user, self.batch_size)
            await self._nullify_invited_by(user)
            await self._delete_user_record(user)

        logger.info(f"Successfully deleted user {user.id} ({self.user_email}) and all associated data")

    async def _delete_workspace_content(self, user: User, batch_size: int) -> None:
        """Delete Content records for workspaces created by user (batched per workspace type)."""
        for model_class in workspace_registry.values():
            workspace_type = model_class.__name__
            total_workspaces = 0
            offset = 0
            while True:
                workspaces = await model_class.filter(creator_id=user.id).limit(batch_size).offset(offset)
                if not workspaces:
                    break

                source_ids = [str(ws.global_id) for ws in workspaces]
                deleted_count = await Content.filter(source_id__in=source_ids).delete()
                total_workspaces += len(workspaces)

                logger.info(
                    f"Deleted {deleted_count} Content records for {len(workspaces)} {workspace_type} workspaces "
                    f"(batch offset {offset}, total processed: {total_workspaces})"
                )
                offset += batch_size

            if total_workspaces > 0:
                logger.info(f"Completed {workspace_type}: processed {total_workspaces} workspaces total")

    async def _delete_user_workspaces(self, user: User, batch_size: int) -> None:
        """Delete workspaces created by user (batched) to avoid large CASCADE on user deletion."""
        for model_class in workspace_registry.values():
            workspace_type = model_class.__name__
            total_deleted = 0
            while True:
                # Always query from offset 0 since deletes shift records up
                workspaces = await model_class.filter(creator_id=user.id).limit(batch_size)
                if not workspaces:
                    break

                workspace_ids = [ws.id for ws in workspaces]
                await model_class.filter(id__in=workspace_ids).delete()
                total_deleted += len(workspace_ids)

                logger.info(f"Deleted {len(workspace_ids)} {workspace_type} workspaces (total: {total_deleted})")

            if total_deleted > 0:
                logger.info(f"Completed {workspace_type} deletion: {total_deleted} workspaces total")

    async def _cleanup_content(self, user: User, batch_size: int, content_query: QuerySet) -> None:
        """Clean up private content where user is an accessor (remove user, delete if orphaned)."""
        total_processed = 0
        total_deleted = 0
        total_updated = 0
        offset = 0
        while True:
            content_list: list[Content] = await content_query.limit(batch_size).offset(offset)

            if not content_list:
                break

            batch_deleted = 0
            batch_updated = 0
            for content in content_list:
                content.remove_user(user.id)
                if content.is_orphaned:
                    await content.delete()
                    batch_deleted += 1
                else:
                    await content.save(update_fields=["allowed_user_ids"])
                    batch_updated += 1

            total_processed += len(content_list)
            total_deleted += batch_deleted
            total_updated += batch_updated

            logger.info(
                f"Processed {len(content_list)} private Content records: {batch_deleted} deleted (orphaned), "
                f"{batch_updated} updated (batch offset {offset}, total: {total_processed})"
            )
            offset += batch_size

        if total_processed > 0:
            logger.info(
                f"Completed private content cleanup: {total_processed} total processed, "
                f"{total_deleted} deleted, {total_updated} updated"
            )

    async def _delete_user_profile_content(self, user: User) -> None:
        """Delete user's profile from search index (source_id is a string field, not FK)."""
        await Content.filter(source_id=str(user.global_id)).delete()

    async def _nullify_invited_by(self, user: User) -> None:
        """Nullify invited_by_id references (no FK constraint exists on this column)."""
        await User.filter(invited_by_id=user.id).update(invited_by_id=None)

    async def _delete_user_record(self, user: User) -> None:
        """Delete user - CASCADE handles everything else automatically."""
        await user.delete()


_BULK_GRANT_MODELS: tuple[type[WorkspaceMixin], ...] = (Meeting, Document)


class BulkGrantCollaboratorAccessJob(JobDefinition):
    """
    Grants a target user collaborator access to every private Meeting and Document
    the source user created within the same organization.

    Intended for customer support use cases — typically handing off a departing
    user's private workspaces to a successor before deletion. CS-only; not exposed
    via the UI.

    Scope is intentionally limited to **Meeting and Document** private workspaces.
    Chat, Goal, Post, and EmailThread workspaces are not included. Resources shared
    at the organization level are skipped because the target already has access.

    Idempotent: re-running with the same source/target is safe — `collaboration.add`
    returns `was_added=False` for existing collaborators and no duplicate
    ADDED_COLLABORATOR events or ContentIndexingJobs are emitted.
    """

    default_queue = JobQueue.MAINTENANCE
    retry_count = 0
    source_user_email: str
    target_user_email: str
    batch_size: int = 100
    # Pagination state, carried across self-re-enqueue (mirrors ReindexEmailThreadsForUserJob).
    # Each invocation processes at most `batch_size` resources before yielding so we get
    # per-batch retry boundaries and stay well under settings.job_timeout_seconds.
    model_index: int = 0
    offset: int = 0
    added_so_far: int = 0
    skipped_so_far: int = 0
    failed_so_far: int = 0
    processed_so_far: int = 0
    # Resolved on the first invocation and carried through continuations so we don't
    # re-lookup the users on every batch.
    source_user_id: UUID | None = None
    target_user_id: UUID | None = None

    async def perform(self):
        with LoggingContext(
            source_user_email=self.source_user_email,
            target_user_email=self.target_user_email,
        ):
            # Source may be soft-deleted (this job exists to hand off a departing user's resources).
            async with allow_soft_deleted():
                if self.source_user_id is not None:
                    source_user = await User.get_or_none(id=self.source_user_id)
                else:
                    source_user = await User.get_or_none(email=self.source_user_email)
            if not source_user:
                logger.warning("Bulk grant aborted: source user not found")
                return

            if self.target_user_id is not None:
                target_user = await User.active.get_or_none(id=self.target_user_id)
            else:
                target_user = await User.active.get_or_none(email=self.target_user_email)
            if not target_user:
                logger.warning("Bulk grant aborted: target user not found or soft-deleted")
                return

            if source_user.id == target_user.id:
                logger.warning("Bulk grant aborted: source and target user are the same")
                return

            if source_user.organization_id != target_user.organization_id:
                logger.warning("Bulk grant aborted: cross-organization grant not allowed")
                return

            if self.model_index >= len(_BULK_GRANT_MODELS):
                with LoggingContext(
                    added=self.added_so_far,
                    skipped=self.skipped_so_far,
                    failed=self.failed_so_far,
                    processed=self.processed_so_far,
                ):
                    logger.info("Bulk grant complete")
                return

            model_class = _BULK_GRANT_MODELS[self.model_index]
            with LoggingContext(resource_type=model_class.__name__):
                resources = await (
                    model_class.filter(
                        creator_id=source_user.id,
                        sharing=Sharing.PRIVATE,
                    )
                    .prefetch_related("workspace")
                    .limit(self.batch_size)
                    .offset(self.offset)
                )

                if not resources:
                    await enqueue_job(
                        self._continuation(
                            advance_to_next_model=True,
                            source_user_id=source_user.id,
                            target_user_id=target_user.id,
                        )
                    )
                    return

                added = skipped = failed = 0
                for resource in resources:
                    try:
                        was_added = await self._grant_one(resource, source_user, target_user)
                        if was_added:
                            added += 1
                        else:
                            skipped += 1
                    except Exception:
                        failed += 1
                        with LoggingContext(resource_id=resource.id):
                            logger.exception("Bulk grant failed for resource")

                running_added = self.added_so_far + added
                running_skipped = self.skipped_so_far + skipped
                running_failed = self.failed_so_far + failed
                running_processed = self.processed_so_far + len(resources)

                with LoggingContext(
                    added=running_added,
                    skipped=running_skipped,
                    failed=running_failed,
                    processed=running_processed,
                    batch=len(resources),
                ):
                    logger.info("Bulk grant batch processed")

                await enqueue_job(
                    self._continuation(
                        advance_to_next_model=False,
                        source_user_id=source_user.id,
                        target_user_id=target_user.id,
                        added=running_added,
                        skipped=running_skipped,
                        failed=running_failed,
                        processed=running_processed,
                    )
                )

    def _continuation(
        self,
        *,
        advance_to_next_model: bool,
        source_user_id: UUID,
        target_user_id: UUID,
        added: int | None = None,
        skipped: int | None = None,
        failed: int | None = None,
        processed: int | None = None,
    ) -> "BulkGrantCollaboratorAccessJob":
        return BulkGrantCollaboratorAccessJob(
            source_user_email=self.source_user_email,
            target_user_email=self.target_user_email,
            source_user_id=source_user_id,
            target_user_id=target_user_id,
            batch_size=self.batch_size,
            model_index=self.model_index + 1 if advance_to_next_model else self.model_index,
            offset=0 if advance_to_next_model else self.offset + self.batch_size,
            added_so_far=self.added_so_far if added is None else added,
            skipped_so_far=self.skipped_so_far if skipped is None else skipped,
            failed_so_far=self.failed_so_far if failed is None else failed,
            processed_so_far=self.processed_so_far if processed is None else processed,
            unique=True,
        )

    async def _grant_one(self, resource: WorkspaceMixin, source_user: User, target_user: User) -> bool:
        async with transaction() as connection:
            _, was_added = await resource.collaboration.add(
                user_to_add=target_user,
                added_by_user=source_user,
                using_db=connection,
            )
            if not was_added:
                return False

            async with resource.workspace.record(
                EventAction.ADDED_COLLABORATOR,
                creator_id=source_user.id,
                using_db=connection,
            ) as recording:
                recording.event.details.update(
                    {
                        "collaborator": target_user.field_values,
                        "reason": f"bulk grant from {source_user.email}",
                    }
                )

            await enqueue_job(
                ContentIndexingJob.from_model(resource.organization_id, resource),
                using_db=connection,
            )
        return True


class ReindexContentHnswIndexJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    retry_count = 0

    async def perform(self):
        connection = Tortoise.get_connection("default")
        index_name = "idx_content_embeddi_d59ccd"

        logger.info(f"Starting concurrent reindex of {index_name}")

        try:
            await connection.execute_query(f'REINDEX INDEX CONCURRENTLY "{index_name}"')
            logger.info(f"Successfully reindexed {index_name}")
        except Exception:
            logger.exception(f"Failed to reindex {index_name}")
            raise


class CleanupUnclaimedAttachmentsJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    is_recurring = True
    retry_count = 0
    batch_size: int = 100
    attachments_deleted: int = 0

    async def perform(self):
        cutoff_time = datetime.now(UTC) - timedelta(days=UNCLAIMED_ATTACHMENTS_GRACE_PERIOD_DAYS)

        unclaimed_attachments = (
            await Attachment.filter(Attachment.filters.unclaimed(cutoff_time))
            .limit(self.batch_size)
            .prefetch_related("file")
        )

        if not unclaimed_attachments:
            if self.attachments_deleted > 0:
                with LoggingContext(
                    total_deleted=self.attachments_deleted,
                    cutoff_time=cutoff_time.isoformat(),
                ):
                    logger.info("Cleanup complete for unclaimed attachments")
            return

        deleted_count = 0
        for attachment in unclaimed_attachments:
            await attachment.delete()
            deleted_count += 1

        new_total = self.attachments_deleted + deleted_count

        with LoggingContext(
            batch_size=self.batch_size,
            deleted_count=deleted_count,
            total_deleted=new_total,
            cutoff_time=cutoff_time.isoformat(),
        ):
            logger.info("Deleted batch of unclaimed attachments")

        if len(unclaimed_attachments) == self.batch_size:
            await enqueue_job(
                CleanupUnclaimedAttachmentsJob(batch_size=self.batch_size, attachments_deleted=new_total, unique=True)
            )


CLEANUP_RETENTION_DAYS = 90
CLEANUP_BATCH_SIZE = 1000
CLEANUP_DELETE_CHUNK_SIZE = 100
PROTECTED_JOB_TYPES = {
    "ResearchJob",
    "ResearchIterationJob",
    "ProcessTranscriptJob",
    "SyncTranscriptFromRecallAIJob",
    "SyncRecordingFromRecallAIJob",
    "ScheduleRecallAIBotJob",
    "ExtractMeetingMetadataJob",
    "GenerateOptionsJob",
    "GenerateCriteriaJob",
    "ExtractBasicsJob",
}


class CleanupOldJobsJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    is_recurring = True
    retry_count = 0
    batch_size: int = CLEANUP_BATCH_SIZE
    retention_days: int = CLEANUP_RETENTION_DAYS

    async def perform(self):
        cutoff = datetime.now(UTC) - timedelta(days=self.retention_days)

        deleted_jobs = await self._delete_old_jobs(cutoff)
        deleted_groups = await self._delete_orphaned_job_groups()

        if deleted_jobs > 0 or deleted_groups > 0:
            logger.info(f"Cleaned up {deleted_jobs} old jobs and {deleted_groups} orphaned job groups")

        if deleted_jobs >= self.batch_size:
            await enqueue_job(CleanupOldJobsJob(batch_size=self.batch_size, retention_days=self.retention_days))

    async def _delete_old_jobs(self, cutoff: datetime) -> int:
        base_filter = Job.filter().exclude(job_type__in=PROTECTED_JOB_TYPES)
        half_batch = self.batch_size // 2

        completed_jobs = await base_filter.filter(completed_at__lt=cutoff).order_by().limit(half_batch).only("id")
        terminated_jobs = await base_filter.filter(terminated_at__lt=cutoff).order_by().limit(half_batch).only("id")

        job_ids = list({job.id for job in completed_jobs + terminated_jobs})
        if not job_ids:
            return 0

        deleted_count = 0
        for i in range(0, len(job_ids), CLEANUP_DELETE_CHUNK_SIZE):
            chunk = job_ids[i : i + CLEANUP_DELETE_CHUNK_SIZE]
            deleted_count += await Job.filter(id__in=chunk).delete()

        return deleted_count

    async def _delete_orphaned_job_groups(self) -> int:
        orphaned_groups = await JobGroup.annotate(job_count=Count("jobs")).filter(job_count=0).limit(1000)

        if not orphaned_groups:
            return 0

        group_ids = [group.id for group in orphaned_groups]
        return await JobGroup.filter(id__in=group_ids).delete()


class GenerateAllGoalTitlesJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    organization_id: UUID

    async def perform(self):
        parent_goals = await Goal.filter(Goal.filters.by_organization(self.organization_id) & Goal.filters.top_level)

        for goal in parent_goals:
            await enqueue_job(GenerateGoalTitleJob(goal_id=goal.id))


class GenerateMissingGoalTitlesJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE

    async def perform(self):
        goals_without_titles = await Goal.filter(Goal.filters.top_level, title="")

        for goal in goals_without_titles:
            await enqueue_job(GenerateGoalTitleJob(goal_id=goal.id))


class BackfillMailboxEntryReadAtJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    batch_size: int = 5000
    records_processed_so_far: int = 0

    async def perform(self):
        connection = Tortoise.get_connection("default")
        updated, _ = await connection.execute_query(
            """
            UPDATE "mailboxentry"
            SET read_at = last_activity_at
            WHERE id IN (
                SELECT id FROM "mailboxentry"
                WHERE read_at IS NULL AND NOT labels @> '["unread"]'::jsonb
                LIMIT $1
            )
            """,
            [self.batch_size],
        )
        new_total = self.records_processed_so_far + updated
        logger.info(f"Backfilled read_at for {updated} mailbox entries. Total so far: {new_total}")

        if updated >= self.batch_size:
            await enqueue_job(
                BackfillMailboxEntryReadAtJob(
                    batch_size=self.batch_size,
                    records_processed_so_far=new_total,
                )
            )
