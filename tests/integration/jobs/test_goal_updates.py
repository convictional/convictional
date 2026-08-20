from datetime import UTC, datetime

import pytest

from app.jobs.goals import (
    CheckScheduledUpdatesJob,
    GenerateGoalUpdatesJob,
    create_goal_update_request,
)
from app.models.workspaces.goals import GoalUpdate
from config.enums import GoalStatus
from infra.email import FakeDelivery
from infra.jobs import JobsOutbox
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_goal,
    create_goal_update,
    create_group,
    create_organization,
    create_organization_updates_configuration,
    create_subgoal,
    create_user,
)


@pytest.mark.asyncio
async def test_scheduled_updates_with_organization_specific_schedule(client: AppClient):
    """Test that ScheduledUpdatesJob respects organization-specific schedules."""
    org1 = await create_organization()
    org2 = await create_organization()
    await create_user(organization_id=org1.id)
    await create_user(organization_id=org2.id)

    # Every minute (should always generate)
    await create_organization_updates_configuration(organization_id=org1.id, update_schedule="* * * * *")

    # Every Sunday at 7:00 UTC
    # Flakey, will fail if the test runs at this time but no one should be running tests at 2am on a sunday
    await create_organization_updates_configuration(organization_id=org2.id, update_schedule="0 7 * * 7")

    # Run the scheduled updates job
    async with JobsOutbox() as outbox:
        job = CheckScheduledUpdatesJob()
        await job.perform()

        # Check that a GenerateGoalUpdatesJob was enqueued only for org1
        assert len(outbox.jobs) == 1
        job_definition = outbox.jobs[0].job_definition
        assert isinstance(job_definition, GenerateGoalUpdatesJob)
        assert job_definition.organization_id == org1.id


@pytest.mark.asyncio
async def test_generate_goal_updates_creates_updates(client: AppClient):
    user = await client.get_default_user()
    organization_id = user.organization_id
    await create_organization_updates_configuration(organization_id=organization_id)

    # Owner goal: update generated
    await create_goal(organization_id=organization_id, creator_id=user.id, owner_id=user.id)

    # Group goal without owner: should be skipped (no update generated)
    group = await create_group(organization_id=organization_id)
    await create_goal(organization_id=organization_id, creator_id=user.id, group_id=group.id)

    # Draft and closed goals should not generate updates
    await create_goal(
        organization_id=organization_id,
        creator_id=user.id,
        owner_id=user.id,
        activated_at=None,
        planning_list_name="Q1",
    )
    await create_goal(
        organization_id=organization_id,
        creator_id=user.id,
        owner_id=user.id,
        closed_at=datetime.now(UTC),
    )

    # Completed-but-open goal (completed_at set, closed_at NULL): must be skipped by
    # automated requests so the count below stays 1.
    await create_goal(
        organization_id=organization_id,
        creator_id=user.id,
        owner_id=user.id,
        completed_at=datetime.now(UTC),
    )

    job = GenerateGoalUpdatesJob(organization_id=organization_id)
    await job.perform()

    all_updates = await GoalUpdate.filter(goal__organization_id=organization_id)
    assert len(all_updates) == 1

    # Running again closes the stale pending and creates a fresh one
    await job.perform()
    all_updates = await GoalUpdate.filter(goal__organization_id=organization_id)
    assert len(all_updates) == 2
    assert len([u for u in all_updates if u.is_closed]) == 1
    assert len([u for u in all_updates if u.is_open and u.is_incomplete]) == 1


@pytest.mark.asyncio
async def test_generate_goal_updates_includes_subgoals(client: AppClient, email_delivery: FakeDelivery):
    user = await client.get_default_user()
    organization_id = user.organization_id
    await create_organization_updates_configuration(organization_id=organization_id)

    parent = await create_goal(organization_id=organization_id, creator_id=user.id, owner_id=user.id)

    # Activated subgoal with owner: should generate an update
    await create_subgoal(parent_id=parent.id, organization_id=organization_id, creator_id=user.id, owner_id=user.id)

    # Draft subgoal: should be skipped
    await create_subgoal(
        parent_id=parent.id, organization_id=organization_id, creator_id=user.id, owner_id=user.id, activated_at=None
    )

    # Subgoal without owner: should be skipped
    await create_subgoal(parent_id=parent.id, organization_id=organization_id, creator_id=user.id)

    job = GenerateGoalUpdatesJob(organization_id=organization_id)
    await job.perform()

    # Parent goal + 1 activated subgoal with owner = 2 updates
    all_updates = await GoalUpdate.filter(goal__organization_id=organization_id)
    assert len(all_updates) == 2

    # Running again closes stale pending updates and creates fresh ones
    await job.perform()
    all_updates = await GoalUpdate.filter(goal__organization_id=organization_id)
    assert len(all_updates) == 4
    assert len([u for u in all_updates if u.is_closed]) == 2
    assert len([u for u in all_updates if u.is_open and u.is_incomplete]) == 2


@pytest.mark.asyncio
async def test_goal_updates_disabled_by_clearing_question(client: AppClient, email_delivery: FakeDelivery):
    user = await client.get_default_user()
    organization_id = user.organization_id

    # goal_update_question has a default value, so we need to explicitly set it to empty to disable goal updates
    await create_organization_updates_configuration(organization_id=organization_id, goal_update_question="")
    await create_goal(organization_id=organization_id, creator_id=user.id, owner_id=user.id)

    job = GenerateGoalUpdatesJob(organization_id=organization_id)
    await job.perform()

    # There should be 0 updates and 0 emails
    assert await GoalUpdate.filter(goal__organization_id=organization_id).count() == 0
    assert len(email_delivery.messages) == 0


@pytest.mark.asyncio
async def test_generate_goal_updates_completes_stale_pending(client: AppClient):
    user = await client.get_default_user()
    organization_id = user.organization_id
    await create_organization_updates_configuration(organization_id=organization_id)

    goal = await create_goal(organization_id=organization_id, creator_id=user.id, owner_id=user.id)

    # Pre-existing stale pending updates
    stale1 = await create_goal_update(goal_id=goal.id, creator_id=user.id, status=GoalStatus.ON_TRACK)
    stale2 = await create_goal_update(goal_id=goal.id, creator_id=user.id, status=GoalStatus.AT_RISK)

    job = GenerateGoalUpdatesJob(organization_id=organization_id)
    await job.perform()

    # Both stale updates should be closed
    await stale1.refresh_from_db()
    await stale2.refresh_from_db()
    assert stale1.is_closed
    assert stale2.is_closed

    # A single fresh pending update should exist
    all_updates = await GoalUpdate.filter(goal_id=goal.id)
    assert len(all_updates) == 3
    pending = [u for u in all_updates if u.is_open and u.is_incomplete]
    assert len(pending) == 1
    assert pending[0].id != stale1.id
    assert pending[0].id != stale2.id


@pytest.mark.asyncio
async def test_create_goal_update_request_completes_stale_pending(client: AppClient):
    user = await client.get_default_user()
    owner = await create_user(organization_id=user.organization_id)
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=owner.id,
        owner_id=owner.id,
        status=GoalStatus.ON_TRACK,
    )

    # Create multiple stale pending updates
    stale1 = await create_goal_update(goal_id=goal.id, creator_id=owner.id, status=GoalStatus.ON_TRACK)
    stale2 = await create_goal_update(goal_id=goal.id, creator_id=owner.id, status=GoalStatus.AT_RISK)

    new_update = await create_goal_update_request(goal, "Need a fresh update please", owner.id, requested_by=user)

    # Both stale updates should be closed
    await stale1.refresh_from_db()
    await stale2.refresh_from_db()
    assert stale1.is_closed
    assert stale2.is_closed

    # Only one pending update should exist — the new one
    pending = await GoalUpdate.filter(GoalUpdate.filters.pending_for_goal(goal.id))
    assert len(pending) == 1
    assert pending[0].id == new_update.id
    assert pending[0].question_text == "Need a fresh update please"
    assert pending[0].requested_by_id == user.id


@pytest.mark.asyncio
async def test_create_goal_update_request_works_for_completed_goal(client: AppClient):
    # The batch job skips completed goals, but an ad-hoc "request update" must still work.
    user = await client.get_default_user()
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        completed_at=datetime.now(UTC),
    )

    update = await create_goal_update_request(goal, "How did this land?", goal.owner_id)

    assert update is not None
    pending = await GoalUpdate.filter(GoalUpdate.filters.pending_for_goal(goal.id))
    assert len(pending) == 1
    assert pending[0].id == update.id
