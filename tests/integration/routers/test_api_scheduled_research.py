import pytest
from fastapi import status

from app.models.commands import ScheduledResearch
from infra.jobs import InlineJobs, Job
from tests.helpers.app import AppClient
from tests.helpers.factories import create_research_question, create_scheduled_research, create_user


@pytest.mark.asyncio
async def test_index_returns_paginated_list_for_current_user_only(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()
    other = await create_user()

    mine = await create_scheduled_research(creator_id=user.id, organization_id=user.organization_id)
    await create_scheduled_research(creator_id=other.id, organization_id=other.organization_id)

    response = await client.get("/api/scheduled_research")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    ids = [row["id"] for row in data["scheduled_researches"]]
    assert str(mine.id) in ids
    assert len(ids) == 1

    assert "next_cursor" in data
    assert "has_more" in data


@pytest.mark.asyncio
async def test_create_rejects_invalid_schedule(client: AppClient, background_jobs: InlineJobs):
    await client.get_default_user()

    response = await client.post(
        "/api/scheduled_research",
        json={
            "prompt": "anything",
            "frequency": "weekly",
            "hour": 9,
            "day_of_week": None,  # weekly requires day_of_week
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_create_enqueues_prepare_only_and_does_not_fire_first_delivery(
    client: AppClient, background_jobs: InlineJobs
):
    # Creating a schedule should set up future deliveries on cadence — it must NOT enqueue an
    # immediate ScheduledResearchJob, which previously confused users by emailing a report
    # outside the schedule they just chose.
    await client.get_default_user()

    response = await client.post(
        "/api/scheduled_research",
        json={"prompt": "Daily standup digest", "frequency": "daily", "hour": 9},
    )
    assert response.status_code == status.HTTP_201_CREATED

    assert await Job.filter(job_type="prepare_scheduled_research").count() == 1
    assert await Job.filter(job_type="scheduled_research").count() == 0


@pytest.mark.asyncio
async def test_show_and_cross_user_404(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()
    mine = await create_scheduled_research(creator_id=user.id, organization_id=user.organization_id)

    other = await create_user()
    theirs = await create_scheduled_research(creator_id=other.id, organization_id=other.organization_id)

    resp_ok = await client.get(f"/api/scheduled_research/{mine.id}")
    assert resp_ok.status_code == status.HTTP_200_OK

    resp_404 = await client.get(f"/api/scheduled_research/{theirs.id}")
    assert resp_404.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_changes_fields_and_reenqueues_prepare_when_prompt_changes(
    client: AppClient, background_jobs: InlineJobs
):
    user = await client.get_default_user()
    schedule = await create_scheduled_research(
        creator_id=user.id,
        organization_id=user.organization_id,
        prompt="Old prompt",
    )

    response = await client.patch(
        f"/api/scheduled_research/{schedule.id}",
        json={"prompt": "New prompt", "hour": 15},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["prompt"] == "New prompt"
    assert data["hour"] == 15

    refreshed = await ScheduledResearch.get(id=schedule.id)
    assert refreshed.prompt == "New prompt"
    assert refreshed.hour == 15

    # Prompt change enqueued a prepare job
    prepare_jobs = await Job.filter(job_type="prepare_scheduled_research").count()
    assert prepare_jobs == 1

    # Same-prompt PATCH doesn't enqueue another prepare
    response = await client.patch(
        f"/api/scheduled_research/{schedule.id}",
        json={"hour": 10},
    )
    assert response.status_code == status.HTTP_200_OK
    assert await Job.filter(job_type="prepare_scheduled_research").count() == 1


@pytest.mark.asyncio
async def test_delete_soft_deletes(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()
    schedule = await create_scheduled_research(creator_id=user.id, organization_id=user.organization_id)

    response = await client.delete(f"/api/scheduled_research/{schedule.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Soft-deleted — default manager filters it out
    assert await ScheduledResearch.filter(id=schedule.id).count() == 0


@pytest.mark.asyncio
async def test_preview_initiation_returns_preview_id(client: AppClient, background_jobs: InlineJobs):
    await client.get_default_user()

    response = await client.post(
        "/api/scheduled_research/preview",
        json={"prompt": "Weekly round-up of SaaS funding, as bullets"},
    )
    assert response.status_code == status.HTTP_202_ACCEPTED
    data = response.json()
    # The plain preview_id lets the React client subscribe to the
    # scheduled_research_preview topic by name (no signed token needed).
    assert data["preview_id"]
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_prefill_from_own_research_question(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()
    question = await create_research_question(creator_id=user.id)

    response = await client.get(f"/api/scheduled_research/prefill?from_research_question={question.id}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["prompt"] == question.body


@pytest.mark.asyncio
async def test_prefill_404_across_users(client: AppClient, background_jobs: InlineJobs):
    await client.get_default_user()
    other = await create_user()
    question = await create_research_question(creator_id=other.id)

    response = await client.get(f"/api/scheduled_research/prefill?from_research_question={question.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
