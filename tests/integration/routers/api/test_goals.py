from datetime import UTC, datetime

import pytest
from fastapi import status

from app.jobs.content import ContentIndexingJob
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Event, Notification, SubscriptionPreference
from app.models.workspaces.goals import Goal
from config.enums import EventAction, MailboxLabel, SubscriptionLevel
from infra.email import FakeDelivery
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_goal_comment, create_group, create_subgoal, create_user


@pytest.mark.asyncio
async def test_goals_listing(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    # Create goals with different owners and a completed goal
    goal1 = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, description="My goal", owner_id=user.id
    )
    await create_goal(
        organization_id=user.organization_id, creator_id=user.id, description="Other goal", owner_id=other_user.id
    )
    completed = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Done")
    completed.is_completed = True
    await completed.close()

    # Add subgoal and comment to first goal
    await create_goal(
        organization_id=user.organization_id, creator_id=user.id, description="Child", parent_id=goal1.id
    )
    await create_goal_comment(goal_id=goal1.id, user_id=user.id, content="A comment")

    # Create a draft goal on a planning list
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Planned goal",
        planning_list_name="Q2 Planning",
    )

    # Active view returns active goals with subgoals and comments
    response = await client.get("/api/goals?expand=subgoals")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["goals"]) == 2
    assert "next_cursor" in data
    assert "has_more" in data
    assert all(not g["is_closed"] for g in data["goals"])

    # First page includes planning list names
    assert data["planning_list_names"] == ["Q2 Planning"]

    goal1_data = next(g for g in data["goals"] if g["id"] == str(goal1.id))
    assert len(goal1_data["subgoals"]) == 1
    assert goal1_data["open_comment_count"] == 1

    # Without ?expand=subgoals the field is null (opt-in)
    response = await client.get("/api/goals")
    data = response.json()
    assert all(g["subgoals"] is None for g in data["goals"])

    # Completed view
    response = await client.get("/api/goals?is_completed=true")
    data = response.json()
    assert len(data["goals"]) == 1
    assert data["goals"][0]["is_completed"] is True

    # Filter by owner
    response = await client.get(f"/api/goals?owner_ids={user.id}")
    data = response.json()
    assert len(data["goals"]) == 1
    assert data["goals"][0]["owner"]["id"] == str(user.id)


@pytest.mark.asyncio
async def test_goal_crud(client: AppClient):
    user = await client.get_default_user()

    # Create with owner
    response = await client.post(
        "/api/goals",
        json={
            "description": "New goal",
            "owner_id": str(user.id),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["description"] == "New goal"
    assert data["status"] == "on_track"
    assert data["is_draft"] is False
    assert data["owner"]["id"] == str(user.id)
    goal_id = data["id"]

    # Update
    response = await client.patch(f"/api/goals/{goal_id}", json={"description": "Updated goal", "status": "at_risk"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["description"] == "Updated goal"
    assert data["status"] == "at_risk"

    # Clear fields
    response = await client.patch(f"/api/goals/{goal_id}", json={"clear_owner": True, "clear_target_date": True})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["owner"] is None

    # Close
    response = await client.post(f"/api/goals/{goal_id}/close")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_closed"] is True

    # Reactivate
    response = await client.post(f"/api/goals/{goal_id}/reactivate")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_closed"] is False

    # Close as completed
    response = await client.post(f"/api/goals/{goal_id}/close", json={"is_completed": True})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_closed"] is True
    assert response.json()["is_completed"] is True

    # Reactivate again
    response = await client.post(f"/api/goals/{goal_id}/reactivate")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_closed"] is False

    # Delete
    response = await client.delete(f"/api/goals/{goal_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_closing_parent_goal_closes_and_notifies_subgoal(client: AppClient, background_jobs: InlineJobs):
    """Closing a parent cascades to its open subgoals: each closes and fires its own
    GOAL_CLOSED event (routed through record_and_notify, attributed to the actor) so the
    subgoal's timeline records the close and its subscribers are notified. A silent bulk
    update would produce no event — this asserts the notified path.
    """
    user = await client.get_default_user()
    subgoal_owner = await create_user(organization_id=user.organization_id)

    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, owner_id=user.id)
    subgoal = await create_subgoal(
        parent_id=parent.id, organization_id=user.organization_id, creator_id=user.id, owner_id=subgoal_owner.id
    )
    # Owner subscribes at ALL so a close reaches their inbox (a non-creator at the default
    # RELEVANT_ONLY level is intentionally not reached by a plain close — see notifications spec).
    await subgoal.fetch_related("workspace")
    await subgoal.workspace.subscribe(subgoal_owner.id)

    response = await client.post(f"/api/goals/{parent.id}/close")
    assert response.status_code == status.HTTP_200_OK

    await subgoal.refresh_from_db()
    assert subgoal.is_closed

    subgoal_close_events = await Event.filter(recordable_id=subgoal.id, action=EventAction.GOAL_CLOSED)
    assert len(subgoal_close_events) == 1
    assert subgoal_close_events[0].creator_id == user.id

    # The notified path reaches the ALL-subscribed owner: an unread inbox row for the close.
    owner_entry = await MailboxEntry.get(resource_gid=str(subgoal.global_id), owner_id=subgoal_owner.id)
    assert MailboxLabel.INBOX in owner_entry.labels
    assert MailboxLabel.UNREAD in owner_entry.labels


@pytest.mark.asyncio
async def test_goal_create_subgoal_and_planning_list(client: AppClient):
    user = await client.get_default_user()

    # Create subgoal
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent")
    response = await client.post(
        "/api/goals",
        json={
            "description": "Child goal",
            "parent_id": str(parent.id),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["description"] == "Child goal"

    # Verify subgoal appears in parent listing
    response = await client.get("/api/goals?expand=subgoals")
    parent_data = next(g for g in response.json()["goals"] if g["id"] == str(parent.id))
    assert len(parent_data["subgoals"]) == 1

    # Create planning list goal
    response = await client.post(
        "/api/goals",
        json={
            "description": "Planning goal",
            "planning_list_name": "Q3 Planning",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["planning_list_name"] == "Q3 Planning"
    assert data["is_draft"] is True

    # Appears in planning list view
    response = await client.get("/api/goals?planning_list_name=Q3 Planning")
    assert len(response.json()["goals"]) == 1


@pytest.mark.asyncio
async def test_goal_show_subgoal_with_expand_parent(client: AppClient):
    user = await client.get_default_user()
    parent_owner = await create_user(organization_id=user.organization_id)
    parent = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=parent_owner.id,
        description="Parent",
    )
    subgoal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        parent_id=parent.id,
        description="Sub",
    )

    response = await client.get(f"/api/goals/{subgoal.id}?expand=subgoals&expand=parent")
    assert response.status_code == status.HTTP_200_OK, response.text
    body = response.json()
    assert body["parent"]["id"] == str(parent.id)
    assert body["parent"]["owner"]["id"] == str(parent_owner.id)


@pytest.mark.asyncio
async def test_goal_access_control(client: AppClient):
    await client.get_default_user()
    other_org_user = await create_user()

    goal = await create_goal(
        organization_id=other_org_user.organization_id,
        creator_id=other_org_user.id,
        description="Other org goal",
    )

    # Cannot access goal from another organization
    response = await client.patch(f"/api/goals/{goal.id}", json={"description": "Hijacked"})
    assert response.status_code == status.HTTP_404_NOT_FOUND

    response = await client.delete(f"/api/goals/{goal.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_goals_sorting(client: AppClient):
    user = await client.get_default_user()

    goal1 = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="First")
    goal2 = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Second")
    goal3 = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Third")

    # Reverse the order
    response = await client.post(
        "/api/goals/sort",
        json={
            "ids": [str(goal3.id), str(goal2.id), str(goal1.id)],
            "view": "active",
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify new order
    response = await client.get("/api/goals")
    goal_ids = [g["id"] for g in response.json()["goals"]]
    assert goal_ids.index(str(goal3.id)) < goal_ids.index(str(goal2.id))
    assert goal_ids.index(str(goal2.id)) < goal_ids.index(str(goal1.id))

    # Subgoal sort
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent")
    sub1 = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, description="Sub 1", parent_id=parent.id
    )
    sub2 = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, description="Sub 2", parent_id=parent.id
    )
    response = await client.post(
        f"/api/goals/{parent.id}/subgoals/sort",
        json={
            "ids": [str(sub2.id), str(sub1.id)],
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_filtering_goals_by_owner_and_group(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    group_a = await create_group(organization_id=user.organization_id, name="Team A")
    group_b = await create_group(organization_id=user.organization_id, name="Team B")

    goal_owned_by_current = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        group_id=group_a.id,
        description="Goal owned by current user in Team A",
        activated_at=datetime.now(UTC),
    )
    goal_owned_by_other = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=other_user.id,
        group_id=group_b.id,
        description="Goal owned by other user in Team B",
        activated_at=datetime.now(UTC),
    )
    goal_no_owner_in_group_a = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=None,
        group_id=group_a.id,
        description="Goal without owner in Team A",
        activated_at=datetime.now(UTC),
    )

    response = await client.get(f"/api/goals?owner_ids={user.id}")
    assert response.status_code == status.HTTP_200_OK
    goal_ids = {g["id"] for g in response.json()["goals"]}
    assert str(goal_owned_by_current.id) in goal_ids
    assert str(goal_owned_by_other.id) not in goal_ids

    response = await client.get(f"/api/goals?group_ids={group_a.id}")
    assert response.status_code == status.HTTP_200_OK
    goal_ids = {g["id"] for g in response.json()["goals"]}
    assert str(goal_owned_by_current.id) in goal_ids
    assert str(goal_no_owner_in_group_a.id) in goal_ids
    assert str(goal_owned_by_other.id) not in goal_ids

    response = await client.get(f"/api/goals?group_ids={group_a.id}&group_ids={group_b.id}")
    assert response.status_code == status.HTTP_200_OK
    goal_ids = {g["id"] for g in response.json()["goals"]}
    assert str(goal_owned_by_current.id) in goal_ids
    assert str(goal_owned_by_other.id) in goal_ids

    response = await client.get(f"/api/goals?owner_ids={user.id}&group_ids={group_a.id}")
    assert response.status_code == status.HTTP_200_OK
    goal_ids = {g["id"] for g in response.json()["goals"]}
    assert str(goal_owned_by_current.id) in goal_ids
    assert str(goal_no_owner_in_group_a.id) not in goal_ids


@pytest.mark.asyncio
async def test_filtering_goals_on_planning_lists(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        description="My Planning Goal",
        planning_list_name="Q1 2025",
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=other_user.id,
        description="Other Planning Goal",
        planning_list_name="Q1 2025",
    )

    response = await client.get(f"/api/goals?planning_list_name=Q1+2025&owner_ids={user.id}")
    assert response.status_code == status.HTTP_200_OK
    descriptions = {g["description"] for g in response.json()["goals"]}
    assert "My Planning Goal" in descriptions
    assert "Other Planning Goal" not in descriptions


@pytest.mark.asyncio
async def test_filtering_parent_goals_by_subgoal_owner(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)

    parent = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=None,
        description="Parent With Matching Subgoals",
        activated_at=datetime.now(UTC),
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        description="Subgoal 1",
        parent_id=parent.id,
        activated_at=datetime.now(UTC),
    )
    other_user_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=other_user.id,
        description="Other User Goal",
        activated_at=datetime.now(UTC),
    )

    response = await client.get(f"/api/goals?owner_ids={user.id}")
    assert response.status_code == status.HTTP_200_OK
    goal_ids = {g["id"] for g in response.json()["goals"]}
    assert str(parent.id) in goal_ids
    assert str(other_user_goal.id) not in goal_ids


@pytest.mark.asyncio
async def test_planning_list_activation(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()

    # Create active goals (one completed, one incomplete)
    active1 = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, description="Active incomplete"
    )
    active2 = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, description="Active completed"
    )
    active2.is_completed = True
    await active2.save()

    # Create planning list goals with a comment thread
    planned1 = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Planned goal 1",
        planning_list_name="Q3",
    )
    planned2 = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Planned goal 2",
        planning_list_name="Q3",
    )
    await create_goal_comment(goal_id=planned1.id, user_id=user.id, content="Open thread")

    # GET summary returns correct counts
    response = await client.get("/api/goals/planning_lists/Q3")
    assert response.status_code == status.HTTP_200_OK
    summary = response.json()
    assert summary["planning_goals_count"] == 2
    assert summary["completed_count"] == 1
    assert summary["incomplete_count"] == 1
    assert summary["open_threads_count"] == 1

    # GET on a missing planning list returns 404
    response = await client.get("/api/goals/planning_lists/nonexistent")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # POST activates the planning list
    response = await client.post("/api/goals/planning_lists/Q3/activate")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Previously active goals are now closed
    await active1.refresh_from_db()
    await active2.refresh_from_db()
    assert active1.is_closed
    assert active2.is_closed

    # Planning list goals are now active (activated_at set, planning_list_name cleared)
    await planned1.refresh_from_db()
    await planned2.refresh_from_db()
    assert planned1.activated_at is not None
    assert planned1.planning_list_name is None
    assert planned2.activated_at is not None
    assert planned2.planning_list_name is None

    # All affected goals were re-indexed
    indexing_jobs = [j for j in background_jobs.completed if isinstance(j.job_definition, ContentIndexingJob)]
    assert len(indexing_jobs) == 4  # 2 closed + 2 activated

    # They appear in the active view
    response = await client.get("/api/goals")
    active_ids = {g["id"] for g in response.json()["goals"]}
    assert str(planned1.id) in active_ids
    assert str(planned2.id) in active_ids
    assert str(active1.id) not in active_ids
    assert str(active2.id) not in active_ids

    # Empty planning list returns 204 with no side effects
    response = await client.post("/api/goals/planning_lists/nonexistent/activate")
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_no_notifications_for_planning_list_goals(client: AppClient, email_delivery: FakeDelivery):
    user = await client.get_default_user()
    subscriber = await create_user(organization_id=user.organization_id)
    await SubscriptionPreference.update_for(subscriber.id, {Goal.record_type: SubscriptionLevel.ALL})

    # Create a planning list goal with a subgoal
    response = await client.post(
        "/api/goals",
        json={
            "description": "Planning list goal",
            "planning_list_name": "Q3 Planning",
            "subgoal_titles": ["Subgoal one"],
            "subgoal_owner_ids": [],
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    goal = await Goal.filter(planning_list_name="Q3 Planning").first()
    assert goal is not None
    subgoal = await Goal.filter(parent_id=goal.id).first()
    assert subgoal is not None

    assert await Notification.all().count() == 0
    assert len(email_delivery.messages) == 0

    # Update the planning list goal
    response = await client.patch(f"/api/goals/{goal.id}", json={"description": "Updated planning goal"})
    assert response.status_code == status.HTTP_200_OK
    assert await Notification.all().count() == 0
    assert len(email_delivery.messages) == 0

    # Update the subgoal (inherits planning list from parent)
    response = await client.patch(f"/api/goals/{subgoal.id}", json={"description": "Updated subgoal"})
    assert response.status_code == status.HTTP_200_OK
    assert await Notification.all().count() == 0
    assert len(email_delivery.messages) == 0
