import json

import pytest

from tests.helpers.factories import create_group, create_group_member, create_user


@pytest.mark.asyncio
async def test_current_user_tool(mcp_client):
    """Test that the current_user tool returns the authenticated user's data."""
    user = await create_user(name="Test User")
    await user.fetch_related("organization")

    async with await mcp_client(user) as client:
        result = await client.call_tool("current_user", {})

    data = json.loads(result.content[0].text)
    assert data["id"] == str(user.id)
    assert data["email"] == user.email
    assert data["name"] == "Test User"
    assert data["is_admin"] is False
    assert "created_at" in data
    assert data["organization"]["id"] == str(user.organization_id)
    assert data["organization"]["domain"] == user.organization.domain
    assert data["groups"] == []


@pytest.mark.asyncio
async def test_current_user_tool_with_groups(mcp_client):
    """Test that the current_user tool returns the user's group memberships."""
    user = await create_user(name="Test User")
    group1 = await create_group(organization_id=user.organization_id, name="Engineering")
    group2 = await create_group(organization_id=user.organization_id, name="Leadership")
    await create_group_member(group_id=group1.id, user_id=user.id)
    await create_group_member(group_id=group2.id, user_id=user.id)

    async with await mcp_client(user) as client:
        result = await client.call_tool("current_user", {})

    data = json.loads(result.content[0].text)
    assert len(data["groups"]) == 2
    group_names = {g["name"] for g in data["groups"]}
    assert group_names == {"Engineering", "Leadership"}
    group_ids = {g["id"] for g in data["groups"]}
    assert group_ids == {str(group1.id), str(group2.id)}
