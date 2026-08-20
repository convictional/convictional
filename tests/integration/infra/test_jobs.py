from datetime import UTC, datetime
from uuid import UUID
from uuid import uuid4 as generate_uuid

import pytest

from config.enums import JobStatus
from infra.jobs import (
    InlineJobs,
    Job,
    JobDefinition,
    JobsOutbox,
    bulk_enqueue_jobs,
    enqueue_job,
    enqueue_job_group,
    enqueue_job_in_group,
)


@pytest.mark.asyncio
async def test_by_job_definition():
    class TestDefinition(JobDefinition):
        foo_id: UUID

        async def perform(self):
            pass

    # Test that a job is not found when it does not exist
    definition = TestDefinition(foo_id=generate_uuid())
    job = await Job.by_job_definition(definition).first()
    assert job is None
    assert await Job.all().count() == 0

    # Test that a job is created by the job definition
    job = await Job.create_by_job_definition(definition)
    assert job.job_type == "test_definition"
    assert job.job_details == {"foo_id": str(definition.foo_id)}
    assert await Job.all().count() == 1

    # Test that a job is found by the job definition
    job = await Job.by_job_definition(definition).first()
    assert job is not None
    assert job.job_type == "test_definition"
    assert job.job_details == {"foo_id": str(definition.foo_id)}
    assert await Job.all().count() == 1

    # Test that the most recently created job is found by the job definition
    job = await Job.create_by_job_definition(definition)
    get_job = await Job.by_job_definition(definition).first()
    assert job.id == get_job.id


@pytest.mark.asyncio
async def test_retries():
    run_count = 0
    should_raise_error = True

    class TestDefinition(JobDefinition):
        async def perform(self):
            nonlocal run_count
            run_count += 1
            if should_raise_error:
                raise ValueError(f"Test error {run_count}")

    definition = TestDefinition()

    # Test that a job is created by the job definition
    job = await Job.create_by_job_definition(definition)
    assert job.status == JobStatus.ENQUEUED

    # Test that the job is started
    with pytest.raises(ValueError):
        await job.run()
    assert job.status == JobStatus.FAILED
    assert job.error == "Test error 1"
    assert run_count == 1

    # Test that the job is retried
    with pytest.raises(ValueError):
        await job.run()
    assert job.status == JobStatus.FAILED
    assert job.error == "Test error 2"
    assert run_count == 2

    # Test that the job is retried a third time
    should_raise_error = False
    await job.run()
    assert job.status == JobStatus.SUCCESSFUL
    assert job.error is None
    assert run_count == 3


@pytest.mark.asyncio
async def test_enqueuing(background_jobs: InlineJobs):
    should_raise_error = False

    class TestDefinition(JobDefinition):
        foo: str

        async def perform(self):
            if should_raise_error:
                raise ValueError("Test error")

    # Test that a job is enqueued
    definition = TestDefinition(foo="bar")
    async with JobsOutbox():
        await enqueue_job(definition)

    assert await Job.all().count() == 1
    job = await Job.by_job_definition(definition).first()
    assert job is not None
    assert job.status == JobStatus.SUCCESSFUL

    # Test that a job is enqueued and retried
    definition = TestDefinition(foo="baz", unique=True)
    should_raise_error = True
    async with JobsOutbox():
        await enqueue_job(definition)

    assert len(background_jobs.failed) == 1
    job, exception = background_jobs.failed[0]
    assert isinstance(job.job_definition, TestDefinition)
    assert isinstance(exception, ValueError)
    background_jobs.reset()

    assert await Job.all().count() == 2
    job = await Job.by_job_definition(definition).first()
    assert job is not None
    assert job.status == JobStatus.FAILED

    # Test that a job is enqueued and retried with unique constraint
    await enqueue_job(definition)
    assert await Job.all().count() == 2


@pytest.mark.asyncio
async def test_job_rescheduling(background_jobs: InlineJobs):
    executions = 0

    class TestDefinition(JobDefinition):
        foo: str

        async def perform(self):
            nonlocal executions
            executions += 1
            if executions == 1:
                await self.reschedule(retry_at=datetime.now(UTC))

    definition = TestDefinition(foo="bar")
    async with JobsOutbox():
        await enqueue_job(definition)

    all_jobs = await Job.all().order_by("created_at").all()
    original = all_jobs[0]
    rescheduled = all_jobs[1]
    assert original.status == JobStatus.TERMINATED
    assert rescheduled.status == JobStatus.SUCCESSFUL
    assert rescheduled.perform_at is not None
    assert rescheduled.job_definition == original.job_definition
    assert rescheduled.job_details == original.job_details
    assert rescheduled.queue == original.queue
    assert rescheduled.task_name == original.task_name
    assert rescheduled.rescheduled_from_id == original.id
    assert executions == 2


class ExampleJob(JobDefinition):
    value: str

    async def perform(self):
        return self.value


class FailingJob(JobDefinition):
    async def perform(self):
        raise ValueError("Job failed intentionally")


class CallbackJob(JobDefinition):
    group_id: UUID

    async def perform(self):
        return f"Callback executed for group {self.group_id}"


@pytest.mark.asyncio
async def test_job_group_creation():
    job_definitions = [ExampleJob(value="job1"), ExampleJob(value="job2"), ExampleJob(value="job3")]
    job_group = await enqueue_job_group(job_definitions)

    assert job_group.total_jobs == 3
    assert job_group.remaining_jobs == 3
    assert job_group.is_complete is False

    jobs = await Job.filter(group_id=job_group.id).order_by("created_at").all()
    assert len(jobs) == 3

    # Verify job order
    assert jobs[0].job_details["value"] == "job1"
    assert jobs[1].job_details["value"] == "job2"
    assert jobs[2].job_details["value"] == "job3"


@pytest.mark.asyncio
async def test_job_group_completion():
    job_definitions = [ExampleJob(value="job1"), ExampleJob(value="job2")]
    callback = CallbackJob(group_id=generate_uuid())
    async with JobsOutbox():
        job_group = await enqueue_job_group(job_definitions, callback)

    await job_group.refresh_from_db()
    assert job_group.is_complete is True
    assert job_group.remaining_jobs == 0

    callback_jobs = await Job.filter(job_type=CallbackJob.job_type()).all()
    assert len(callback_jobs) == 1
    assert callback_jobs[0].status == JobStatus.SUCCESSFUL
    assert callback_jobs[0].job_details.get("group_id") is not None


@pytest.mark.asyncio
async def test_adding_jobs_to_group():
    class AddingJob(JobDefinition):
        async def perform(self):
            await enqueue_job_in_group(ExampleJob(value="child"))
            return "complete"

    async with JobsOutbox():
        job_group = await enqueue_job_group([AddingJob()])

    # Verify a new job was added to the group and the group is complete
    await job_group.refresh_from_db()
    assert job_group.is_complete is True
    assert job_group.total_jobs == 2
    assert job_group.remaining_jobs == 0

    # Ensure the child job was created and run
    child_job = await Job.get_or_none(group_id=job_group.id, job_type=ExampleJob.job_type())
    assert child_job
    assert child_job.status == JobStatus.SUCCESSFUL


@pytest.mark.asyncio
async def test_job_order_in_group():
    class OrderedJob(JobDefinition):
        position: int

        async def perform(self):
            return f"Executed position {self.position}"

    # Create job definitions with positions
    job_definitions = [OrderedJob(position=1), OrderedJob(position=2), OrderedJob(position=3)]

    async with JobsOutbox():
        await enqueue_job_group(job_definitions)

    jobs = await Job.filter(job_type=OrderedJob.job_type()).order_by("created_at").all()
    assert len(jobs) == 3
    assert all(job.status == JobStatus.SUCCESSFUL for job in jobs)
    # Verify the jobs were created in order (note order_by("created_at") in the query)
    for index, job in enumerate(jobs):
        assert job.job_details["position"] == index + 1


@pytest.mark.asyncio
async def test_group_with_failed_job(background_jobs: InlineJobs):
    job_definitions = [
        ExampleJob(value="job1"),
        FailingJob(),
        ExampleJob(value="job2"),
    ]

    # Use JobsOutbox without expecting an immediate exception
    async with JobsOutbox():
        job_group = await enqueue_job_group(job_definitions)

    # Verify the exception is captured in background_jobs
    assert len(background_jobs.failed) > 0
    _, exception = background_jobs.failed[0]
    assert isinstance(exception, ValueError)

    all_jobs = await Job.all()
    failing_jobs = [job for job in all_jobs if job.job_type == FailingJob.job_type()]
    success_jobs = [job for job in all_jobs if job.job_type == ExampleJob.job_type()]

    # All jobs are run in parallel, the failed job does not block the others
    # If the failing job should enqueue another job (sequential JobGroup) that job would not be added.
    assert len(success_jobs) == 2
    assert all(job.status == JobStatus.SUCCESSFUL for job in success_jobs)
    assert len(failing_jobs) == 1
    assert failing_jobs[0].status == JobStatus.FAILED

    await job_group.refresh_from_db()
    assert job_group.remaining_jobs == 0
    assert job_group.is_complete is True

    # Test failing JobGroup with callback
    background_jobs.reset()

    callback = CallbackJob(group_id=generate_uuid())
    async with JobsOutbox():
        job_group = await enqueue_job_group(job_definitions, callback)

    assert len(background_jobs.failed) > 0
    _, exception = background_jobs.failed[0]
    assert isinstance(exception, ValueError)

    # Verify callback was NOT executed due to failed job
    callback_jobs = await Job.filter(job_type=CallbackJob.job_type()).all()
    assert len(callback_jobs) == 0

    await job_group.refresh_from_db()
    assert job_group.is_complete is True
    assert job_group.remaining_jobs == 0

    # Teardown - reset background jobs
    background_jobs.reset()


@pytest.mark.asyncio
async def test_bulk_insert_by_unique():
    class UniqueTestJob(JobDefinition):
        unique: bool = True
        value: str

        async def perform(self):
            return f"Processed {self.value}"

    class NonUniqueTestJob(JobDefinition):
        unique: bool = False
        value: str

        async def perform(self):
            return f"Processed {self.value}"

    # Test bulk insert with all new jobs
    job_definitions = [
        UniqueTestJob(value="job1"),
        UniqueTestJob(value="job2"),
        NonUniqueTestJob(value="job3"),
    ]

    all_jobs, new_jobs = await Job.bulk_insert_by_unique(job_definitions)

    assert len(all_jobs) == 3
    assert len(new_jobs) == 3

    # Check actual job types
    job_types = [job.job_type for job in all_jobs]
    assert "unique_test" in job_types
    assert "non_unique_test" in job_types
    assert await Job.all().count() == 3

    # Test bulk insert with existing unique job - should not create duplicate
    existing_unique = UniqueTestJob(value="job1")
    new_unique = UniqueTestJob(value="job4")
    duplicate_non_unique = NonUniqueTestJob(value="job3")  # Non-unique allows duplicates

    job_definitions = [existing_unique, new_unique, duplicate_non_unique]
    all_jobs, new_jobs = await Job.bulk_insert_by_unique(job_definitions)

    assert len(all_jobs) == 3  # existing unique + new unique + duplicate non-unique
    assert len(new_jobs) == 2  # new unique + duplicate non-unique
    assert await Job.all().count() == 5  # 3 original + 2 new

    # Verify existing unique job was returned, not recreated
    existing_job = next(job for job in all_jobs if job.job_details["value"] == "job1")
    assert existing_job.job_type == "unique_test"

    # Test bulk insert with completed unique job - should create new one
    completed_job = await Job.by_job_definition(existing_unique).first()
    completed_job.completed_at = datetime.now(UTC)
    await completed_job.save()

    job_definitions = [existing_unique]  # Same definition as completed job
    all_jobs, new_jobs = await Job.bulk_insert_by_unique(job_definitions)

    assert len(all_jobs) == 1
    assert len(new_jobs) == 1
    assert all_jobs[0].id != completed_job.id  # New job created
    assert await Job.all().count() == 6  # 5 previous + 1 new

    # Test bulk insert with None group_id (no group)
    job_definitions = [UniqueTestJob(value="grouped1"), UniqueTestJob(value="grouped2")]
    all_jobs, new_jobs = await Job.bulk_insert_by_unique(job_definitions, group_id=None)

    assert len(all_jobs) == 2
    assert len(new_jobs) == 2
    assert all(job.group_id is None for job in all_jobs)
    assert await Job.all().count() == 8  # 6 previous + 2 new

    # Test empty job_definitions list
    all_jobs, new_jobs = await Job.bulk_insert_by_unique([])
    assert len(all_jobs) == 0
    assert len(new_jobs) == 0
    assert await Job.all().count() == 8  # No change


@pytest.mark.asyncio
async def test_bulk_enqueue_jobs(background_jobs: InlineJobs):
    class BulkTestJob(JobDefinition):
        unique: bool = True
        value: str

        async def perform(self):
            return f"Processed {self.value}"

    # Test bulk enqueue with JobsOutbox context - jobs should be executed
    job_definitions = [
        BulkTestJob(value="job1"),
        BulkTestJob(value="job2"),
    ]

    async with JobsOutbox():
        jobs = await bulk_enqueue_jobs(job_definitions)

    assert len(jobs) == 2
    assert await Job.all().count() == 2

    # Jobs should be executed and successful
    assert all(job.status == JobStatus.SUCCESSFUL for job in jobs)

    # Test with completed unique job - should create new job since original is completed
    completed_job_def = BulkTestJob(value="job1")  # Same as first job (which is completed)
    new_job = BulkTestJob(value="job3")

    async with JobsOutbox():
        jobs = await bulk_enqueue_jobs([completed_job_def, new_job])

    assert len(jobs) == 2  # new job1 + new job3
    assert await Job.all().count() == 4  # 2 original + 2 new

    # Verify both jobs were newly created and executed (since original job1 was completed)
    job1_from_result = next(job for job in jobs if job.job_details["value"] == "job1")
    job3_from_result = next(job for job in jobs if job.job_details["value"] == "job3")
    assert job1_from_result.status == JobStatus.SUCCESSFUL  # Newly created and executed
    assert job3_from_result.status == JobStatus.SUCCESSFUL  # Newly created and executed

    # Test with running unique job - should return existing job without creating new one
    running_job = await Job.create_by_job_definition(BulkTestJob(value="running_job"))
    assert running_job.status == JobStatus.ENQUEUED  # Not completed

    jobs = await bulk_enqueue_jobs([BulkTestJob(value="running_job"), BulkTestJob(value="new_job")])

    assert len(jobs) == 2  # existing running + new job
    assert await Job.all().count() == 6  # 4 previous + 1 running + 1 new

    # Verify existing running job was returned (not duplicated) and new job was created
    running_from_result = next(job for job in jobs if job.job_details["value"] == "running_job")
    new_from_result = next(job for job in jobs if job.job_details["value"] == "new_job")
    assert running_from_result.id == running_job.id  # Same job instance
    assert running_from_result.status == JobStatus.ENQUEUED  # Still not executed
    assert new_from_result.status == JobStatus.ENQUEUED  # Created but not executed (no JobsOutbox)

    # Test bulk enqueue without JobsOutbox context - jobs created but not executed
    jobs = await bulk_enqueue_jobs([BulkTestJob(value="not_executed")])
    assert len(jobs) == 1
    assert jobs[0].status == JobStatus.ENQUEUED  # Not executed
    assert await Job.all().count() == 7  # 6 previous + 1 new

    # Test empty list
    async with JobsOutbox():
        jobs = await bulk_enqueue_jobs([])
    assert len(jobs) == 0
    assert await Job.all().count() == 7  # No change
