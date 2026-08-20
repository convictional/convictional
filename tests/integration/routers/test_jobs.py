import pytest
import pytest_asyncio

from app.jobs.maintenance import CacheCleanupJob, IndexSearchJob
from config.enums import JobQueue, JobStatus
from infra.jobs import InlineJobs, Job, JobDefinition, build_jobs_router
from tests.helpers.app import AppClient


class FailingTestJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    retry_count = 3

    async def perform(self):
        raise Exception("Test job intentionally fails")


@pytest_asyncio.fixture
async def jobs_client(client: AppClient):
    jobs_router = build_jobs_router()
    client._app.include_router(jobs_router, prefix="/jobs")
    return client


@pytest.mark.asyncio
async def test_job_retry_count_behavior(jobs_client: AppClient):
    # Ensure default retry count is respected and jobs terminate appropriately
    job_with_default_retries = await Job.create_by_job_definition(IndexSearchJob())

    # Should be final retry
    cloud_task_retry_count = 99
    headers = {"x-cloudtasks-taskretrycount": str(cloud_task_retry_count)}

    assert job_with_default_retries.job_definition.is_final_retry(cloud_task_retry_count)
    assert not job_with_default_retries.job_definition.has_exhausted_retries(cloud_task_retry_count)

    job_data = {"id": str(job_with_default_retries.id), "type": IndexSearchJob.job_type()}
    response = await jobs_client.post(f"/jobs/{IndexSearchJob.job_type()}", json=job_data, headers=headers)
    assert response.status_code == 200

    await job_with_default_retries.refresh_from_db()
    assert job_with_default_retries.status == JobStatus.SUCCESSFUL

    job_with_default_retries = await Job.create_by_job_definition(IndexSearchJob())

    # Should have exhausted retries
    job_with_default_retries = await Job.create_by_job_definition(IndexSearchJob())
    cloud_task_retry_count = 100
    headers = {"x-cloudtasks-taskretrycount": str(cloud_task_retry_count)}

    assert not job_with_default_retries.job_definition.is_final_retry(cloud_task_retry_count)
    assert job_with_default_retries.job_definition.has_exhausted_retries(cloud_task_retry_count)

    job_data = {"id": str(job_with_default_retries.id), "type": IndexSearchJob.job_type()}
    response = await jobs_client.post(f"/jobs/{IndexSearchJob.job_type()}", json=job_data, headers=headers)
    assert response.status_code == 200

    await job_with_default_retries.refresh_from_db()
    assert job_with_default_retries.status == JobStatus.TERMINATED

    # Ensure zero retry count is respected and jobs terminate appropriately
    job_with_no_retries = await Job.create_by_job_definition(CacheCleanupJob())

    # Should be final (and only) try
    cloud_task_retry_count = 0
    headers = {"x-cloudtasks-taskretrycount": str(cloud_task_retry_count)}

    assert job_with_no_retries.job_definition.is_final_retry(cloud_task_retry_count)
    assert not job_with_no_retries.job_definition.has_exhausted_retries(cloud_task_retry_count)

    job_data = {"id": str(job_with_no_retries.id), "type": CacheCleanupJob.job_type()}
    response = await jobs_client.post(f"/jobs/{CacheCleanupJob.job_type()}", json=job_data, headers=headers)
    assert response.status_code == 200

    await job_with_no_retries.refresh_from_db()
    assert job_with_no_retries.status == JobStatus.SUCCESSFUL

    # Should have exhausted retries
    job_with_no_retries = await Job.create_by_job_definition(CacheCleanupJob())
    cloud_task_retry_count = 1
    headers = {"x-cloudtasks-taskretrycount": str(cloud_task_retry_count)}

    assert not job_with_no_retries.job_definition.is_final_retry(cloud_task_retry_count)
    assert job_with_no_retries.job_definition.has_exhausted_retries(cloud_task_retry_count)

    job_data = {"id": str(job_with_no_retries.id), "type": CacheCleanupJob.job_type()}
    response = await jobs_client.post(f"/jobs/{CacheCleanupJob.job_type()}", json=job_data, headers=headers)
    assert response.status_code == 200

    await job_with_no_retries.refresh_from_db()
    assert job_with_no_retries.status == JobStatus.TERMINATED


@pytest.mark.asyncio
async def test_recurring_job_route(jobs_client: AppClient, background_jobs: InlineJobs):
    # Test that the recurring job endpoint creates and enqueues a job
    response = await jobs_client.post(f"/jobs/recurring/{CacheCleanupJob.job_type()}")
    assert response.status_code == 200

    jobs = await Job.filter(job_type=CacheCleanupJob.job_type())
    assert jobs is not None
    assert len(jobs) == 1
    job = jobs[0]
    assert job.status == JobStatus.SUCCESSFUL  # Should be executed immediately with inline runner

    # Verify only one job was created and it completed successfully
    assert background_jobs.has_completed_job(CacheCleanupJob, count=1)
    assert len(background_jobs.failed) == 0  # No failures expected


@pytest.mark.asyncio
async def test_job_terminated_on_final_retry_exception(jobs_client: AppClient):
    # Create a job that will fail
    failing_job = await Job.create_by_job_definition(FailingTestJob())

    # Set retry count to final retry
    final_retry_count = 3
    headers = {"x-cloudtasks-taskretrycount": str(final_retry_count)}

    assert failing_job.job_definition.is_final_retry(final_retry_count)
    assert not failing_job.job_definition.has_exhausted_retries(final_retry_count)

    job_data = {"id": str(failing_job.id), "type": FailingTestJob.job_type()}
    response = await jobs_client.post(f"/jobs/{FailingTestJob.job_type()}", json=job_data, headers=headers)

    # Should return 200 OK to prevent Cloud Tasks from retrying
    assert response.status_code == 200

    await failing_job.refresh_from_db()
    # Job should be terminated due to exception on final retry
    assert failing_job.status == JobStatus.TERMINATED
