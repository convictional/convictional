from uuid import uuid4 as generate_uuid

import pytest
from fastapi import status

from app.jobs.mailers import SendFeedbackEmailJob
from app.models.collaboration.workspace import Attachment
from config import settings
from infra.email import FakeDelivery
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient


@pytest.mark.asyncio
async def test_api_feedback_create_happy_path(
    client: AppClient,
    email_delivery: FakeDelivery,
    background_jobs: InlineJobs,
    monkeypatch: pytest.MonkeyPatch,
):
    # The notification email's "Feedback Details" link only renders when settings.has_sentry
    # is truthy; set the Sentry settings so we can assert it appears — and that the removed
    # Session Replay link does not.
    monkeypatch.setattr(settings, "sentry_org", "convictional")
    monkeypatch.setattr(settings, "sentry_project", "convictional")
    monkeypatch.setattr(settings, "sentry_project_id", "4506791569522688")
    monkeypatch.setattr(settings, "feedback_email", "feedback@example.com")

    user = await client.get_default_user()
    claim_id = str(generate_uuid())

    csv_bytes = b"Title,Year\nThe Shawshank Redemption,1994\n"
    upload_response = await client.post(
        "/api/workspaces/attachments",
        files={"files": ("feedback.csv", csv_bytes, "text/csv")},
        data={"claim_id": claim_id},
    )
    assert upload_response.status_code == status.HTTP_201_CREATED

    attachment = await Attachment.all().first()
    assert attachment is not None
    assert attachment.claim_id is not None

    response = await client.post(
        "/api/feedback",
        json={
            "description": "This is **feedback**",
            "current_url": "https://example.com/page",
            "sentry_event_id": "9ec79c33ec9942ab8353589fcb2e04dc",
            "attachment_claim_id": claim_id,
        },
    )

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.text == ""

    assert background_jobs.has_completed_job(SendFeedbackEmailJob, count=1)
    job = background_jobs.find_completed_job_by_type(SendFeedbackEmailJob)
    assert job is not None
    assert job.job_details["url"] == "https://example.com/page"
    assert job.job_details["user_email"] == user.email
    assert job.job_details["description"] == "This is **feedback**"
    assert job.job_details["sentry_event_id"] == "9ec79c33ec9942ab8353589fcb2e04dc"

    await attachment.refresh_from_db()
    assert attachment.claim_id is None
    assert str(attachment.id) in [str(aid) for aid in job.job_details["attachment_ids"]]

    assert len(email_delivery.messages) == 1
    message = email_delivery.messages[0]
    assert message.to == settings.feedback_email
    # Sentry User Feedback stays; Session Replay recording was removed entirely.
    body = message.text or ""
    assert "Feedback Details" in body
    assert "Session Replay" not in body


@pytest.mark.asyncio
async def test_api_feedback_secure_path(client: AppClient, background_jobs: InlineJobs):
    await client.get_default_user()

    for description in (None, "", "   "):
        body = {"current_url": "https://example.com"}
        if description is not None:
            body["description"] = description
        response = await client.post("/api/feedback", json=body)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    response = await client.post(
        "/api/feedback",
        json={
            "description": "feedback",
            "current_url": "https://example.com",
            "sentry_event_id": "also-bad",
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    job = background_jobs.find_completed_job_by_type(SendFeedbackEmailJob)
    assert job is not None
    assert job.job_details["sentry_event_id"] is None

    with client.logged_out():
        response = await client.post(
            "/api/feedback",
            json={"description": "feedback", "current_url": "https://example.com"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Authentication required"}
