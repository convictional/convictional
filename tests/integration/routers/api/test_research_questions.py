import pytest
from fastapi import status

from app.jobs.mailers import SendResearchQuestionEmailJob
from app.jobs.research import GenerateResearchQuestionTitleJob, ResearchJob, ResearchQuestionCompleteJob
from app.models.collaboration.content import Research
from app.models.commands import ResearchQuestion
from config.enums import ResearchSource
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient


@pytest.mark.asyncio
@pytest.mark.vcr
async def test_api_research_question_create(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()

    response = await client.post("/api/research_questions", json={"body": "test research topic"})
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["body"] == "test research topic"
    assert data["id"]
    assert "created_at" in data
    assert "title" in data

    question = await ResearchQuestion.filter(creator_id=user.id).first()
    assert question is not None
    assert question.body == "test research topic"
    assert question.sources == [ResearchSource.INTERNAL]
    assert question.research_id is not None

    research = await Research.filter(id=question.research_id).first()
    assert research is not None
    assert research.topic == "test research topic"

    assert background_jobs.has_completed_job(ResearchJob, count=1)
    assert background_jobs.has_completed_job(GenerateResearchQuestionTitleJob, count=1)
    assert background_jobs.has_completed_job(ResearchQuestionCompleteJob, count=1)
    assert background_jobs.has_completed_job(SendResearchQuestionEmailJob, count=1)
    assert len(background_jobs.failed) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["", "   ", "\n\t "])
async def test_api_research_question_create_rejects_blank_body(client: AppClient, body: str):
    response = await client.post("/api/research_questions", json={"body": body})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert isinstance(response.json()["detail"], list)


@pytest.mark.asyncio
async def test_api_research_question_create_requires_auth(client: AppClient):
    with client.logged_out():
        response = await client.post("/api/research_questions", json={"body": "anything"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.json() == {"detail": "Authentication required"}
