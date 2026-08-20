import pytest

from config.enums import ChannelEventAction, ChannelEventResource
from infra.messaging import Topic
from tests.helpers.app import AppClient, receive_event
from tests.helpers.factories import create_goal, create_goal_comment, create_user


@pytest.mark.asyncio
async def test_goal_comments_channel_broadcasts(client: AppClient):
    """Test that comment mutations broadcast JSON events to subscribers."""
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    topic = Topic("goal_comments", goal_id=goal.id)

    # Create a comment from another user and broadcast — subscriber receives creation event
    comment = await create_goal_comment(goal_id=goal.id, user_id=other_user.id, content="New comment")

    async with client.connect_channel(topic) as websocket:
        await topic.broadcast(new_comment_id=str(comment.id), author_id=str(other_user.id))
        response = await receive_event(websocket, ChannelEventResource.GOAL_COMMENT)
        assert response["action"] == ChannelEventAction.CREATED
        assert response["data"]["content"] == "New comment"

        # Edit broadcast from other user
        comment.content = "Edited"
        await comment.save(update_fields=["content"])
        await topic.broadcast(edited_comment_id=str(comment.id), author_id=str(other_user.id))
        response = await receive_event(websocket, ChannelEventResource.GOAL_COMMENT)
        assert response["action"] == ChannelEventAction.UPDATED
        assert response["data"]["content"] == "Edited"

        # Delete broadcast from other user
        await topic.broadcast(deleted_comment_id=str(comment.id), author_id=str(other_user.id))
        response = await receive_event(websocket, ChannelEventResource.GOAL_COMMENT)
        assert response["action"] == ChannelEventAction.DELETED

    # Reaction updates are sent to everyone (including the author)
    comment2 = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="React to this")

    async with client.connect_channel(topic) as websocket:
        await client.post(f"/api/goals/{goal.id}/comments/{comment2.id}/reactions?reaction_type=thumbs_up")
        response = await receive_event(websocket, ChannelEventResource.GOAL_COMMENT)
        assert response["action"] == ChannelEventAction.REACTION_TOGGLED


@pytest.mark.asyncio
async def test_goal_comments_close_thread_broadcasts_panel(client: AppClient):
    """Test that closing a thread sends a panel update event."""
    user = await client.get_default_user()
    goal = await create_goal(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Thread")
    topic = Topic("goal_comments", goal_id=goal.id)

    async with client.connect_channel(topic) as websocket:
        await client.patch(f"/api/goals/{goal.id}/comments/{comment.id}", json={"closed": True})
        response = await receive_event(websocket, ChannelEventResource.GOAL_COMMENT)
        assert response["action"] == ChannelEventAction.PANEL_UPDATED
