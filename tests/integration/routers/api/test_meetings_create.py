import pytest
from fastapi import status

from app.jobs.meetings import MeetingProcessingCompleteCallbackJob, ProcessTranscriptJob
from app.models.workspaces.meetings import Meeting, MeetingJob
from infra.jobs import InlineJobs
from integrations.recall_ai.jobs import ScheduleRecallAIBotJob
from tests.helpers.app import AppClient


@pytest.fixture(autouse=True)
def stub_external_jobs(monkeypatch: pytest.MonkeyPatch):
    # Creating a meeting triggers several jobs that call third-party APIs:
    # ProcessTranscriptJob → Claude (titling) → OpenAI (embeddings via the
    # content-indexing fan-out), and ScheduleRecallAIBotJob → Recall.ai.
    # These tests verify the API contract (status codes, persisted state,
    # MeetingJob row); the third-party fan-out is covered by the cassette-
    # backed HTMX tests in tests/integration/routers/test_meetings.py.
    async def noop(self):
        pass

    monkeypatch.setattr(ProcessTranscriptJob, "perform", noop)
    monkeypatch.setattr(MeetingProcessingCompleteCallbackJob, "perform", noop)
    monkeypatch.setattr(ScheduleRecallAIBotJob, "perform", noop)


@pytest.mark.asyncio
async def test_create_from_transcript_returns_201_and_enqueues_processing(
    client: AppClient, background_jobs: InlineJobs
):
    response = await client.post(
        "/api/meetings",
        json={"type": "transcript", "transcript": "Speaker A: hi\nSpeaker B: hello"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["title"].startswith("Meeting at ")
    assert data["scheduled_at"] is not None

    meeting = await Meeting.get(id=data["id"])
    user = await client.get_default_user()
    assert meeting.organization_id == user.organization_id
    assert meeting.creator_id == user.id
    assert meeting.transcript == "Speaker A: hi\nSpeaker B: hello"
    assert meeting.manually_created_at is not None

    assert any(isinstance(job.job_definition, ProcessTranscriptJob) for job in background_jobs.completed)
    assert await MeetingJob.exists(meeting_id=meeting.id)


@pytest.mark.asyncio
async def test_create_from_transcript_respects_explicit_title(client: AppClient):
    response = await client.post(
        "/api/meetings",
        json={"type": "transcript", "transcript": "x", "title": "Quarterly review"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["title"] == "Quarterly review"


@pytest.mark.parametrize(
    "url",
    [
        "https://zoom.us/j/1234567890",
        "https://meet.google.com/abc-defg-hij",
        "https://teams.microsoft.com/meet/1234567890",
    ],
)
@pytest.mark.asyncio
async def test_create_from_url_accepts_supported_providers(client: AppClient, url: str):
    response = await client.post("/api/meetings", json={"type": "url", "conferencing_url": url})
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["title"] == f"Meeting at {url}"
    meeting = await Meeting.get(id=data["id"])
    assert meeting.conferencing_url == url


@pytest.mark.asyncio
async def test_create_from_url_rejects_unsupported_provider(client: AppClient):
    response = await client.post(
        "/api/meetings",
        json={"type": "url", "conferencing_url": "https://example.com/meeting"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    errors = response.json()["detail"]
    assert any("conferencing_url" in err["loc"] for err in errors)
    assert any("Zoom, Google Meet, or Microsoft Teams" in err["msg"] for err in errors)


@pytest.mark.asyncio
async def test_create_rejects_unknown_type(client: AppClient):
    response = await client.post("/api/meetings", json={"type": "garbage", "transcript": "x"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    response = await client.post("/api/meetings", json={"transcript": "x"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
