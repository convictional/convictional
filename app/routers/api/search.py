from fastapi import APIRouter, Depends, Query

from app.models.accounts import User
from app.models.collaboration.content import SERP_DEFAULT_CONTENT_TYPES, run_serp_search
from app.routers.api.schemas import ContentResponse, PaginatedResponse
from app.routers.api.serializers import content_responses
from app.routers.dependencies import get_current_user
from config.enums import ContentType

router = APIRouter(tags=["search"])

# Content types the user can explicitly filter to. Decisions are filter-only: they
# surface only when the user selects the Decisions facet, never in the default results.
FILTERABLE_CONTENT_TYPES = SERP_DEFAULT_CONTENT_TYPES | {ContentType.DECISION}


class SearchResponse(PaginatedResponse):
    results: list[ContentResponse]
    query: str
    content_type: str | None
    hero_count: int = 0


@router.get("/search", response_model=SearchResponse)
async def api_search(
    q: str = Query(""),
    content_type: ContentType | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    query = q.strip()
    content_type_value = content_type.value if content_type else None

    if len(query) < 2:
        return SearchResponse(results=[], query=query, content_type=content_type_value)

    if content_type and content_type not in FILTERABLE_CONTENT_TYPES:
        return SearchResponse(results=[], query=query, content_type=content_type_value)

    results, search = await run_serp_search(
        organization=current_user.organization,
        query=query,
        user=current_user,
        content_type=content_type,
    )

    return SearchResponse(
        results=content_responses(results, search.relevance_scores, current_user),
        query=query,
        content_type=content_type_value,
        hero_count=search.hero_count,
    )
