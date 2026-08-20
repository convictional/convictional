import pytest
from fastapi import status

from app.models.collaboration.content import IndexMetadata, SearchableData
from config.enums import ContentCategory, ContentType, Sharing
from tests.helpers.app import AppClient
from tests.helpers.factories import create_content, create_user

pytestmark = pytest.mark.real_embeddings


@pytest.mark.asyncio
async def test_search_returns_results(client: AppClient):
    user = await client.get_default_user()
    organization = user.organization

    content = await create_content(organization=organization)
    await content.indexer.index(
        SearchableData("Quarterly Planning", "Our Q2 planning document", str(content.source_id), "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
    )

    response = await client.get("/api/search?q=Quarterly Planning")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["query"] == "Quarterly Planning"
    assert data["content_type"] is None
    assert len(data["results"]) >= 1
    assert any(r["id"] == str(content.id) for r in data["results"])

    result = next(r for r in data["results"] if r["id"] == str(content.id))
    assert result["title"] == "Quarterly Planning"
    assert result["content_type"] == "document"


@pytest.mark.asyncio
async def test_search_filters_by_content_type(client: AppClient):
    user = await client.get_default_user()
    organization = user.organization

    doc = await create_content(organization=organization)
    await doc.indexer.index(
        SearchableData("Budget Doc", "Annual budget document", str(doc.source_id), "Alice"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.DOCUMENT, Sharing.ORGANIZATION),
    )

    meeting = await create_content(organization=organization)
    await meeting.indexer.index(
        SearchableData("Budget Meeting", "Meeting about annual budget", str(meeting.source_id), "Bob"),
        IndexMetadata(ContentCategory.ACTIVITY, ContentType.MEETING, Sharing.ORGANIZATION),
    )

    response = await client.get("/api/search?q=budget&content_type=document")
    data = response.json()
    assert data["content_type"] == "document"
    assert len(data["results"]) >= 1
    assert all(r["content_type"] == "document" for r in data["results"])


@pytest.mark.asyncio
async def test_search_excludes_disallowed_content_types(client: AppClient):
    user = await client.get_default_user()
    organization = user.organization

    # Index a content type not in the allowed list
    post_comment = await create_content(organization=organization)
    await post_comment.indexer.index(
        SearchableData("Comment on report", "This report needs revision", str(post_comment.source_id), "Alice"),
        IndexMetadata(ContentCategory.ACTIVITY, ContentType.POST_COMMENT, Sharing.ORGANIZATION),
    )

    response = await client.get("/api/search?q=report needs revision")
    data = response.json()
    assert not any(r["content_type"] == "post_comment" for r in data["results"])


@pytest.mark.asyncio
async def test_search_respects_access_control(client: AppClient):
    user = await client.get_default_user()
    organization = user.organization
    other_user = await create_user(organization_id=organization.id)

    # Private content only visible to other_user
    private = await create_content(organization=organization)
    await private.indexer.index(
        SearchableData("Secret Project", "Top secret project details", str(private.source_id), "Bob"),
        IndexMetadata(
            ContentCategory.DOCUMENT,
            ContentType.DOCUMENT,
            force_sharing=Sharing.PRIVATE,
            allowed_user_ids=[other_user.id],
        ),
    )

    response = await client.get("/api/search?q=Secret Project")
    data = response.json()
    assert not any(r["id"] == str(private.id) for r in data["results"])


@pytest.mark.asyncio
async def test_search_empty_query(client: AppClient):
    response = await client.get("/api/search?q=")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["results"] == []

    response = await client.get("/api/search?q=a")
    data = response.json()
    assert data["results"] == []


@pytest.mark.asyncio
async def test_search_returns_empty_for_disallowed_content_type_filter(client: AppClient):
    response = await client.get("/api/search?q=test&content_type=meeting_transcript")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["results"] == []


@pytest.mark.asyncio
async def test_search_decisions_are_filter_only(client: AppClient):
    user = await client.get_default_user()
    organization = user.organization

    decision = await create_content(organization=organization)
    await decision.indexer.index(
        SearchableData("Decision in Roadmap", "We decided to ship in Q3", str(decision.source_id), "Alice"),
        IndexMetadata(
            ContentCategory.ACTIVITY,
            ContentType.DECISION,
            Sharing.ORGANIZATION,
            comment_gid="gid://convictional/PostComment/abc",
        ),
    )

    # Filtered to decisions: the decision surfaces.
    filtered = (await client.get("/api/search?q=decided to ship&content_type=decision")).json()
    assert filtered["content_type"] == "decision"
    assert any(r["id"] == str(decision.id) for r in filtered["results"])

    # Unfiltered ("all") search: the decision is absent.
    unfiltered = (await client.get("/api/search?q=decided to ship")).json()
    assert not any(r["content_type"] == "decision" for r in unfiltered["results"])


@pytest.mark.asyncio
async def test_search_decisions_respect_access_control(client: AppClient):
    user = await client.get_default_user()
    organization = user.organization
    other_user = await create_user(organization_id=organization.id)

    decision = await create_content(organization=organization)
    await decision.indexer.index(
        SearchableData("Decision in Secret", "Private decision body", str(decision.source_id), "Bob"),
        IndexMetadata(
            ContentCategory.ACTIVITY,
            ContentType.DECISION,
            force_sharing=Sharing.PRIVATE,
            allowed_user_ids=[other_user.id],
        ),
    )

    data = (await client.get("/api/search?q=Private decision body&content_type=decision")).json()
    assert not any(r["id"] == str(decision.id) for r in data["results"])


@pytest.mark.asyncio
async def test_search_metadata_and_shared_with_me(client: AppClient):
    user = await client.get_default_user()
    organization = user.organization
    other_user = await create_user(organization_id=organization.id)

    # Email thread owned by other_user — should be "shared_with_me" for client user
    shared_thread = await create_content(organization=organization)
    await shared_thread.indexer.index(
        SearchableData("Metadata Test Thread", "Thread about metadata", str(shared_thread.source_id), "Other Person"),
        IndexMetadata(
            ContentCategory.ACTIVITY,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            owner_user_id=other_user.id,
            message_count=5,
            has_calendar_invite=True,
            is_automated_sender=False,
            scheduled_at="2026-05-01T10:00:00Z",
        ),
    )

    # Email thread owned by client user — should NOT be "shared_with_me"
    own_thread = await create_content(organization=organization)
    await own_thread.indexer.index(
        SearchableData("Metadata Own Thread", "My own thread", str(own_thread.source_id), "Me"),
        IndexMetadata(
            ContentCategory.ACTIVITY,
            ContentType.EMAIL_THREAD,
            Sharing.ORGANIZATION,
            owner_user_id=user.id,
            message_count=2,
        ),
    )

    response = await client.get("/api/search?q=Metadata")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "hero_count" in data

    shared_result = next(r for r in data["results"] if r["id"] == str(shared_thread.id))
    own_result = next(r for r in data["results"] if r["id"] == str(own_thread.id))

    # shared_with_me computed server-side
    assert shared_result["shared_with_me"] is True
    assert own_result["shared_with_me"] is False

    # Allowlisted metadata fields present
    assert shared_result["metadata"]["message_count"] == 5
    assert shared_result["metadata"]["has_calendar_invite"] is True

    # Internal fields excluded from metadata
    assert "is_automated_sender" not in shared_result["metadata"]
    assert "owner_user_id" not in shared_result["metadata"]
