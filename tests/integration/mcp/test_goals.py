import json
from datetime import date

import pytest
from fastmcp.exceptions import ToolError

from config.enums import GoalStatus
from tests.helpers.factories import create_goal, create_goal_comment, create_group, create_user


@pytest.mark.asyncio
async def test_list_goals(mcp_client):
    user = await create_user(email="test@convictional.com")
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test Goal")

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["id"] == str(goal.id)
    assert data[0]["description"] == "Test Goal"
    assert data[0]["subgoals"] == []


@pytest.mark.asyncio
async def test_list_goals_includes_subgoals(mcp_client):
    user = await create_user(email="test@convictional.com")
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent Goal")
    subgoal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=parent.id, description="Subgoal"
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["id"] == str(parent.id)
    assert len(data[0]["subgoals"]) == 1
    assert data[0]["subgoals"][0]["id"] == str(subgoal.id)
    assert data[0]["subgoals"][0]["description"] == "Subgoal"


@pytest.mark.asyncio
async def test_list_goals_excludes_other_organizations(mcp_client):
    user = await create_user(email="test@convictional.com")
    await create_goal(organization_id=user.organization_id, creator_id=user.id, description="My Goal")
    other_user = await create_user(email="other-org@convictional.com")
    await create_goal(organization_id=other_user.organization_id, creator_id=other_user.id, description="Other Goal")

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["description"] == "My Goal"


@pytest.mark.asyncio
async def test_list_goals_filter_by_status(mcp_client):
    user = await create_user(email="test@convictional.com")
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="On Track Goal",
        status=GoalStatus.ON_TRACK,
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="At Risk Goal",
        status=GoalStatus.AT_RISK,
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {"status": "at_risk"})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["description"] == "At Risk Goal"
    assert data[0]["status"] == "at_risk"


@pytest.mark.asyncio
async def test_list_goals_filter_by_owner(mcp_client):
    user = await create_user(email="test@convictional.com")
    other_user = await create_user(organization_id=user.organization_id, email="other@convictional.com")
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        description="My Owned Goal",
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=other_user.id,
        description="Other Owned Goal",
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {"owner_id": str(user.id)})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["description"] == "My Owned Goal"


@pytest.mark.asyncio
async def test_list_goals_filter_by_group(mcp_client):
    user = await create_user(email="test@convictional.com")
    group1 = await create_group(organization_id=user.organization_id, name="Engineering")
    group2 = await create_group(organization_id=user.organization_id, name="Marketing")
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        group_id=group1.id,
        description="Engineering Goal",
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        group_id=group2.id,
        description="Marketing Goal",
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {"group_id": str(group1.id)})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["description"] == "Engineering Goal"
    assert data[0]["group"]["id"] == str(group1.id)
    assert data[0]["group"]["name"] == "Engineering"


@pytest.mark.asyncio
async def test_list_goals_filter_by_target_date(mcp_client):
    user = await create_user(email="test@convictional.com")
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Goal With Date",
        target_date=date(2026, 6, 15),
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Goal Without Date",
        target_date=None,
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {"has_target_date": True})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["description"] == "Goal With Date"


@pytest.mark.asyncio
async def test_list_goals_filter_by_date_range(mcp_client):
    user = await create_user(email="test@convictional.com")
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Early Goal",
        target_date=date(2026, 1, 15),
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Mid Goal",
        target_date=date(2026, 6, 15),
    )
    await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        description="Late Goal",
        target_date=date(2026, 12, 15),
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool(
            "list_goals", {"target_date_after": "2026-03-01", "target_date_before": "2026-09-01"}
        )

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["description"] == "Mid Goal"


@pytest.mark.real_embeddings
@pytest.mark.asyncio
async def test_list_goals_search(mcp_client):
    user = await create_user(email="test@convictional.com")
    await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Revenue Growth")
    await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Team Expansion")

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_goals", {"search": "revenue"})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["description"] == "Revenue Growth"


@pytest.mark.asyncio
async def test_get_goal(mcp_client):
    user = await create_user(email="test@convictional.com")
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test Goal")

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_goal", {"goal_id": str(goal.id)})

    data = json.loads(result.content[0].text)
    assert data["id"] == str(goal.id)
    assert data["description"] == "Test Goal"
    assert data["subgoals"] == []


@pytest.mark.asyncio
async def test_get_goal_with_subgoals(mcp_client):
    user = await create_user(email="test@convictional.com")
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent Goal")
    subgoal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=parent.id, description="Subgoal"
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_goal", {"goal_id": str(parent.id)})

    data = json.loads(result.content[0].text)
    assert data["id"] == str(parent.id)
    assert len(data["subgoals"]) == 1
    assert data["subgoals"][0]["id"] == str(subgoal.id)
    assert data["subgoals"][0]["description"] == "Subgoal"


@pytest.mark.asyncio
async def test_get_goal_with_comments(mcp_client):
    user = await create_user(email="test@convictional.com")
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test Goal")
    comment = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="First comment")
    reply = await create_goal_comment(goal_id=goal.id, user_id=user.id, parent_id=comment.id, content="Reply to first")

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_goal", {"goal_id": str(goal.id)})

    data = json.loads(result.content[0].text)
    assert data["id"] == str(goal.id)
    assert len(data["comments"]) == 1
    assert data["comments"][0]["id"] == str(comment.id)
    assert data["comments"][0]["content"] == "First comment"
    assert len(data["comments"][0]["replies"]) == 1
    assert data["comments"][0]["replies"][0]["id"] == str(reply.id)
    assert data["comments"][0]["replies"][0]["content"] == "Reply to first"


@pytest.mark.asyncio
async def test_get_goal_presenter_fields(mcp_client):
    user = await create_user(name="Test Owner", email="owner@convictional.com")
    group = await create_group(organization_id=user.organization_id, name="Test Group")
    goal = await create_goal(
        organization_id=user.organization_id,
        creator_id=user.id,
        owner_id=user.id,
        group_id=group.id,
        description="Test Goal",
        start_date=date(2026, 1, 1),
        target_date=date(2026, 6, 30),
        status=GoalStatus.AT_RISK,
        progress=0.5,
    )
    await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=goal.id, description="Subgoal 1"
    )
    await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=goal.id, description="Subgoal 2"
    )
    await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Comment 1")
    await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Comment 2")

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_goal", {"goal_id": str(goal.id)})

    data = json.loads(result.content[0].text)
    assert data["start_date"] == "2026-01-01"
    assert data["target_date"] == "2026-06-30"
    assert data["status"] == "at_risk"
    assert data["progress"] == 0.5
    assert data["owner_id"] == str(user.id)
    assert data["owner_name"] == "Test Owner"
    assert data["group"]["id"] == str(group.id)
    assert data["group"]["name"] == "Test Group"
    assert data["is_subgoal"] is False
    assert data["parent_id"] is None
    assert data["subgoal_count"] == 2
    assert data["comment_count"] == 2
    assert "created_at" in data


@pytest.mark.asyncio
async def test_list_subgoals(mcp_client):
    user = await create_user(email="test@convictional.com")
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent Goal")
    subgoal1 = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=parent.id, description="Subgoal 1"
    )
    subgoal2 = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=parent.id, description="Subgoal 2"
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_subgoals", {"goal_id": str(parent.id)})

    data = json.loads(result.content[0].text)
    assert len(data) == 2
    ids = {g["id"] for g in data}
    assert ids == {str(subgoal1.id), str(subgoal2.id)}


@pytest.mark.asyncio
async def test_list_subgoals_recursive(mcp_client):
    user = await create_user(email="test@convictional.com")
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent Goal")
    subgoal = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=parent.id, description="Subgoal"
    )
    nested = await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=subgoal.id, description="Nested Subgoal"
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_subgoals", {"goal_id": str(parent.id), "recursive": True})

    data = json.loads(result.content[0].text)
    assert len(data) == 2
    ids = {g["id"] for g in data}
    assert ids == {str(subgoal.id), str(nested.id)}


@pytest.mark.asyncio
async def test_list_subgoals_not_found(mcp_client):
    user = await create_user(email="test@convictional.com")

    with pytest.raises(ToolError, match="Goal not found"):
        async with await mcp_client(user) as client:
            await client.call_tool("list_subgoals", {"goal_id": "00000000-0000-0000-0000-000000000000"})


@pytest.mark.asyncio
async def test_list_subgoals_shows_is_subgoal_field(mcp_client):
    user = await create_user(email="test@convictional.com")
    parent = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Parent Goal")
    await create_goal(
        organization_id=user.organization_id, creator_id=user.id, parent_id=parent.id, description="Subgoal"
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("list_subgoals", {"goal_id": str(parent.id)})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["is_subgoal"] is True
    assert data[0]["parent_id"] == str(parent.id)


@pytest.mark.asyncio
async def test_get_goal_comments(mcp_client):
    user = await create_user(email="test@convictional.com")
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test Goal")
    comment1 = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="First comment")
    comment2 = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Second comment")
    reply = await create_goal_comment(goal_id=goal.id, user_id=user.id, parent_id=comment1.id, content="Reply")

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_goal_comments", {"goal_id": str(goal.id)})

    data = json.loads(result.content[0].text)
    assert len(data) == 2
    ids = {c["id"] for c in data}
    assert ids == {str(comment1.id), str(comment2.id)}
    first_comment = next(c for c in data if c["id"] == str(comment1.id))
    assert len(first_comment["replies"]) == 1
    assert first_comment["replies"][0]["id"] == str(reply.id)


@pytest.mark.asyncio
async def test_get_goal_comments_excludes_closed(mcp_client):
    user = await create_user(email="test@convictional.com")
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test Goal")
    open_comment = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Open comment")
    closed_comment = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Closed comment")
    await closed_comment.close()

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_goal_comments", {"goal_id": str(goal.id)})

    data = json.loads(result.content[0].text)
    assert len(data) == 1
    assert data[0]["id"] == str(open_comment.id)


@pytest.mark.asyncio
async def test_get_goal_comments_include_closed(mcp_client):
    user = await create_user(email="test@convictional.com")
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, description="Test Goal")
    await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Open comment")
    closed_comment = await create_goal_comment(goal_id=goal.id, user_id=user.id, content="Closed comment")
    await closed_comment.close()

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_goal_comments", {"goal_id": str(goal.id), "include_closed": True})

    data = json.loads(result.content[0].text)
    assert len(data) == 2


@pytest.mark.asyncio
async def test_get_goal_comments_not_found(mcp_client):
    user = await create_user(email="test@convictional.com")

    with pytest.raises(ToolError, match="Goal not found"):
        async with await mcp_client(user) as client:
            await client.call_tool("get_goal_comments", {"goal_id": "00000000-0000-0000-0000-000000000000"})
