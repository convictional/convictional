from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status

from app.models.workspaces.meetings import Meeting, MeetingCollection
from tests.helpers.app import AppClient
from tests.helpers.factories import create_meeting, create_meeting_collection, create_organization


@pytest.mark.asyncio
async def test_index_returns_empty_envelope(client: AppClient):
    response = await client.get("/api/meetings_collections")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "collections": [],
        "uncategorized_count": 0,
        "next_cursor": None,
        "has_more": False,
    }


@pytest.mark.asyncio
async def test_index_returns_metadata_and_excludes_cross_org(client: AppClient):
    user = await client.get_default_user()
    other_org = await create_organization()

    plain = await create_meeting_collection(
        organization_id=user.organization_id, title="A: Plain", description="No meetings yet"
    )
    populated = await create_meeting_collection(
        organization_id=user.organization_id, title="B: Populated", description=None
    )
    auto = await create_meeting_collection(organization_id=user.organization_id, title="C: Auto-managed")
    await create_meeting_collection(organization_id=other_org.id, title="D: Cross-org")

    last_scheduled = datetime.now(UTC) - timedelta(days=1)
    await create_meeting(
        title="In B",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=last_scheduled - timedelta(days=2),
        scheduled_end_at=last_scheduled - timedelta(days=2, hours=-1),
        collection_id=populated.id,
    )
    await create_meeting(
        title="Recent in B",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=last_scheduled,
        scheduled_end_at=last_scheduled + timedelta(hours=1),
        collection_id=populated.id,
    )
    await create_meeting(
        title="Auto",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=last_scheduled,
        scheduled_end_at=last_scheduled + timedelta(hours=1),
        collection_id=auto.id,
        collection_auto_assigned=True,
    )
    await create_meeting(
        title="Unfiled",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=last_scheduled,
        scheduled_end_at=last_scheduled + timedelta(hours=1),
    )

    response = await client.get("/api/meetings_collections")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert [c["id"] for c in body["collections"]] == [str(plain.id), str(populated.id), str(auto.id)]
    assert body["uncategorized_count"] == 1

    by_id = {c["id"]: c for c in body["collections"]}
    assert by_id[str(plain.id)] == {
        "id": str(plain.id),
        "title": "A: Plain",
        "description": "No meetings yet",
        "meeting_count": 0,
        "last_meeting_at": None,
        "auto_assigned": False,
    }
    assert by_id[str(populated.id)]["meeting_count"] == 2
    assert by_id[str(populated.id)]["last_meeting_at"] is not None
    assert by_id[str(populated.id)]["auto_assigned"] is False
    assert by_id[str(auto.id)]["meeting_count"] == 1
    assert by_id[str(auto.id)]["auto_assigned"] is True


@pytest.mark.asyncio
async def test_show_returns_collection_with_paginated_past_meetings(client: AppClient):
    user = await client.get_default_user()
    collection = await create_meeting_collection(
        organization_id=user.organization_id, title="Standups", description="Daily standups"
    )

    past_scheduled = datetime.now(UTC) - timedelta(days=1)
    future_scheduled = datetime.now(UTC) + timedelta(days=1)
    past_meeting = await create_meeting(
        title="Past in collection",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=past_scheduled,
        scheduled_end_at=past_scheduled + timedelta(hours=1),
        collection_id=collection.id,
    )
    await create_meeting(
        title="Upcoming in collection",
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=future_scheduled,
        scheduled_end_at=future_scheduled + timedelta(hours=1),
        collection_id=collection.id,
    )

    response = await client.get(f"/api/meetings_collections/{collection.id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["collection"]["id"] == str(collection.id)
    # Title/description back the React index header for real-collection deep links.
    assert body["collection"]["title"] == "Standups"
    assert body["collection"]["description"] == "Daily standups"
    assert body["collection"]["meeting_count"] == 2
    # Only past meetings render in the show payload — upcoming meetings live
    # behind the generic /api/meetings?scheduled_after=... query.
    assert [m["id"] for m in body["meetings"]] == [str(past_meeting.id)]
    assert body["meetings"][0]["agenda"] == ""


@pytest.mark.asyncio
async def test_show_returns_404_for_unknown_or_cross_org(client: AppClient):
    response = await client.get(f"/api/meetings_collections/{uuid4()}")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    other_org = await create_organization()
    cross_org = await create_meeting_collection(organization_id=other_org.id)
    response = await client.get(f"/api/meetings_collections/{cross_org.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_validates_title_and_returns_201(client: AppClient):
    response = await client.post("/api/meetings_collections", json={"title": ""})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    response = await client.post(
        "/api/meetings_collections", json={"title": "Customer interviews", "description": "All of them"}
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["title"] == "Customer interviews"
    assert body["description"] == "All of them"
    assert body["meeting_count"] == 0
    assert body["last_meeting_at"] is None
    assert body["auto_assigned"] is False
    assert await MeetingCollection.exists(id=body["id"])


@pytest.mark.asyncio
async def test_patch_distinguishes_omitted_from_null(client: AppClient):
    user = await client.get_default_user()
    collection = await create_meeting_collection(
        organization_id=user.organization_id, title="Original", description="Original notes"
    )

    response = await client.patch(f"/api/meetings_collections/{collection.id}", json={"title": "Renamed"})
    assert response.status_code == status.HTTP_200_OK
    refreshed = await MeetingCollection.get(id=collection.id)
    assert refreshed.title == "Renamed"
    assert refreshed.description == "Original notes"

    response = await client.patch(f"/api/meetings_collections/{collection.id}", json={"description": None})
    assert response.status_code == status.HTTP_200_OK
    refreshed = await MeetingCollection.get(id=collection.id)
    assert refreshed.title == "Renamed"
    assert refreshed.description is None

    # A PATCH with no recognized fields is a semantic no-op and must be rejected.
    response = await client.patch(f"/api/meetings_collections/{collection.id}", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_patch_returns_404_for_cross_org(client: AppClient):
    other_org = await create_organization()
    collection = await create_meeting_collection(organization_id=other_org.id)
    response = await client.patch(f"/api/meetings_collections/{collection.id}", json={"title": "Hijacked"})
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_returns_204_unless_auto_assigned(client: AppClient):
    user = await client.get_default_user()
    empty = await create_meeting_collection(organization_id=user.organization_id, title="Empty")
    manual = await create_meeting_collection(organization_id=user.organization_id, title="Manual")
    auto = await create_meeting_collection(organization_id=user.organization_id, title="Auto")

    scheduled_at = datetime.now(UTC) - timedelta(days=1)
    manual_meeting = await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        collection_id=manual.id,
    )
    await create_meeting(
        creator_id=user.id,
        organization_id=user.organization_id,
        scheduled_at=scheduled_at,
        scheduled_end_at=scheduled_at + timedelta(hours=1),
        collection_id=auto.id,
        collection_auto_assigned=True,
    )

    response = await client.delete(f"/api/meetings_collections/{empty.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not await MeetingCollection.exists(id=empty.id)

    response = await client.delete(f"/api/meetings_collections/{manual.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not await MeetingCollection.exists(id=manual.id)
    # ON DELETE SET NULL on the Meeting.collection FK leaves the meeting itself intact.
    refreshed = await Meeting.get(id=manual_meeting.id)
    assert refreshed.collection_id is None

    response = await client.delete(f"/api/meetings_collections/{auto.id}")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert await MeetingCollection.exists(id=auto.id)


@pytest.mark.asyncio
async def test_delete_returns_404_for_cross_org(client: AppClient):
    other_org = await create_organization()
    cross_org = await create_meeting_collection(organization_id=other_org.id)
    response = await client.delete(f"/api/meetings_collections/{cross_org.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert await MeetingCollection.exists(id=cross_org.id)


@pytest.mark.asyncio
async def test_index_paginates(client: AppClient):
    user = await client.get_default_user()
    # `pagination_default_per_page` is 30 in settings — create one full page
    # plus a tail so we exercise both pages.
    for i in range(35):
        await create_meeting_collection(organization_id=user.organization_id, title=f"Collection {i:02d}")

    first = await client.get("/api/meetings_collections")
    assert first.status_code == status.HTTP_200_OK
    first_body = first.json()
    assert len(first_body["collections"]) == 30
    assert first_body["has_more"] is True
    assert first_body["next_cursor"] is not None

    second = await client.get("/api/meetings_collections", params={"cursor": first_body["next_cursor"]})
    assert second.status_code == status.HTTP_200_OK
    second_body = second.json()
    assert len(second_body["collections"]) == 5
    assert second_body["has_more"] is False
    assert second_body["next_cursor"] is None
