import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_research_question


@pytest.mark.asyncio
async def test_research_progress_show_returns_pending_questions(client: AppClient):
    user = await client.get_default_user()
    question = await create_research_question(creator_id=user.id, title="Q1")

    response = await client.get("/api/research_progress")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert len(body["pending_research_questions"]) == 1
    assert body["pending_research_questions"][0]["id"] == str(question.id)
    assert body["pending_research_questions"][0]["title"] == "Q1"


@pytest.mark.asyncio
async def test_research_progress_show_returns_empty_when_no_pending(client: AppClient):
    response = await client.get("/api/research_progress")
    body = response.json()
    assert body["pending_research_questions"] == []


@pytest.mark.asyncio
async def test_research_progress_show_falls_back_to_untitled(client: AppClient):
    user = await client.get_default_user()
    await create_research_question(creator_id=user.id, title=None)

    response = await client.get("/api/research_progress")
    body = response.json()
    assert body["pending_research_questions"][0]["title"] == "Untitled"
