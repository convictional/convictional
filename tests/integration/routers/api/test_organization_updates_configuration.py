import pytest
from fastapi import status

from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_user


@pytest.mark.asyncio
async def test_updates_configuration_show_and_update(client: AppClient):
    user = await create_user(is_admin=True)
    client.current_user = user

    response = await client.get("/api/organization/updates_configuration")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert {"frequency", "hour", "day_of_week", "goal_update_question", "has_goals", "enabled"} == set(data)
    # No raw cron string is exposed, and an unconfigured schedule reports null (not faked defaults).
    assert "update_schedule" not in data
    assert data["frequency"] is None
    assert data["hour"] is None
    assert data["enabled"] is False

    # Set a weekly schedule.
    response = await client.patch(
        "/api/organization/updates_configuration",
        json={"frequency": "weekly", "hour": 10, "day_of_week": "5"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["frequency"] == "weekly"
    assert data["hour"] == 10
    assert data["day_of_week"] == "5"
    assert "update_schedule" not in data

    # The goal-update question can be set on its own, independent of the schedule.
    response = await client.patch(
        "/api/organization/updates_configuration",
        json={"goal_update_question": "How's progress?"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["goal_update_question"] == "How's progress?"

    # Clearing the question to "" is the supported "disable goal updates" path — it is
    # accepted (not rejected as blank) and flips enabled off.
    response = await client.patch("/api/organization/updates_configuration", json={"goal_update_question": ""})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["goal_update_question"] == ""
    assert data["enabled"] is False


@pytest.mark.asyncio
async def test_enabled_requires_schedule_question_and_goals(client: AppClient):
    # `enabled` drives the React island's Enabled/Disabled badge and is only true when a
    # schedule, a question, and an open goal all exist. Schedule + question alone (no goals)
    # stays disabled; adding an open goal flips it on.
    user = await create_user(is_admin=True)
    client.current_user = user

    response = await client.patch(
        "/api/organization/updates_configuration",
        json={"frequency": "weekly", "hour": 9, "day_of_week": "1", "goal_update_question": "How's it going?"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["enabled"] is False  # no open goals yet

    await create_goal(organization_id=user.organization_id, creator_id=user.id)

    response = await client.get("/api/organization/updates_configuration")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["has_goals"] is True
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_updates_configuration_validation(client: AppClient):
    user = await create_user(is_admin=True)
    client.current_user = user

    # Weekly schedule without a day_of_week is semantically invalid → 422.
    response = await client.patch(
        "/api/organization/updates_configuration",
        json={"frequency": "weekly", "hour": 10},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # frequency and hour must be set together — one alone can't rebuild the cron.
    response = await client.patch("/api/organization/updates_configuration", json={"frequency": "monthly"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Bodies that can't produce a change are rejected, not silently 200'd: an empty body,
    # day_of_week alone (can't rebuild the cron without frequency+hour), and a null question.
    assert (
        await client.patch("/api/organization/updates_configuration", json={})
    ).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (
        await client.patch("/api/organization/updates_configuration", json={"day_of_week": "5"})
    ).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert (
        await client.patch("/api/organization/updates_configuration", json={"goal_update_question": None})
    ).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Monthly needs no day_of_week, and reports day_of_week as null (not applicable).
    response = await client.patch(
        "/api/organization/updates_configuration",
        json={"frequency": "monthly", "hour": 8},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["frequency"] == "monthly"
    assert data["hour"] == 8
    assert data["day_of_week"] is None


@pytest.mark.asyncio
async def test_updates_configuration_requires_admin(client: AppClient):
    member = await create_user(is_admin=False)
    client.current_user = member

    assert (await client.get("/api/organization/updates_configuration")).status_code == status.HTTP_403_FORBIDDEN
    response = await client.patch(
        "/api/organization/updates_configuration",
        json={"goal_update_question": "nope"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
