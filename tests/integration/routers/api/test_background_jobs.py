import pytest
import pytest_asyncio
from fastapi import status

from app.models.accounts import User
from config.enums import JobQueue
from infra.jobs import InlineJobs, JobDefinition
from tests.helpers.app import AppClient
from tests.helpers.factories import create_superuser


# Self-contained, harmless jobs so the inline runner doesn't perform real
# maintenance work. Defining a JobDefinition subclass auto-registers it in
# job_registry (see JobDefinition.__init_subclass__), mirroring test_jobs.py.
class NoopBackgroundTestJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS

    async def perform(self):
        pass


class RequiredArgBackgroundTestJob(JobDefinition):
    default_queue = JobQueue.MAINTENANCE
    count: int

    async def perform(self):
        pass


@pytest_asyncio.fixture
async def superuser() -> User:
    return await create_superuser()


@pytest.mark.asyncio
async def test_index_lists_job_types_for_superuser(client: AppClient, superuser: User):
    with client.current_user_as(superuser):
        response = await client.get("/api/background_job_types")

    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    # Envelope, not a bare array.
    assert "job_types" in body
    job_types = body["job_types"]
    assert isinstance(job_types, list)

    # Alphabetically sorted by job_type.
    keys = [entry["job_type"] for entry in job_types]
    assert keys == sorted(keys)

    by_type = {entry["job_type"]: entry for entry in job_types}
    noop = by_type[NoopBackgroundTestJob.job_type()]
    assert noop["name"] == "NoopBackgroundTestJob"
    assert isinstance(noop["args_schema"], dict)
    # The job's default queue is surfaced (it's a ClassVar, absent from args_schema).
    assert noop["queue"] == JobQueue.MISCELLANEOUS.value

    # The required argument surfaces in the schema so the client can build a template,
    # and the queue reflects this job's own default, not a shared constant.
    required_entry = by_type[RequiredArgBackgroundTestJob.job_type()]
    assert "count" in required_entry["args_schema"]["properties"]
    assert "count" in required_entry["args_schema"]["required"]
    assert required_entry["queue"] == JobQueue.MAINTENANCE.value


@pytest.mark.asyncio
async def test_create_enqueues_job_for_superuser(client: AppClient, superuser: User, background_jobs: InlineJobs):
    with client.current_user_as(superuser):
        response = await client.post(
            "/api/background_jobs",
            json={"job_type": NoopBackgroundTestJob.job_type(), "arguments": {}},
        )

    assert response.status_code == status.HTTP_202_ACCEPTED
    body = response.json()
    assert body["job_type"] == NoopBackgroundTestJob.job_type()
    assert body["job_id"]

    assert background_jobs.has_completed_job(NoopBackgroundTestJob, count=1)


@pytest.mark.asyncio
async def test_create_rejects_unknown_job_type(client: AppClient, superuser: User, background_jobs: InlineJobs):
    with client.current_user_as(superuser):
        response = await client.post(
            "/api/background_jobs",
            json={"job_type": "definitely_not_a_real_job", "arguments": {}},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # Same structured shape as an argument-validation failure: a list of
    # {loc, msg, ...} entries, with the error pointing at body.job_type.
    detail = response.json()["detail"]
    assert any("job_type" in entry["loc"] for entry in detail)
    assert not background_jobs.completed


@pytest.mark.asyncio
async def test_create_rejects_invalid_arguments(client: AppClient, superuser: User, background_jobs: InlineJobs):
    with client.current_user_as(superuser):
        # Missing the required `count` argument.
        response = await client.post(
            "/api/background_jobs",
            json={"job_type": RequiredArgBackgroundTestJob.job_type(), "arguments": {}},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    # Structured validation payload: a list of {loc, msg, ...} entries naming the field.
    detail = response.json()["detail"]
    assert any("count" in entry["loc"] for entry in detail)
    assert not background_jobs.completed


@pytest.mark.asyncio
async def test_endpoints_require_superuser(client: AppClient):
    # Default user (dev@example.com) is not a superuser.
    await client.get_default_user()
    get_response = await client.get("/api/background_job_types")
    post_response = await client.post(
        "/api/background_jobs",
        json={"job_type": NoopBackgroundTestJob.job_type(), "arguments": {}},
    )
    assert get_response.status_code == status.HTTP_403_FORBIDDEN
    assert post_response.status_code == status.HTTP_403_FORBIDDEN

    # Unauthenticated requests are forbidden too.
    with client.logged_out():
        logged_out_response = await client.get("/api/background_job_types")
    assert logged_out_response.status_code == status.HTTP_403_FORBIDDEN
