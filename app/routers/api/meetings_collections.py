import asyncio
from datetime import datetime
from typing import Self, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from tortoise.functions import Count, Max

from app.models.accounts import User
from app.models.workspaces.meetings import Meeting, MeetingCollection
from app.routers.api.meetings import MeetingResponse, _meeting_list_responses
from app.routers.api.schemas import PaginatedResponse
from app.routers.dependencies import get_current_user
from infra.db import Pagination

router = APIRouter(tags=["meeting collections"])


class MeetingCollectionListItemResponse(BaseModel):
    id: str
    title: str
    description: str | None
    meeting_count: int
    last_meeting_at: datetime | None
    # True iff at least one meeting in the collection was auto-assigned. Such
    # collections are managed by the calendar-grouping flow and can't be
    # deleted via the API.
    auto_assigned: bool


class MeetingCollectionListResponse(PaginatedResponse):
    collections: list[MeetingCollectionListItemResponse]
    # Count of meetings with no collection, surfaced for the "Uncategorized"
    # pseudo-collection row on the index. Page-independent (same on every page).
    uncategorized_count: int


class MeetingCollectionShowResponse(PaginatedResponse):
    collection: MeetingCollectionListItemResponse
    meetings: list[MeetingResponse]


class CreateCollectionRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str | None = None


# `description` follows the PR 1 PATCH idiom: nullable, distinguishes "omitted"
# (leave alone) from explicit null (clear) via `body.model_fields_set`. `title`
# uses the `is not None` idiom — it isn't clearable.
class UpdateCollectionRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    description: str | None = None

    @model_validator(mode="after")
    def at_least_one_field(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("must set at least one field")
        return self


async def get_api_meeting_collection(
    collection_id: UUID, current_user: User = Depends(get_current_user)
) -> MeetingCollection:
    collection = await MeetingCollection.get_or_none(id=collection_id, organization_id=current_user.organization_id)
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


async def _ids_with_auto_assigned_meetings(collection_ids: list[UUID]) -> set[UUID]:
    if not collection_ids:
        return set()
    # Override Meeting's default ordering — Postgres rejects DISTINCT + ORDER BY
    # over columns not in the SELECT list.
    rows = (
        await Meeting.filter(collection_id__in=collection_ids, collection_auto_assigned=True)
        .order_by("collection_id")
        .distinct()
        .values_list("collection_id", flat=True)
    )
    return set(cast(list[UUID], rows))


def _list_item_response(
    collection: MeetingCollection, *, meeting_count: int, last_meeting_at: datetime | None, auto_assigned: bool
) -> MeetingCollectionListItemResponse:
    return MeetingCollectionListItemResponse(
        id=str(collection.id),
        title=collection.title,
        description=collection.description,
        meeting_count=meeting_count,
        last_meeting_at=last_meeting_at,
        auto_assigned=auto_assigned,
    )


async def _single_collection_summary(collection: MeetingCollection) -> MeetingCollectionListItemResponse:
    metadata, auto_assigned_ids = await asyncio.gather(
        _collection_metadata([collection.id]),
        _ids_with_auto_assigned_meetings([collection.id]),
    )
    meeting_count, last_meeting_at = metadata.get(collection.id, (0, None))
    auto_assigned = bool(auto_assigned_ids)
    return _list_item_response(
        collection,
        meeting_count=meeting_count,
        last_meeting_at=last_meeting_at,
        auto_assigned=auto_assigned,
    )


async def _collection_metadata(collection_ids: list[UUID]) -> dict[UUID, tuple[int, datetime | None]]:
    if not collection_ids:
        return {}
    rows = (
        await MeetingCollection.filter(id__in=collection_ids)
        .annotate(meeting_count=Count("meetings_collection"), last_meeting_at=Max("meetings_collection__scheduled_at"))
        .values("id", "meeting_count", "last_meeting_at")
    )
    return {row["id"]: (row["meeting_count"] or 0, row["last_meeting_at"]) for row in rows}


@router.get("/meetings_collections", response_model=MeetingCollectionListResponse)
async def api_meetings_collections_index(
    current_user: User = Depends(get_current_user),
    cursor: str | None = Query(None),
):
    queryset = MeetingCollection.filter(organization_id=current_user.organization_id).order_by("title", "id")
    pagination = await Pagination.create(MeetingCollection, cursor=cursor, queryset=queryset)
    page_ids = [c.id for c in pagination.results]
    metadata = await _collection_metadata(page_ids)
    auto_assigned_ids = await _ids_with_auto_assigned_meetings(page_ids)
    uncategorized_count = await Meeting.filter(
        organization_id=current_user.organization_id, collection_id__isnull=True
    ).count()
    return MeetingCollectionListResponse(
        collections=[
            _list_item_response(
                c,
                meeting_count=metadata.get(c.id, (0, None))[0],
                last_meeting_at=metadata.get(c.id, (0, None))[1],
                auto_assigned=c.id in auto_assigned_ids,
            )
            for c in pagination.results
        ],
        uncategorized_count=uncategorized_count,
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@router.get("/meetings_collections/{collection_id}", response_model=MeetingCollectionShowResponse)
async def api_meetings_collections_show(
    collection: MeetingCollection = Depends(get_api_meeting_collection),
    current_user: User = Depends(get_current_user),
    cursor: str | None = Query(None),
):
    meetings_queryset = (
        Meeting.by_organization_or_user(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
        )
        .filter(Meeting.filters.by_collection(collection.id))
        .filter(Meeting.filters.by_past())
        .prefetch_related("organization", "workspace__collaborators__user", "jobs__job", "recording", "collection")
        .order_by("-scheduled_at", "id")
    )
    pagination = await Pagination.create(Meeting, cursor=cursor, queryset=meetings_queryset)
    summary = await _single_collection_summary(collection)
    return MeetingCollectionShowResponse(
        collection=summary,
        meetings=await _meeting_list_responses(
            pagination.results,
            current_user_id=current_user.id,
            organization_id=current_user.organization_id,
        ),
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@router.post(
    "/meetings_collections",
    response_model=MeetingCollectionListItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_meetings_collections_create(
    body: CreateCollectionRequest,
    current_user: User = Depends(get_current_user),
):
    collection = await MeetingCollection.create(
        organization_id=current_user.organization_id,
        title=body.title,
        description=body.description,
    )
    return await _single_collection_summary(collection)


@router.patch("/meetings_collections/{collection_id}", response_model=MeetingCollectionListItemResponse)
async def api_meetings_collections_update(
    body: UpdateCollectionRequest,
    collection: MeetingCollection = Depends(get_api_meeting_collection),
):
    fields_set = body.model_fields_set
    if body.title is not None:
        collection.title = body.title
    if "description" in fields_set:
        collection.description = body.description
    if collection.changes:
        await collection.save()
    return await _single_collection_summary(collection)


@router.delete("/meetings_collections/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_meetings_collections_delete(
    collection: MeetingCollection = Depends(get_api_meeting_collection),
):
    if await Meeting.exists(collection_id=collection.id, collection_auto_assigned=True):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete a collection with auto-assigned meetings",
        )
    await collection.delete()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
