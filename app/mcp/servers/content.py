from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastmcp import Context, FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field

from app.mcp.auth import get_current_user
from app.models.collaboration.content import Content, ContentResearchQuery
from app.routers.api.schemas import ContentResponse, DetailedContentResponse
from app.routers.api.serializers import content_responses, detailed_content_response
from config.enums import ContentType
from infra.db import GlobalID

server = FastMCP("Content")


@server.tool(
    description="Search across all available work-related content "
    "(meetings, posts, goals, tasks, emails, etc.) using full-text search with relevance ranking. "
    "Pass content_type='decision' to find recorded decisions ('what did we decide about X'), "
    "each attributed to its decider and timestamped."
)
async def search_content(
    ctx: Context,
    query: str,
    content_type: ContentType | None = None,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    limit: int = 10,
) -> list[ContentResponse]:
    user = await get_current_user(ctx)

    search = ContentResearchQuery(
        organization=user.organization,
        query=query,
        user=user,
        limit=limit,
        starts_at=starts_at,
        ends_at=ends_at,
        content_types={content_type} if content_type else None,
    )
    results = await search.execute()

    return content_responses(results)


@server.tool(description="Get the full details of a specific content item by ID, including its complete text body.")
async def get_content(
    ctx: Context,
    content_id: UUID | None = None,
    source_id: Annotated[
        str | None,
        Field(
            description="A global_id from another tool's global_id field, "
            "in the format gid://convictional/<Type>/<uuid> "
            "(e.g. gid://convictional/Task/550e8400-e29b-41d4-a716-446655440000)"
        ),
    ] = None,
) -> DetailedContentResponse:
    user = await get_current_user(ctx)

    if content_id:
        content = await Content.get_or_none(id=content_id, organization_id=user.organization_id)
    elif source_id:
        gid = GlobalID.parse(source_id)
        if not gid.is_internal or not gid.record_id:
            raise ToolError(f"Invalid global ID: {source_id}")
        content = await Content.get_or_none(source_id=source_id, organization_id=user.organization_id)
    else:
        raise ToolError("Either content_id or source_id must be provided")

    if not content or not content.can_be_accessed_by(user.id):
        raise ToolError(f"Content not found: {content_id or source_id}")

    return detailed_content_response(content)
