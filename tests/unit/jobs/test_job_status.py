from datetime import UTC, datetime, timedelta

from config.enums import JobStatus
from config.settings import settings
from infra.jobs import Job


def test_job_status():
    # TERMINATED status
    job = Job()
    job.terminated_at = datetime.now(UTC)
    assert job.status == JobStatus.TERMINATED
    assert job.is_completed_or_dead is True

    # SUCCESSFUL status
    job = Job()
    job.completed_at = datetime.now(UTC)
    assert job.status == JobStatus.SUCCESSFUL
    assert job.is_completed_or_dead is True

    # FAILED status
    job = Job()
    job.error = "Something went wrong"
    assert job.status == JobStatus.FAILED
    assert job.is_completed_or_dead is False

    # STARTED status
    job = Job()
    job.started_at = datetime.now(UTC)
    assert job.status == JobStatus.STARTED
    assert job.is_completed_or_dead is False

    # SCHEDULED status
    job = Job()
    job.perform_at = datetime.now(UTC) + timedelta(hours=settings.dead_job_interval_hours - 1)
    assert job.status == JobStatus.SCHEDULED
    assert job.is_completed_or_dead is False

    # DEAD status
    job = Job()
    job.created_at = datetime.now(UTC) - timedelta(hours=settings.dead_job_interval_hours + 1)
    assert job.status == JobStatus.DEAD
    assert job.is_completed_or_dead is True

    # ENQUEUED status
    job = Job()
    job.created_at = datetime.now(UTC)
    assert job.status == JobStatus.ENQUEUED
    assert job.is_completed_or_dead is False

    # Completed jobs are not dead even if old
    job = Job()
    job.created_at = datetime.now(UTC) - timedelta(hours=settings.dead_job_interval_hours + 1)
    job.completed_at = datetime.now(UTC)
    assert job.status == JobStatus.SUCCESSFUL
    assert job.is_completed_or_dead is True

    # Terminated jobs are not dead even if old
    job = Job()
    job.created_at = datetime.now(UTC) - timedelta(hours=settings.dead_job_interval_hours + 1)
    job.terminated_at = datetime.now(UTC)
    assert job.status == JobStatus.TERMINATED
    assert job.is_completed_or_dead is True
