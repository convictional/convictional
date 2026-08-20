import pytest
from fastapi import status

from app.models.collaboration.workspace import Mention
from app.models.workspaces.goals import GoalComment
from tests.helpers.app import AppClient
from tests.helpers.factories import create_goal, create_goal_comment, create_user


@pytest.mark.asyncio
async def test_comment_crud(client: AppClient):
    creator = await client.get_default_user()
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    # GET empty list
    response = await client.get(f"/api/goals/{goal.id}/comments")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["comments"] == []

    # POST create top-level comment
    response = await client.post(
        f"/api/goals/{goal.id}/comments",
        json={"content": "This needs work"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["content"] == "This needs work"
    assert data["parent_id"] is None
    assert data["closed_at"] is None
    assert data["user"]["id"] == str(creator.id)
    assert data["user"]["display_name"] == creator.display_name
    assert data["replies"] == []
    comment_id = data["id"]

    # POST create reply
    response = await client.post(
        f"/api/goals/{goal.id}/comments",
        json={"content": "I agree", "parent_id": comment_id},
    )
    assert response.status_code == status.HTTP_201_CREATED
    reply_data = response.json()
    assert reply_data["parent_id"] == comment_id
    reply_id = reply_data["id"]

    # GET returns threaded comments (only top-level, with replies nested)
    response = await client.get(f"/api/goals/{goal.id}/comments")
    comments = response.json()["comments"]
    assert len(comments) == 1
    assert comments[0]["id"] == comment_id
    assert len(comments[0]["replies"]) == 1
    assert comments[0]["replies"][0]["id"] == reply_id

    # PATCH edit
    response = await client.patch(
        f"/api/goals/{goal.id}/comments/{comment_id}",
        json={"content": "Updated feedback"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["content"] == "Updated feedback"

    # PATCH close thread
    response = await client.patch(
        f"/api/goals/{goal.id}/comments/{comment_id}",
        json={"closed": True},
    )
    assert response.status_code == status.HTTP_200_OK
    # Closed comments are excluded from the list
    assert response.json()["comments"] == []

    # Re-closing is a no-op.
    response = await client.patch(
        f"/api/goals/{goal.id}/comments/{comment_id}",
        json={"closed": True},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["comments"] == []

    # PATCH reopen thread
    response = await client.patch(
        f"/api/goals/{goal.id}/comments/{comment_id}",
        json={"closed": False},
    )
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()["comments"]) == 1

    # Content edit and close can be combined.
    response = await client.patch(
        f"/api/goals/{goal.id}/comments/{comment_id}",
        json={"content": "Final wording", "closed": True},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["comments"] == []

    # Empty PATCH body is rejected.
    response = await client.patch(
        f"/api/goals/{goal.id}/comments/{comment_id}",
        json={},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # DELETE
    response = await client.delete(f"/api/goals/{goal.id}/comments/{comment_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_comment_permissions(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    # Creator makes a comment
    response = await client.post(
        f"/api/goals/{goal.id}/comments",
        json={"content": "Review this"},
    )
    comment_id = response.json()["id"]

    # Other user cannot edit or delete creator's comment
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/goals/{goal.id}/comments/{comment_id}",
            json={"content": "Hijacked"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await client.delete(f"/api/goals/{goal.id}/comments/{comment_id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # But other user can close (collaborative workflow), and cannot smuggle a
    # content edit through the same PATCH.
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/goals/{goal.id}/comments/{comment_id}",
            json={"closed": True},
        )
        assert response.status_code == status.HTTP_200_OK

        response = await client.patch(
            f"/api/goals/{goal.id}/comments/{comment_id}",
            json={"content": "Sneaky", "closed": False},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    comment = await GoalComment.get(id=comment_id)
    assert comment.is_closed


@pytest.mark.asyncio
async def test_cannot_close_reply(client: AppClient):
    creator = await client.get_default_user()
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    parent = await create_goal_comment(goal_id=goal.id, user_id=creator.id, content="Thread start")
    reply = await create_goal_comment(goal_id=goal.id, user_id=creator.id, content="Reply", parent_id=parent.id)

    response = await client.patch(
        f"/api/goals/{goal.id}/comments/{reply.id}",
        json={"closed": True},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_comment_mentions(client: AppClient):
    # Goals are inbox-native: a mention records a Mention row (surfaced via the inbox), never email.
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Goals", organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.post(
        f"/api/goals/{goal.id}/comments",
        json={"content": "Hey @[Alice Goals] what do you think?"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    await goal.fetch_related("workspace")
    mentions = await Mention.filter(workspace_id=goal.workspace_id).all()
    assert len(mentions) == 1
    assert mentions[0].mentioned_id == alice.id


@pytest.mark.asyncio
async def test_reaction_toggle(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.post(
        f"/api/goals/{goal.id}/comments",
        json={"content": "Test comment"},
    )
    comment_id = response.json()["id"]

    # Toggle reaction on
    response = await client.post(f"/api/goals/{goal.id}/comments/{comment_id}/reactions?reaction_type=thumbs_up")
    assert response.status_code == status.HTTP_200_OK
    reaction_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
    assert str(creator.id) in reaction_ids

    # Toggle reaction off
    response = await client.post(f"/api/goals/{goal.id}/comments/{comment_id}/reactions?reaction_type=thumbs_up")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["reactions"].get("thumbs_up", []) == []

    # Another user can react
    with client.current_user_as(other_user):
        response = await client.post(f"/api/goals/{goal.id}/comments/{comment_id}/reactions?reaction_type=heart")
        assert response.status_code == status.HTTP_200_OK
        heart_ids = [u["id"] for u in response.json()["reactions"]["heart"]]
        assert str(other_user.id) in heart_ids


@pytest.mark.asyncio
async def test_content_validation(client: AppClient):
    creator = await client.get_default_user()
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)

    # Empty content rejected
    response = await client.post(
        f"/api/goals/{goal.id}/comments",
        json={"content": ""},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Blank content rejected
    response = await client.post(
        f"/api/goals/{goal.id}/comments",
        json={"content": "   "},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
