import json
from uuid import uuid4

import pytest
from fastmcp.exceptions import ToolError

from config.enums import ContentCategory, ContentType, Sharing
from tests.helpers.factories import create_content, create_user


@pytest.mark.asyncio
async def test_search_content(mcp_client):
    user = await create_user()
    await create_content(
        title="Quarterly Revenue Report",
        index_content="The quarterly revenue exceeded expectations with strong growth.",
        organization_id=user.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    await create_content(
        title="Unrelated Document",
        index_content="This document is about something else entirely.",
        organization_id=user.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("search_content", {"query": "quarterly revenue"})

    data = json.loads(result.content[0].text)
    assert len(data) >= 1
    titles = [d["title"] for d in data]
    assert "Quarterly Revenue Report" in titles


@pytest.mark.asyncio
async def test_search_content_with_content_type_filter(mcp_client):
    user = await create_user()
    await create_content(
        title="Meeting Notes",
        index_content="Discussion about project timelines and deadlines.",
        content_type=ContentType.MEETING,
        organization_id=user.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    await create_content(
        title="Post Deadlines",
        index_content="Review project timelines and deadlines for Q2.",
        content_type=ContentType.POST,
        organization_id=user.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("search_content", {"query": "project timelines", "content_type": "meeting"})

    data = json.loads(result.content[0].text)
    content_types = [d["content_type"] for d in data]
    assert all(ct == "meeting" for ct in content_types)


@pytest.mark.asyncio
async def test_get_content(mcp_client):
    user = await create_user()
    content = await create_content(
        title="Important Decision",
        index_content="We decided to proceed with option A after careful consideration.",
        preview_content="We decided to proceed with option A",
        author="Alice",
        content_type=ContentType.POST,
        category=ContentCategory.DOCUMENT,
        organization_id=user.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_content", {"content_id": str(content.id)})

    data = json.loads(result.content[0].text)
    assert data["id"] == str(content.id)
    assert data["title"] == "Important Decision"
    assert data["author"] == "Alice"
    assert data["content_type"] == "post"
    assert data["category"] == "document"
    assert data["index_content"] == "We decided to proceed with option A after careful consideration."
    assert data["preview_content"] == "We decided to proceed with option A"


@pytest.mark.asyncio
async def test_get_content_not_found(mcp_client):
    user = await create_user()

    with pytest.raises(ToolError, match="Content not found"):
        async with await mcp_client(user) as client:
            await client.call_tool("get_content", {"content_id": "00000000-0000-0000-0000-000000000000"})


@pytest.mark.asyncio
async def test_content_access_control(mcp_client):
    user = await create_user()
    other_user = await create_user(organization_id=user.organization_id)

    private_content = await create_content(
        title="Private Notes",
        index_content="These are private notes only for the other user.",
        organization_id=user.organization_id,
        sharing=Sharing.PRIVATE,
        allowed_user_ids=[str(other_user.id)],
    )

    with pytest.raises(ToolError, match="Content not found"):
        async with await mcp_client(user) as client:
            await client.call_tool("get_content", {"content_id": str(private_content.id)})


@pytest.mark.asyncio
async def test_get_content_by_source_id(mcp_client):
    user = await create_user()
    task_id = uuid4()
    gid = f"gid://convictional/Task/{task_id}"
    content = await create_content(
        title="Task Content",
        index_content="This content is linked to a task.",
        source_id=gid,
        organization_id=user.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    async with await mcp_client(user) as client:
        result = await client.call_tool("get_content", {"source_id": gid})

    data = json.loads(result.content[0].text)
    assert data["id"] == str(content.id)
    assert data["title"] == "Task Content"


@pytest.mark.asyncio
async def test_get_content_by_invalid_source_id(mcp_client):
    user = await create_user()

    with pytest.raises(ToolError, match="Invalid global ID"):
        async with await mcp_client(user) as client:
            await client.call_tool("get_content", {"source_id": "not-a-global-id"})
