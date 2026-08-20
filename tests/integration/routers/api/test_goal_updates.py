from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.workspace import (
    Attachment,
    Event,
    Mention,
)
from app.models.workspaces.goals import Goal, GoalUpdate
from config.enums import EventAction, GoalStatus
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_goal,
    create_goal_update,
    create_group,
    create_group_member,
    create_user,
)


@pytest.mark.asyncio
async def test_get_latest_update(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, owner_id=user.id)

    # Returns envelope with null latest_update when no completed updates exist
    response = await client.get(f"/api/goals/{goal.id}/updates/latest")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["latest_update"] is None
    assert data["question_text"] == "How's it going?"
    assert data["group_members"] == []

    # Returns the most recent completed update, ignoring pending ones
    await create_goal_update(goal_id=goal.id, creator_id=user.id, status=GoalStatus.ON_TRACK)
    await create_goal_update(
        goal_id=goal.id,
        creator_id=user.id,
        status=GoalStatus.AT_RISK,
        answer_text="Making great progress",
    )

    response = await client.get(f"/api/goals/{goal.id}/updates/latest")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    update = data["latest_update"]
    assert update["answer_text"] == "Making great progress"
    assert update["answer_html"] is not None
    assert update["status"] == "at_risk"
    assert update["is_completed"] is True
    assert update["creator"]["id"] == str(user.id)
    assert update["creator"]["display_name"] == user.display_name
    assert "created_at" in update


@pytest.mark.asyncio
async def test_get_pending_update(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, owner_id=user.id)

    # Returns default question text when no pending update exists
    response = await client.get(f"/api/goals/{goal.id}/updates/pending")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is None
    assert data["question_text"] == "How's it going?"

    # Returns the pending update when one exists
    pending = await create_goal_update(goal_id=goal.id, creator_id=user.id, status=GoalStatus.AT_RISK)
    response = await client.get(f"/api/goals/{goal.id}/updates/pending")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(pending.id)
    assert data["question_text"] == "How's it going?"
    assert data["status"] == "at_risk"
    assert data["answer_text"] is None

    # Does not return completed updates
    pending.completed_at = pending.created_at
    await pending.save()
    response = await client.get(f"/api/goals/{goal.id}/updates/pending")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] is None

    # Returns 204 for non-owner
    other_user = await create_user(organization_id=user.organization_id)
    other_goal = await create_goal(
        organization_id=user.organization_id, creator_id=other_user.id, owner_id=other_user.id
    )
    await create_goal_update(goal_id=other_goal.id, creator_id=other_user.id, status=GoalStatus.ON_TRACK)
    response = await client.get(f"/api/goals/{other_goal.id}/updates/pending")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_submit_update(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )

    # Submit a completed update
    response = await client.post(
        f"/api/goals/{goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Hit a blocker",
            "progress": 0.75,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["answer_text"] == "Hit a blocker"
    assert data["status"] == "at_risk"
    assert data["progress"] == 0.75
    assert data["is_completed"] is True
    assert data["creator"]["id"] == str(user.id)

    await goal.refresh_from_db()
    assert goal.status == GoalStatus.AT_RISK
    assert goal.progress == 0.75

    event = await Event.filter(Event.filters.by_action(EventAction.GOAL_UPDATE_POSTED)).first()
    assert event is not None

    # Fills a pending update instead of creating a new one
    pending_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )
    await create_goal_update(goal_id=pending_goal.id, creator_id=user.id, status=GoalStatus.ON_TRACK)

    response = await client.post(
        f"/api/goals/{pending_goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Filled pending",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    pending_updates = await GoalUpdate.filter(goal_id=pending_goal.id)
    assert len(pending_updates) == 1
    assert pending_updates[0].answer_text == "Filled pending"

    # Draft saves without completing or creating events
    draft_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )
    pending = await create_goal_update(goal_id=draft_goal.id, creator_id=user.id, status=GoalStatus.ON_TRACK)

    response = await client.post(
        f"/api/goals/{draft_goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Work in progress",
            "progress": 0.6,
            "is_draft": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["is_completed"] is False
    assert data["answer_text"] == "Work in progress"

    await pending.refresh_from_db()
    assert pending.is_completed is False

    await draft_goal.refresh_from_db()
    assert draft_goal.status == GoalStatus.ON_TRACK

    # Group member can submit an update
    group = await create_group(organization_id=user.organization_id)
    await create_group_member(group.id, user.id)
    group_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        group_id=group.id,
        owner_id=None,
    )

    response = await client.post(
        f"/api/goals/{group_goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": "Group member update",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["answer_text"] == "Group member update"

    # Returns 404 for non-owner
    other_user = await create_user(organization_id=user.organization_id)
    other_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=other_user.id,
        owner_id=other_user.id,
    )
    response = await client.post(
        f"/api/goals/{other_goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": "Unauthorized",
        },
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_submit_update_mentions(client: AppClient):
    # Goals are inbox-native: a mention in an update records a Mention row (surfaced via the
    # inbox), never email.
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Goals", organization_id=creator.organization_id)
    goal = await create_goal(
        organization_id=creator.organization_id,
        creator_id=creator.id,
        owner_id=creator.id,
        status=GoalStatus.ON_TRACK,
    )

    response = await client.post(
        f"/api/goals/{goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": "Hey @[Alice Goals] can you review?",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    await goal.fetch_related("workspace")
    mentions = await Mention.filter(workspace_id=goal.workspace_id).all()
    assert len(mentions) == 1
    assert mentions[0].mentioned_id == alice.id

    # A draft does not notify mentioned users
    draft_goal = await create_goal(
        organization_id=creator.organization_id,
        creator_id=creator.id,
        owner_id=creator.id,
        status=GoalStatus.ON_TRACK,
    )
    response = await client.post(
        f"/api/goals/{draft_goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": "Draft mentioning @[Alice Goals]",
            "is_draft": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK

    await draft_goal.fetch_related("workspace")
    draft_mentions = await Mention.filter(workspace_id=draft_goal.workspace_id).all()
    assert draft_mentions == []


@pytest.mark.asyncio
async def test_complete_goal_with_update(client: AppClient):
    user = await client.get_default_user()
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )

    response = await client.post(
        f"/api/goals/{goal.id}/updates/complete",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": "All done!",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["is_completed"] is True
    assert data["answer_text"] == "All done!"

    await goal.refresh_from_db()
    assert goal.is_completed is True
    assert goal.completed_at is not None

    completed_event = await Event.filter(
        Event.filters.by_action(EventAction.GOAL_COMPLETED) & Event.filters.by_workspace(goal.workspace_id)
    ).first()
    assert completed_event is not None

    update_event = await Event.filter(
        Event.filters.by_action(EventAction.GOAL_UPDATE_POSTED) & Event.filters.by_workspace(goal.workspace_id)
    ).first()
    assert update_event is not None
    assert update_event.details["is_completed"] is True


@pytest.mark.asyncio
async def test_submit_update_claims_attachments(client: AppClient):
    user = await client.get_default_user()

    async def unclaimed_attachment(goal: Goal) -> Attachment:
        # Mirror the upload endpoint, which sets workspace_id and a non-null claim_id.
        return await create_attachment(
            user_id=user.id,
            workspace_id=goal.workspace_id,
            claim_id=uuid4(),
        )

    def referencing(attachment: Attachment, workspace_id) -> str:
        # Mirror how the composer embeds an upload: an image whose src is the download URL.
        return f"An update ![](/workspaces/{workspace_id}/attachments/{attachment.id}/download)"

    # Final submit clears claim_id for the referenced attachment, protecting it from cleanup.
    # An upload the update doesn't reference keeps its claim_id, so CleanupUnclaimedAttachmentsJob
    # can still sweep it — a removed/abandoned attachment isn't retained forever.
    submit_goal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, owner_id=user.id, status=GoalStatus.ON_TRACK
    )
    submit_attachment = await unclaimed_attachment(submit_goal)
    unreferenced_attachment = await unclaimed_attachment(submit_goal)
    response = await client.post(
        f"/api/goals/{submit_goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": referencing(submit_attachment, submit_goal.workspace_id),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    await submit_attachment.refresh_from_db()
    assert submit_attachment.claim_id is None
    assert submit_attachment.workspace_id == submit_goal.workspace_id
    await unreferenced_attachment.refresh_from_db()
    assert unreferenced_attachment.claim_id is not None

    # Draft save also claims referenced attachments, so a long-lived draft's files survive cleanup
    draft_goal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, owner_id=user.id, status=GoalStatus.ON_TRACK
    )
    draft_attachment = await unclaimed_attachment(draft_goal)
    response = await client.post(
        f"/api/goals/{draft_goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": referencing(draft_attachment, draft_goal.workspace_id),
            "is_draft": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    await draft_attachment.refresh_from_db()
    assert draft_attachment.claim_id is None
    assert draft_attachment.workspace_id == draft_goal.workspace_id

    # Complete-with-update path claims too
    complete_goal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, owner_id=user.id, status=GoalStatus.ON_TRACK
    )
    complete_attachment = await unclaimed_attachment(complete_goal)
    response = await client.post(
        f"/api/goals/{complete_goal.id}/updates/complete",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": referencing(complete_attachment, complete_goal.workspace_id),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    await complete_attachment.refresh_from_db()
    assert complete_attachment.claim_id is None
    assert complete_attachment.workspace_id == complete_goal.workspace_id

    # Cross-user: referencing another user's upload doesn't claim it (the claim is scoped to the
    # submitting user), so the update posts but the attachment stays unclaimed.
    other_user = await create_user(organization_id=user.organization_id)
    cross_user_goal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, owner_id=user.id, status=GoalStatus.ON_TRACK
    )
    other_user_attachment = await create_attachment(
        user_id=other_user.id,
        workspace_id=cross_user_goal.workspace_id,
        claim_id=uuid4(),
    )
    response = await client.post(
        f"/api/goals/{cross_user_goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": referencing(other_user_attachment, cross_user_goal.workspace_id),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    await other_user_attachment.refresh_from_db()
    assert other_user_attachment.claim_id is not None

    # Cross-workspace: referencing an attachment uploaded to a different workspace doesn't claim it,
    # even when it belongs to the submitting user — the claim is scoped to the goal's workspace.
    cross_workspace_goal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, owner_id=user.id, status=GoalStatus.ON_TRACK
    )
    foreign_workspace_goal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, owner_id=user.id, status=GoalStatus.ON_TRACK
    )
    foreign_attachment = await create_attachment(
        user_id=user.id,
        workspace_id=foreign_workspace_goal.workspace_id,
        claim_id=uuid4(),
    )
    response = await client.post(
        f"/api/goals/{cross_workspace_goal.id}/updates",
        json={
            "status": GoalStatus.ON_TRACK.value,
            "question_text": "How's it going?",
            "answer_text": referencing(foreign_attachment, foreign_workspace_goal.workspace_id),
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    await foreign_attachment.refresh_from_db()
    assert foreign_attachment.claim_id is not None


@pytest.mark.asyncio
async def test_draft_after_submit_does_not_resurrect_request(client: AppClient):
    user = await client.get_default_user()

    # A completing submit fills the pending row and marks it complete.
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )
    pending = await create_goal_update(goal_id=goal.id, creator_id=user.id, status=GoalStatus.ON_TRACK)
    pending_id = pending.id

    response = await client.post(
        f"/api/goals/{goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Submitted",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED
    updates = await GoalUpdate.filter(goal_id=goal.id)
    assert len(updates) == 1
    assert updates[0].is_completed
    completed_at = updates[0].completed_at

    # A trailing draft targeting the now-completed row is a no-op (204), not a resurrection.
    response = await client.post(
        f"/api/goals/{goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Late draft",
            "is_draft": True,
            "update_id": str(pending_id),
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    updates = await GoalUpdate.filter(goal_id=goal.id)
    assert len(updates) == 1
    assert await GoalUpdate.filter(GoalUpdate.filters.pending_for_goal(goal.id)).first() is None
    assert updates[0].completed_at == completed_at
    assert updates[0].answer_text == "Submitted"

    # Drafting against a still-pending request updates it in place (200), no new row.
    second_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )
    second_pending = await create_goal_update(goal_id=second_goal.id, creator_id=user.id, status=GoalStatus.ON_TRACK)

    response = await client.post(
        f"/api/goals/{second_goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "In-place draft",
            "is_draft": True,
            "update_id": str(second_pending.id),
        },
    )
    assert response.status_code == status.HTTP_200_OK
    second_updates = await GoalUpdate.filter(goal_id=second_goal.id)
    assert len(second_updates) == 1
    assert second_updates[0].answer_text == "In-place draft"
    assert second_updates[0].completed_at is None

    # A proactive draft (no update_id, no pending row) creates a fresh pending row.
    third_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )

    response = await client.post(
        f"/api/goals/{third_goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Proactive draft",
            "is_draft": True,
        },
    )
    assert response.status_code == status.HTTP_200_OK
    third_updates = await GoalUpdate.filter(goal_id=third_goal.id)
    assert len(third_updates) == 1
    assert third_updates[0].is_completed is False

    # A draft targeting a closed (not completed) request is a no-op (204).
    closed_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )
    closed_pending = await create_goal_update(goal_id=closed_goal.id, creator_id=user.id, status=GoalStatus.ON_TRACK)
    await closed_pending.close()
    await closed_pending.save()

    response = await client.post(
        f"/api/goals/{closed_goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Draft on closed",
            "is_draft": True,
            "update_id": str(closed_pending.id),
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert len(await GoalUpdate.filter(goal_id=closed_goal.id)) == 1

    # A draft whose update_id is unknown is a no-op (204) and creates nothing.
    unknown_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        status=GoalStatus.ON_TRACK,
    )

    response = await client.post(
        f"/api/goals/{unknown_goal.id}/updates",
        json={
            "status": GoalStatus.AT_RISK.value,
            "question_text": "How's it going?",
            "answer_text": "Draft with unknown id",
            "is_draft": True,
            "update_id": str(uuid4()),
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert len(await GoalUpdate.filter(goal_id=unknown_goal.id)) == 0


@pytest.mark.asyncio
async def test_request_update(client: AppClient):
    user = await client.get_default_user()
    owner = await create_user(organization_id=user.organization_id)
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=owner.id,
        owner_id=owner.id,
        status=GoalStatus.AT_RISK,
    )

    # Request update for an owned goal
    response = await client.post(
        f"/api/goals/{goal.id}/updates/request",
        json={"question_text": "Can you share an update?"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["question_text"] == "Can you share an update?"
    assert data["answer_text"] is None
    assert data["is_completed"] is False
    assert data["creator"]["id"] == str(owner.id)

    goal_update = await GoalUpdate.filter(goal_id=goal.id).first()
    assert goal_update is not None
    assert goal_update.requested_by_id == user.id

    # A goal with no owner has no one to request an update from
    ownerless_goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=None,
        group_id=None,
    )

    response = await client.post(
        f"/api/goals/{ownerless_goal.id}/updates/request",
        json={"question_text": "Anyone there?"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
