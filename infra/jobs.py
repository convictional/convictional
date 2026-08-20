import asyncio
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import wraps
from typing import Annotated, Any, ClassVar, Self
from urllib.parse import urljoin
from uuid import UUID
from uuid import uuid4 as generate_uuid

import sentry_sdk
from fastapi import APIRouter, Body, HTTPException, Request, status
from google.api_core.exceptions import NotFound
from google.cloud import tasks_v2
from google.protobuf import duration_pb2, timestamp_pb2
from pydantic import BaseModel, model_validator
from tortoise import BaseDBAsyncClient, fields
from tortoise.expressions import F

from config import logger, settings
from config.enums import JobQueue, JobStatus
from config.logging import LoggingContext
from config.settings import JobRunner
from infra.db import PartialIndex, RecordModel, transaction

#
# Job definition
#
#


JobDefinitionClass = type["JobDefinition"]
job_registry: dict[str, JobDefinitionClass] = {}
job_metadata_var: ContextVar[dict | None] = ContextVar("job_metadata_var", default=None)


class AsyncJobMetadataContext:
    def __init__(self, job_metadata: dict):
        self.job_metadata = job_metadata
        self.token: Any = Token[None]

    async def __aenter__(self):
        self.token = job_metadata_var.set(self.job_metadata)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        job_metadata_var.reset(self.token)


# Utility function to get job metadata
def get_job_metadata() -> dict | None:
    return job_metadata_var.get()


# Decorator to extract metadata from job and set up logging context
def with_job_metadata(func):
    @wraps(func)
    async def wrapper(job_instance: "Job", *args, **kwargs):
        metadata = job_instance.field_values
        # Add group information if present
        if job_instance.group_id:
            metadata["group_id"] = str(job_instance.group_id)

        # Extract ID fields for logging context
        id_fields = {k: v for k, v in metadata.items() if k.endswith("_id")}

        async with AsyncJobMetadataContext(metadata):
            with LoggingContext(
                job_id=job_instance.id,
                job_type=job_instance.job_type,
                job_queue=job_instance.queue.value,
                task_name=job_instance.task_name,
                **id_fields,
            ):
                return await func(job_instance, *args, **kwargs)

    return wrapper


class JobDefinition(BaseModel):
    perform_at: datetime | None = None
    queue: JobQueue | None = None
    unique: bool = False
    is_recurring: ClassVar[bool] = False
    default_queue: ClassVar[JobQueue] = JobQueue.MISCELLANEOUS
    retry_count: ClassVar[int] = 99

    def __init_subclass__(cls) -> None:
        job_registry[cls.job_type()] = cls
        super().__init_subclass__()

    @model_validator(mode="before")
    @classmethod
    def set_default_queue(cls, values):
        if "queue" not in values or values["queue"] is None:
            values["queue"] = cls.default_queue
        return values

    @classmethod
    def job_type(cls) -> str:
        job_type = re.sub("(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return job_type.removesuffix("_job")

    @classmethod
    def has_exhausted_retries(cls, retry_count: int) -> bool:
        return retry_count > cls.retry_count

    @classmethod
    def is_final_retry(cls, retry_count: int) -> bool:
        return retry_count == cls.retry_count

    async def perform(self):
        raise NotImplementedError("Must implement perform method")

    async def reschedule(self, retry_at: datetime):
        metadata = get_job_metadata()
        if not metadata:
            raise ValueError("Cannot reschedule job without metadata, is this running in a job?")

        job = await Job.get(id=metadata["id"])
        await job.reschedule(perform_at=retry_at)

    def dump(self):
        return self.model_dump_json(exclude={"perform_at", "queue", "unique"})

    async def last_started_at(self, using_db: BaseDBAsyncClient | None = None) -> datetime | None:
        last_job = (
            await Job.by_job_definition(self)
            .filter(completed_at__isnull=False, error__isnull=True)
            .using_db(using_db)
            .order_by("-started_at")
            .first()
        )
        return last_job.started_at if last_job else None


class JobGroup(RecordModel):
    total_jobs = fields.IntField(default=0)
    remaining_jobs = fields.IntField(default=0)
    callback_job_type: str | None = fields.TextField(max_length=500, null=True)
    callback_job_details: dict[str, Any] | None = fields.JSONField(null=True)
    jobs: fields.ReverseRelation["Job"]

    @property
    def is_complete(self) -> bool:
        return self.remaining_jobs == 0

    async def status(self, using_db: BaseDBAsyncClient | None = None) -> JobStatus:
        if await self.has_failed_jobs(using_db):
            return JobStatus.FAILED

        if self.is_complete:
            return JobStatus.SUCCESSFUL

        return JobStatus.STARTED

    async def add_job(self, job: "Job", using_db: BaseDBAsyncClient | None = None) -> None:
        await (
            JobGroup.filter(id=self.id)
            .using_db(using_db)
            .update(total_jobs=F("total_jobs") + 1, remaining_jobs=F("remaining_jobs") + 1)
        )
        await self.refresh_from_db(using_db=using_db)
        job.group_id = self.id
        await job.save(using_db=using_db)

    async def decrement(self, using_db: BaseDBAsyncClient | None = None) -> None:
        # Use SQL update to atomically decrement the counter only if it's greater than 0
        await (
            JobGroup.filter(id=self.id, remaining_jobs__gt=0)
            .using_db(using_db)
            .update(remaining_jobs=F("remaining_jobs") - 1)
        )
        await self.refresh_from_db(using_db=using_db)

    async def has_failed_jobs(self, using_db: BaseDBAsyncClient | None = None) -> bool:
        failed_count = await Job.filter(group_id=self.id, error__isnull=False).using_db(using_db).count()

        return failed_count > 0

    async def update_status(self, job: "Job", using_db: BaseDBAsyncClient | None = None) -> None:
        await self.decrement(using_db=using_db)

        if self.is_complete and not await self.has_failed_jobs(using_db):
            await self.enqueue_callback(using_db=using_db)

    async def enqueue_callback(self, using_db: BaseDBAsyncClient | None = None) -> None:
        if not self.is_complete or not self.callback_job_type or not self.callback_job_details:
            return

        job_definition_class = job_registry.get(self.callback_job_type, None)
        if not job_definition_class:
            raise ValueError(f"Job type '{self.callback_job_type}' not found")

        job_definition = job_definition_class(**self.callback_job_details, unique=True)
        await enqueue_job(job_definition, using_db=using_db)


class Job(RecordModel):
    job_type = fields.CharField(max_length=500)
    job_details: dict[str, Any] = fields.JSONField(default={})
    perform_at: datetime | None = fields.DatetimeField(null=True)
    started_at: datetime | None = fields.DatetimeField(null=True)
    completed_at: datetime | None = fields.DatetimeField(null=True)
    terminated_at: datetime | None = fields.DatetimeField(null=True)
    error: str | None = fields.TextField(null=True)
    task_name: str | None = fields.CharField(max_length=500, null=True)  # type: ignore
    queue = fields.CharEnumField(JobQueue, default=JobQueue.MISCELLANEOUS, max_length=255)
    rescheduled_from: fields.ForeignKeyNullableRelation["Job"] = fields.ForeignKeyField("convictional.Job", null=True)
    rescheduled_from_id: Annotated[UUID | None, "foreign key to job rescheduled from"]
    group: fields.ForeignKeyNullableRelation[JobGroup] = fields.ForeignKeyField(
        "convictional.JobGroup", null=True, related_name="jobs"
    )
    group_id: Annotated[UUID | None, "foreign key to job group"]

    class Meta:
        ordering = ["-created_at"]
        indexes = (
            ("job_type", "job_details"),
            ("group_id", "created_at"),
            PartialIndex(fields=["group_id"], extra="error IS NOT NULL"),
            PartialIndex(
                fields=["created_at"],
                extra="task_name IS NULL AND started_at IS NULL AND completed_at IS NULL AND terminated_at IS NULL",
            ),
            PartialIndex(
                fields=["created_at"],
                extra="task_name IS NOT NULL AND completed_at IS NULL AND terminated_at IS NULL",
            ),
            PartialIndex(fields=["completed_at"], extra="completed_at IS NOT NULL"),
            PartialIndex(fields=["terminated_at"], extra="terminated_at IS NOT NULL"),
        )

    @classmethod
    async def create_by_job_definition(
        cls,
        job_definition: JobDefinition,
        group_id: UUID | None = None,
        using_db: BaseDBAsyncClient | None = None,
        **kwargs,
    ):
        return await cls.create(
            job_type=job_definition.job_type(),
            job_details=job_definition.dump(),
            perform_at=job_definition.perform_at,
            queue=job_definition.queue or job_definition.default_queue,
            group_id=group_id,
            using_db=using_db,
            **kwargs,
        )

    @classmethod
    async def create_or_get_by_unique(
        cls, job_definition: JobDefinition, using_db: BaseDBAsyncClient | None = None
    ) -> tuple[Self, bool]:
        async def create_job(using_db: BaseDBAsyncClient | None = None):
            if job_definition.unique:
                existing_job = await Job.by_job_definition(job_definition).using_db(using_db).first()
                if existing_job and not existing_job.is_completed_or_dead:
                    return existing_job, False

            new_job = await Job.create_by_job_definition(job_definition, using_db=using_db)
            return new_job, True

        if using_db:
            job, was_new = await create_job(using_db)
        elif job_definition.unique:
            async with transaction() as connection:
                job, was_new = await create_job(connection)
        else:
            job, was_new = await create_job()

        return job, was_new

    @classmethod
    async def bulk_insert_by_unique(
        cls,
        job_definitions: Sequence[JobDefinition],
        group_id: UUID | None = None,
        using_db: BaseDBAsyncClient | None = None,
    ) -> tuple[list[Self], list[Self]]:
        jobs: list[Self] = []
        jobs_to_insert: list[JobDefinition] = []
        new_jobs: list[Self] = []
        async with transaction(using_db=using_db) as connection:
            for job_definition in job_definitions:
                if job_definition.unique:
                    existing_job = await cls.by_job_definition(job_definition).using_db(connection).first()
                    if existing_job and not existing_job.is_completed_or_dead:
                        jobs.append(existing_job)
                    else:
                        jobs_to_insert.append(job_definition)
                else:
                    jobs_to_insert.append(job_definition)

            if jobs_to_insert:
                job_objects = [
                    cls(
                        # Generate a new UUID for each job because `bulk_create` does not return the created objects
                        id=generate_uuid(),
                        job_type=job_definition.job_type(),
                        job_details=job_definition.dump(),
                        perform_at=job_definition.perform_at,
                        queue=job_definition.queue or job_definition.default_queue,
                        group_id=group_id,
                    )
                    for job_definition in jobs_to_insert
                ]
                await cls.bulk_create(objects=job_objects, using_db=connection)

                # Fetch the created jobs from database to get full details
                new_jobs = await cls.filter(id__in=[job.id for job in job_objects]).using_db(connection)

                jobs.extend(new_jobs)

        return jobs, new_jobs

    @classmethod
    def by_job_definition(cls, job_definition: JobDefinition, using_db: BaseDBAsyncClient | None = None):
        return cls.filter(job_type=job_definition.job_type(), job_details=job_definition.dump()).using_db(using_db)

    @classmethod
    def by_unenqueued(cls):
        cutoff_time = datetime.now(UTC) - timedelta(seconds=settings.job_timeout_seconds)
        return cls.filter(
            task_name__isnull=True,
            created_at__lt=cutoff_time,
            started_at__isnull=True,
            completed_at__isnull=True,
            terminated_at__isnull=True,
        )

    @classmethod
    def by_enqueued_not_completed(cls):
        return cls.filter(
            task_name__isnull=False,
            completed_at__isnull=True,
            terminated_at__isnull=True,
        )

    @property
    def job_definition(self) -> JobDefinition:
        job_definition_class = job_registry.get(self.job_type, None)
        if not job_definition_class:
            raise ValueError(f"Job type '{self.job_type}' not found")
        return job_definition_class(**self.job_details)

    @property
    def status(self):
        if self.terminated_at:
            return JobStatus.TERMINATED
        if self.completed_at:
            return JobStatus.SUCCESSFUL
        if self.error:
            return JobStatus.FAILED
        if self.started_at:
            return JobStatus.STARTED
        if self.perform_at and self.perform_at > datetime.now(UTC):
            return JobStatus.SCHEDULED
        if (
            not self.completed_at
            and not self.terminated_at
            and self.created_at < datetime.now(UTC) - timedelta(hours=settings.dead_job_interval_hours)
        ):
            return JobStatus.DEAD
        return JobStatus.ENQUEUED

    @property
    def is_completed(self):
        return self.status in [JobStatus.SUCCESSFUL, JobStatus.TERMINATED]

    @property
    def is_completed_or_dead(self):
        return self.status in [JobStatus.SUCCESSFUL, JobStatus.TERMINATED, JobStatus.DEAD]

    @with_job_metadata
    async def run(self):
        async with JobsOutbox():
            try:
                logger.info("Starting job")
                self.set_status(JobStatus.STARTED)
                await self.save()
                result = await self.job_definition.perform()

                async with transaction() as connection:
                    await self.refresh_from_db(using_db=connection)

                    # If the job status was changed during the perform method, don't mark it as successful
                    if self.status == JobStatus.STARTED:
                        self.set_status(JobStatus.SUCCESSFUL)
                        await self.save(using_db=connection)

                        if self.group_id:
                            group = await JobGroup.get(id=self.group_id, using_db=connection)
                            await group.update_status(self, using_db=connection)

                return result
            except Exception as e:
                logger.exception("Job failed")
                self.set_status(JobStatus.FAILED, str(e))
                await self.save()

                # If a job fails, we need to update its group status if it belongs to one
                if self.group_id:
                    try:
                        async with transaction() as connection:
                            group = await JobGroup.get(id=self.group_id, using_db=connection)
                            await group.update_status(self, using_db=connection)
                    except Exception as group_error:
                        logger.exception(f"Failed to update job group status: {group_error}")

                raise

    def set_status(self, status: JobStatus, error: str | None = None):
        self.error = None
        if status == JobStatus.TERMINATED:
            self.terminated_at = datetime.now(UTC)
        if status == JobStatus.SUCCESSFUL:
            self.completed_at = datetime.now(UTC)
        if status == JobStatus.STARTED:
            self.started_at = datetime.now(UTC)
        if status == JobStatus.FAILED:
            self.error = error

    async def reschedule(self, perform_at: datetime):
        await cancel_job(self)

        replacement = Job(
            job_type=self.job_type,
            job_details=self.job_details,
            perform_at=perform_at,
            task_name=self.task_name,
            queue=self.queue,
            rescheduled_from_id=self.id,
        )

        async with transaction() as connection:
            await replacement.save(using_db=connection)
            self.set_status(JobStatus.TERMINATED)
            await self.save(using_db=connection)

            # Update job group when job is terminated due to rescheduling
            if self.group_id:
                group = await JobGroup.get(id=self.group_id, using_db=connection)
                await group.update_status(job=self, using_db=connection)

            await JobsOutbox.add(replacement)

    async def terminate(self, using_db=None):
        async with transaction(using_db=using_db) as connection:
            self.set_status(JobStatus.TERMINATED)
            await self.save(using_db=connection)

            if self.group_id:
                group = await JobGroup.get(id=self.group_id, using_db=connection)
                await group.update_status(job=self, using_db=connection)


#
# Running jobs
#
#


class JobsOutbox:
    _jobs_outbox: ContextVar[list[Job]] = ContextVar("jobs_outbox", default=[])

    @classmethod
    async def add(cls, job: Job):
        outbox = cls._jobs_outbox.get()
        outbox.append(job)
        cls._jobs_outbox.set(outbox)

    @classmethod
    async def enqueue_pending(cls):
        jobs = await cls.get()
        await cls.reset()

        for job in jobs:
            await JOB_RUNNERS[settings.job_runner].enqueue(job)

        jobs_with_task_names = [j for j in jobs if j.task_name]
        if jobs_with_task_names:
            await Job.bulk_update(jobs_with_task_names, fields=["task_name"])

    @classmethod
    async def get(cls) -> list[Job]:
        return cls._jobs_outbox.get()

    @classmethod
    async def reset(cls):
        cls._jobs_outbox.set([])

    @classmethod
    async def cancel(cls, job: Job):
        jobs = cls._jobs_outbox.get()
        cls._jobs_outbox.set([j for j in jobs if j.id != job.id])

    def __init__(self):
        self.token: Token[list[Job]] | None = None

    async def __aenter__(self):
        self.token = self._jobs_outbox.set([])
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        jobs = self._jobs_outbox.get()
        if self.token is not None:
            self._jobs_outbox.reset(self.token)

        for index, job in enumerate(jobs, 1):
            if settings.sentry_dsn:
                sentry_sdk.set_context(
                    "Job", {"id": str(job.id), "type": job.job_type, "queue": job.queue, "details": job.job_details}
                )
            with LoggingContext(
                job_id=job.id, job_type=job.job_type, job_queue=job.queue, job_index=f"{index}/{len(jobs)}"
            ):
                await JOB_RUNNERS[settings.job_runner].enqueue(job)

        jobs_with_task_names = [j for j in jobs if j.task_name]
        if jobs_with_task_names:
            await Job.bulk_update(jobs_with_task_names, fields=["task_name"])

    @property
    def jobs(self) -> list[Job]:
        return self._jobs_outbox.get()


async def enqueue_job(job_definition: JobDefinition, using_db: BaseDBAsyncClient | None = None) -> Job:
    runner = settings.job_runner
    if runner not in JOB_RUNNERS:
        raise ValueError(f"Invalid job runner: {runner}")

    job, was_new = await Job.create_or_get_by_unique(job_definition, using_db)
    if was_new:
        await JobsOutbox.add(job)

    return job


async def bulk_enqueue_jobs(
    job_definitions: Sequence[JobDefinition], group_id: UUID | None = None, using_db: BaseDBAsyncClient | None = None
) -> list[Job]:
    runner = settings.job_runner
    if runner not in JOB_RUNNERS:
        raise ValueError(f"Invalid job runner: {runner}")

    jobs, new_jobs = await Job.bulk_insert_by_unique(job_definitions, group_id=group_id, using_db=using_db)

    for job in new_jobs:
        await JobsOutbox.add(job)

    return jobs


async def enqueue_job_group(
    job_definitions: Sequence[JobDefinition],
    callback: JobDefinition | None = None,
    using_db: BaseDBAsyncClient | None = None,
) -> JobGroup:
    job_group = JobGroup(total_jobs=len(job_definitions), remaining_jobs=len(job_definitions))

    if callback:
        job_group.callback_job_type = callback.job_type()
        job_group.callback_job_details = json.loads(callback.dump())

    await job_group.save(using_db=using_db)

    await bulk_enqueue_jobs(job_definitions, group_id=job_group.id, using_db=using_db)

    await job_group.fetch_related("jobs", using_db=using_db)

    return job_group


async def enqueue_job_in_group(job_definition: JobDefinition, using_db: BaseDBAsyncClient | None = None) -> Job:
    metadata = get_job_metadata() or {}
    group_id_str = metadata.get("group_id")
    async with transaction(using_db=using_db) as connection:
        if group_id_str:
            group_id = UUID(group_id_str)
        else:
            logger.info("Trying to enqueue a job in a group but no group ID was found, creating a new group.")
            job_group = await enqueue_job_group([job_definition], using_db=connection)
            return job_group.jobs[0]

        job_group = await JobGroup.get(id=group_id, using_db=connection)
        job = await Job.create_by_job_definition(job_definition, group_id=job_group.id, using_db=connection)
        await job_group.add_job(job, using_db=connection)

    await JobsOutbox.add(job)

    return job


async def cancel_job(job: Job):
    runner = settings.job_runner
    if runner not in JOB_RUNNERS:
        raise ValueError(f"Invalid job runner: {runner}")

    await JOB_RUNNERS[runner].cancel(job)
    await JobsOutbox.cancel(job)
    return job


class JobClient(ABC):
    @abstractmethod
    async def enqueue(self, job: Job):
        pass

    @abstractmethod
    async def cancel(self, job: Job):
        pass

    async def fetch_jobs_for_group(self, group_id: UUID) -> list[Job]:
        return await Job.filter(group_id=group_id).order_by("created_at").all()


class CloudTasksJobs(JobClient):
    _client: tasks_v2.CloudTasksAsyncClient | None = None

    @property
    def client(self) -> tasks_v2.CloudTasksAsyncClient:
        if self._client is None:
            self._client = tasks_v2.CloudTasksAsyncClient()
        return self._client

    async def enqueue(self, job: Job):
        if not settings.has_cloud_tasks:
            raise ValueError("Cloud Tasks not configured")

        queue = self.client.queue_path(settings.gcp_project, settings.gcp_location, job.queue.cloud_tasks_queue_name)

        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=urljoin(str(settings.jobs_service_url), f"jobs/{job.job_type}"),
                body=json.dumps(
                    {"id": str(job.id), "type": job.job_type, "definition": job.job_definition.dump()}
                ).encode(),
                headers={"Content-Type": "application/json"},
            )
        )

        if settings.cloud_tasks_service_account:
            task.http_request.oidc_token = tasks_v2.OidcToken(
                service_account_email=settings.cloud_tasks_service_account,
                audience=str(settings.jobs_service_url),
            )

        # Without this, Cloud Tasks defaults to a 10-minute HTTP dispatch deadline
        # regardless of the Cloud Run service timeout — a long-running job would
        # get killed at 10m and retried per the queue's retry_config. Align with
        # the Cloud Run revision's own timeout via settings.job_timeout_seconds.
        task.dispatch_deadline = duration_pb2.Duration(seconds=settings.job_timeout_seconds)

        if job.perform_at and job.perform_at > datetime.now(UTC):
            timestamp = timestamp_pb2.Timestamp()
            timestamp.FromDatetime(job.perform_at)
            task.schedule_time = timestamp

        response = await self.client.create_task(
            tasks_v2.CreateTaskRequest(
                parent=queue,
                task=task,
            )
        )

        job.task_name = response.name

    async def cancel(self, job: Job):
        if not job.task_name:
            return

        try:
            await self.client.delete_task(name=job.task_name)
        except NotFound:
            pass  # Task already deleted

        job.task_name = None
        job.set_status(JobStatus.TERMINATED)
        await job.save(update_fields=["task_name", "terminated_at"])


cloud_tasks_jobs = CloudTasksJobs()


@dataclass
class AsyncIOJobs(JobClient):
    _tasks: dict[UUID, tuple[Job, asyncio.Task]] = field(default_factory=dict)
    completed: list[Job] = field(default_factory=list)
    failed: list[tuple[Job, Exception]] = field(default_factory=list)

    async def enqueue(self, job: Job):
        if job.perform_at:
            return

        task = asyncio.create_task(self._run_job(job))
        self._tasks[job.id] = (job, task)

    async def _run_job(self, job: Job):
        try:
            await job.run()
            self.completed.append(job)
        except Exception as e:
            self.failed.append((job, e))
            raise
        finally:
            self._tasks.pop(job.id, None)

    async def cancel(self, job: Job):
        if job.id in self._tasks:
            _, task = self._tasks[job.id]
            if not task.done():
                task.cancel()
            self._tasks.pop(job.id, None)

    async def wait_for_all(self, timeout: float | None = None):
        # Keep waiting until all tasks complete, including ones created during execution
        start_time = asyncio.get_event_loop().time() if timeout else None

        while self._tasks:
            tasks = [task for _, task in self._tasks.values()]

            if timeout and start_time:
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = timeout - elapsed
                if remaining <= 0:
                    break
                await asyncio.wait(tasks, timeout=remaining)
            else:
                await asyncio.gather(*tasks, return_exceptions=True)

            # Small delay to let any new tasks be added
            if self._tasks:
                await asyncio.sleep(0.01)

    def is_done(self) -> bool:
        return len(self._tasks) == 0

    def reset(self):
        self._tasks.clear()
        self.completed.clear()
        self.failed.clear()


asyncio_jobs = AsyncIOJobs()


@dataclass
class InlineJobs(JobClient):
    scheduled: list[Job] = field(default_factory=list)
    completed: list[Job] = field(default_factory=list)
    failed: list[tuple[Job, Exception]] = field(default_factory=list)

    async def enqueue(self, job: Job):
        if job.perform_at and job.perform_at >= datetime.now(UTC):
            logger.warning(f"Job {job.id} is scheduled for {job.perform_at}, not running immediately.")
            self.scheduled.append(job)
            return

        try:
            await job.run()
            self.completed.append(job)
        except Exception as e:
            self.failed.append((job, e))

    async def cancel(self, job: Job):
        self.scheduled = [j for j in self.scheduled if j.id != job.id]

    def reset(self):
        self.scheduled.clear()
        self.completed.clear()
        self.failed.clear()

    def has_completed_job(self, job_definition: type[JobDefinition], count: int = -1) -> bool:
        if count == -1:
            return any(job.job_type == job_definition.job_type() for job in self.completed)
        return len([job for job in self.completed if job.job_type == job_definition.job_type()]) == count

    def find_completed_job_by_type(self, job_definition: type[JobDefinition]):
        return next((job for job in self.completed if job.job_type == job_definition.job_type()), None)

    def all_completed_jobs_by_type(self, job_definition: type[JobDefinition]):
        return [job for job in self.completed if job.job_type == job_definition.job_type()]

    def all_scheduled_jobs_by_type(self, job_definition: type[JobDefinition]):
        return [job for job in self.scheduled if job.job_type == job_definition.job_type()]

    def raise_first_failed(self):
        if self.failed:
            _, exception = self.failed[0]
            raise exception


inline_jobs = InlineJobs()


#
# API for job execution
#
#


class JobResponse(BaseModel):
    message: str = "Job performed successfully"


def create_job_route(job_type: str):
    async def perform_job_endpoint(request: Request, job_data: dict = Body(...)):
        headers = dict(request.headers)
        # Cloud Tasks retry count starts at 0, where 0 is the first attempt
        retry_count = int(headers.get("x-cloudtasks-taskretrycount", "0"))

        job = await Job.get_or_none(id=job_data["id"])
        if not job:
            # Sometimes, Cloud Tasks will call a job that doesn't exist yet.
            logger.warning(f"Could Tasks tried to call a {job_type} job that doesn't exist: {job_data['id']}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

        with LoggingContext(
            retry_count=retry_count, job_id=job.id, job_type=job.job_type, job_details=job.job_details
        ):
            if settings.sentry_dsn:
                sentry_sdk.set_context(
                    "Job",
                    {"id": str(job.id), "type": job.job_type, "details": job.job_details, "retry_count": retry_count},
                )

            if job.is_completed:
                logger.warning("Job was already completed")
                # 200 OK to indicate that the job was processed so it won't be retried again
                return JobResponse()

            if job.job_definition.is_final_retry(retry_count):
                try:
                    await job.run()
                except Exception:
                    pass

                await job.refresh_from_db()
                if not job.is_completed:
                    logger.warning("Job did not complete successfully on final retry, terminating")
                    await job.terminate()

                # 200 OK to indicate that the job was processed so it won't be retried again
                return JobResponse()
            elif job.job_definition.has_exhausted_retries(retry_count):
                logger.error("Job retry count exceeded limit, terminating")
                await job.terminate()

                # 200 OK to indicate that the job was processed so it won't be retried again
                return JobResponse()
            elif retry_count > 50:
                logger.warning("Job retry approaching limit")
            elif retry_count > 0:
                logger.info("Job retry attempted")

            await job.run()
            return JobResponse()

    return perform_job_endpoint


def create_recurring_job_route(job_type: str, job_class: type[JobDefinition]):
    async def enqueue_recurring_job_endpoint(request: Request):
        definition = job_class()

        with LoggingContext(is_recurring=True, job_type=job_type, job_definition=definition):
            if settings.sentry_dsn:
                sentry_sdk.set_context("Recurring Job", {"type": job_type})

            await enqueue_job(job_definition=definition)

    return enqueue_recurring_job_endpoint


def build_jobs_router() -> APIRouter:
    router = APIRouter()

    for job_type, job_class in job_registry.items():
        # Recurring jobs need an endpoint for Cloud Scheduler to call to enqueue them
        if job_class.is_recurring:
            endpoint = create_recurring_job_route(job_type, job_class)
            router.add_api_route(f"/recurring/{job_type}", endpoint, methods=["POST"])

        # All jobs need an endpoint for Cloud Tasks to call to perform them
        endpoint = create_job_route(job_type)
        router.add_api_route(f"/{job_type}", endpoint, methods=["POST"])

    return router


#
# Job runner
#
#

JOB_RUNNERS: dict[JobRunner, JobClient] = {
    JobRunner.CLOUD_TASKS: cloud_tasks_jobs,
    JobRunner.ASYNCIO: asyncio_jobs,
    JobRunner.INLINE: inline_jobs,
}
