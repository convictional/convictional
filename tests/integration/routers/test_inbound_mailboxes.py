import hmac
import time
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.jobs.mailers import SendResearchQuestionEmailJob
from app.jobs.research import ResearchJob, ResearchQuestionCompleteJob
from app.mailers.research import ResearchQuestionMailer
from app.main import app
from app.models.collaboration.content import Research, ResearchIteration, ResearchQuery
from app.models.commands import ResearchQuestion
from app.routers.inbound_mailboxes import handle_research_email
from config import settings
from config.enums import ResearchSource
from infra.email import FakeDelivery, InboundEmail
from infra.jobs import InlineJobs, JobsOutbox
from tests.helpers.app import BASE_URL, AppClient
from tests.helpers.factories import create_content, create_job, create_user

TEST_MAILGUN_SIGNING_KEY = "test-mailgun-signing-key"
RESEARCH_ADDRESS = "research@example.com"


def _signed_mailgun_form(extra: dict[str, str]) -> dict[str, str]:
    timestamp = str(int(time.time()))
    token = "test-token"
    signature = hmac.new(
        key=TEST_MAILGUN_SIGNING_KEY.encode(),
        msg=f"{timestamp}{token}".encode(),
        digestmod="sha256",
    ).hexdigest()
    return {**extra, "timestamp": timestamp, "token": token, "signature": signature}


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_handle_research_email_creates_research_question(
    background_jobs: InlineJobs, email_delivery: FakeDelivery
):
    settings.research_email_from = RESEARCH_ADDRESS
    user = await create_user()
    await user.fetch_related("organization")

    email = InboundEmail(
        sender=f"Test User <{user.email}>",
        to=[RESEARCH_ADDRESS, "colleague@example.com"],
        cc=["manager@example.com", "Manager Two <manager2@example.com>"],
        subject="Market analysis request",
        body_plain="Please research competitor pricing strategies in Q4 2024.",
        stripped_text="Please research competitor pricing strategies in Q4 2024.",
        message_headers={"Message-ID": "<abc123@example.com>"},
    )

    async with JobsOutbox():
        await handle_research_email(email)

    question = await ResearchQuestion.filter(creator_id=user.id).first()
    assert question is not None
    assert "Market analysis request" in question.body
    assert "competitor pricing strategies" in question.body
    assert question.research_id is not None
    assert question.in_reply_to_message_id == "<abc123@example.com>"
    assert question.in_reply_to_subject == "Market analysis request"
    assert set(question.cc_recipients) == {"colleague@example.com", "manager@example.com", "manager2@example.com"}

    assert background_jobs.has_completed_job(ResearchJob, count=1)
    assert background_jobs.has_completed_job(ResearchQuestionCompleteJob, count=1)
    assert background_jobs.has_completed_job(SendResearchQuestionEmailJob, count=1)

    assert len(email_delivery.messages) == 1
    sent_email = email_delivery.messages[0]
    assert sent_email.to == user.email
    assert sent_email.cc == "colleague@example.com, manager@example.com, manager2@example.com"
    assert sent_email.subject == "Re: Market analysis request"

    header_dict = {h["name"]: h["value"] for h in sent_email.headers}
    assert header_dict["In-Reply-To"] == "<abc123@example.com>"
    assert header_dict["References"] == "<abc123@example.com>"


@pytest.mark.asyncio
async def test_handle_research_email_ignores_unknown_sender():
    email = InboundEmail(
        sender="Unknown Person <unknown@example.com>",
        to=[RESEARCH_ADDRESS],
        subject="Research request",
        body_plain="Some research topic",
        stripped_text="Some research topic",
    )

    await handle_research_email(email)

    questions = await ResearchQuestion.filter(body__contains="Some research topic").all()
    assert len(questions) == 0


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_handle_research_email_stores_replying_to_message_id(
    background_jobs: InlineJobs, email_delivery: FakeDelivery
):
    user = await create_user()
    await user.fetch_related("organization")

    reply_email = InboundEmail(
        sender=f"Test User <{user.email}>",
        to=[RESEARCH_ADDRESS],
        subject="Re: Follow-up question",
        body_plain="What about competitor Y?",
        stripped_text="What about competitor Y?",
        message_headers={
            "Message-ID": "<reply456@example.com>",
            "In-Reply-To": "<original-response@convictional.com>",
        },
    )

    async with JobsOutbox():
        await handle_research_email(reply_email)

    question = await ResearchQuestion.filter(creator_id=user.id).first()
    assert question is not None
    assert question.in_reply_to_message_id == "<reply456@example.com>"
    assert question.replying_to_message_id == "<original-response@convictional.com>"
    assert "competitor Y" in question.body


@pytest.mark.asyncio
async def test_get_thread_context_builds_chronological_chain():
    user = await create_user()
    other_user = await create_user()

    first = await ResearchQuestion.create(
        body="First question",
        creator_id=user.id,
        response="First response.",
        response_completed_at=datetime.now(UTC),
        response_message_id="<response-1@convictional.com>",
    )

    # Incomplete question (no response_completed_at) - should be excluded
    await ResearchQuestion.create(
        body="Incomplete question",
        creator_id=user.id,
        response_message_id="<incomplete@convictional.com>",
    )

    second = await ResearchQuestion.create(
        body="Second question",
        creator_id=user.id,
        response="Second response.",
        response_completed_at=datetime.now(UTC),
        replying_to_message_id="<response-1@convictional.com>",
        response_message_id="<response-2@convictional.com>",
    )

    # Other user's question with same message_id - should be excluded (scoped to creator)
    await ResearchQuestion.create(
        body="Other user's question",
        creator_id=other_user.id,
        response="Other response.",
        response_completed_at=datetime.now(UTC),
        response_message_id="<response-2@convictional.com>",
    )

    third = await ResearchQuestion.create(
        body="Third question",
        creator_id=user.id,
        replying_to_message_id="<response-2@convictional.com>",
    )

    thread_context = await third.get_thread_context()

    assert len(thread_context) == 2
    assert thread_context[0].id == first.id
    assert thread_context[1].id == second.id


@pytest.mark.asyncio
async def test_research_mailer_collects_content_from_thread_context():
    """Test that ResearchQuestionMailer includes content from prior research in thread context."""
    user = await create_user()
    await user.fetch_related("organization")

    first_content = await create_content(
        title="First Research Content",
        organization_id=user.organization_id,
    )
    second_content = await create_content(
        title="Second Research Content",
        organization_id=user.organization_id,
    )

    first_research = await Research.create(
        topic="First topic",
        sources=[ResearchSource.INTERNAL],
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    first_job = await create_job(ResearchJob(research_id=first_research.id))
    first_iteration = await ResearchIteration.create(
        research_id=first_research.id,
        title="First iteration",
        directions="First directions",
        queries_count=1,
        job_id=first_job.id,
    )
    await ResearchQuery.create(
        iteration_id=first_iteration.id,
        research_id=first_research.id,
        title="First query",
        goals="First goals",
        source=ResearchSource.INTERNAL,
        content_result_ids=[first_content.id],
        completed_at=datetime.now(UTC),
    )

    await ResearchQuestion.create(
        body="First question",
        creator_id=user.id,
        research_id=first_research.id,
        response=f"First response with citation [^content:{first_content.id}]",
        response_completed_at=datetime.now(UTC),
        response_message_id="<first-response@convictional.com>",
    )

    second_research = await Research.create(
        topic="Second topic",
        sources=[ResearchSource.INTERNAL],
        creator_id=user.id,
        organization_id=user.organization_id,
    )
    second_job = await create_job(ResearchJob(research_id=second_research.id))
    second_iteration = await ResearchIteration.create(
        research_id=second_research.id,
        title="Second iteration",
        directions="Second directions",
        queries_count=1,
        job_id=second_job.id,
    )
    await ResearchQuery.create(
        iteration_id=second_iteration.id,
        research_id=second_research.id,
        title="Second query",
        goals="Second goals",
        source=ResearchSource.INTERNAL,
        content_result_ids=[second_content.id],
        completed_at=datetime.now(UTC),
    )

    second_question = await ResearchQuestion.create(
        body="Follow-up question",
        creator_id=user.id,
        research_id=second_research.id,
        response=f"Second response with citation [^content:{second_content.id}]",
        response_completed_at=datetime.now(UTC),
        replying_to_message_id="<first-response@convictional.com>",
    )
    await second_question.fetch_related("research__iterations__queries", "creator")

    mailer = ResearchQuestionMailer(second_question)
    results_by_id = await mailer._collect_all_results_by_id()

    assert first_content.id in results_by_id, "Content from prior research should be included"
    assert second_content.id in results_by_id, "Content from current research should be included"
    assert results_by_id[first_content.id].title == "First Research Content"
    assert results_by_id[second_content.id].title == "Second Research Content"


@pytest.mark.asyncio
async def test_mailgun_webhook_exception_propagation(client: AppClient, monkeypatch):
    settings.mailgun_domain = "example.com"
    settings.mailgun_api_key = SecretStr("test-api-key")
    settings.mailgun_webhook_signing_key = SecretStr(TEST_MAILGUN_SIGNING_KEY)
    settings.research_email_from = RESEARCH_ADDRESS

    async def mock_create(*args, **kwargs):
        raise RuntimeError("Database connection lost")

    monkeypatch.setattr(ResearchQuestion, "create", mock_create)

    user = await client.get_default_user()
    form_data = _signed_mailgun_form(
        {
            "from": f"Test User <{user.email}>",
            "To": RESEARCH_ADDRESS,
            "subject": "Failing Request",
            "body-plain": "This should fail and bubble up",
            "stripped-text": "This should fail and bubble up",
        }
    )

    # AppClient re-raises 5xx client-side; this one lets FastAPI's handler convert to 500.
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url=BASE_URL,
    ) as no_raise_client:
        response = await no_raise_client.post("/webhooks/email/", data=form_data)

    assert response.status_code == 500
