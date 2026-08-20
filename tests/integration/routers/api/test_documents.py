from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status

from app.jobs.content import ContentIndexingJob
from app.models.collaboration.workspace import Visit
from app.models.workspaces.documents import Document, DocumentComment
from config.enums import Sharing
from config.settings import settings
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_document, create_user


@pytest.mark.asyncio
async def test_updating_document_title(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    document = await create_document(
        title="Original Title",
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    # Creator can update the title
    response = await client.patch(f"/api/documents/{document.id}", json={"title": "New Title"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["title"] == "New Title"

    await document.refresh_from_db()
    assert document.title == "New Title"

    # Non-creator collaborator can also update the title
    await create_collaborator(workspace_id=document.workspace_id, added_by_id=creator.id, user_id=other_user.id)
    with client.current_user_as(other_user):
        response = await client.patch(f"/api/documents/{document.id}", json={"title": "Collaborator Title"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["title"] == "Collaborator Title"

    await document.refresh_from_db()
    assert document.title == "Collaborator Title"

    # Title changes trigger search re-indexing
    assert any(isinstance(job.job_definition, ContentIndexingJob) for job in background_jobs.completed)

    # Non-collaborator org member cannot update title on org-shared document
    non_collaborator = await create_user(organization_id=creator.organization_id)
    with client.current_user_as(non_collaborator):
        response = await client.patch(f"/api/documents/{document.id}", json={"title": "Org Member Title"})
        assert response.status_code == status.HTTP_403_FORBIDDEN

    await document.refresh_from_db()
    assert document.title == "Collaborator Title"


@pytest.mark.asyncio
async def test_documents_index_empty(client: AppClient):
    await client.get_default_user()

    response = await client.get("/api/documents")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body == {"documents": [], "next_cursor": None, "has_more": False}


@pytest.mark.asyncio
async def test_documents_index_listing(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)

    own_doc = await create_document(
        title="My Doc",
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    collab_doc = await create_document(
        title="Collab Doc",
        creator_id=other_user.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )
    await create_collaborator(workspace_id=collab_doc.workspace_id, added_by_id=other_user.id, user_id=creator.id)
    await create_document(
        title="Org Doc",
        creator_id=other_user.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    # Private doc by another user we don't collaborate on — not accessible, so excluded from every filter
    await create_document(
        title="Hidden Doc",
        creator_id=other_user.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )

    # Add a collaborator + open + resolved comments + visit so we can assert item shape on My Doc
    await create_collaborator(workspace_id=own_doc.workspace_id, added_by_id=creator.id, user_id=other_user.id)
    await DocumentComment.create(
        document_id=own_doc.id,
        user_id=creator.id,
        content="Open comment",
        quoted_text="My",
        comment_mark_id="mark-open",
    )
    resolved = await DocumentComment.create(
        document_id=own_doc.id,
        user_id=creator.id,
        content="Resolved comment",
        quoted_text="My",
        comment_mark_id="mark-resolved",
    )
    resolved.resolved_at = datetime.now(UTC)
    await resolved.save(update_fields=["resolved_at"])
    await Visit.record(creator.id, own_doc.workspace_id)

    # Default (mine): only documents created by the current user
    response = await client.get("/api/documents")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert {d["title"] for d in data["documents"]} == {"My Doc"}

    own_item = next(d for d in data["documents"] if d["id"] == str(own_doc.id))
    assert own_item["title"] == "My Doc"
    assert own_item["author_display_name"] == "Me"
    assert own_item["sharing"] == Sharing.ORGANIZATION.value
    assert own_item["comment_count"] == 1
    # Creator + the explicitly added collaborator
    assert own_item["collaborator_count"] == 2
    assert own_item["last_viewed_at"] is not None
    assert own_item["source_url"] == f"/documents/{own_doc.id}"

    # Anyone: every document the user can access — Hidden Doc (another user's private
    # doc we don't collaborate on) is not accessible, so it's excluded.
    response = await client.get("/api/documents?filter=anyone")
    assert {d["title"] for d in response.json()["documents"]} == {"My Doc", "Collab Doc", "Org Doc"}

    # Mine: only documents created by current user
    response = await client.get("/api/documents?filter=mine")
    assert {d["title"] for d in response.json()["documents"]} == {"My Doc"}

    # Others: accessible documents I didn't create — excludes my own "My Doc" and the
    # inaccessible Hidden Doc.
    response = await client.get("/api/documents?filter=others")
    assert {d["title"] for d in response.json()["documents"]} == {"Collab Doc", "Org Doc"}

    # Other org members see org-shared + their own (and "Me" resolves per-viewer)
    with client.current_user_as(other_user):
        response = await client.get("/api/documents?filter=anyone")
        data = response.json()
        assert {d["title"] for d in data["documents"]} == {"My Doc", "Collab Doc", "Org Doc", "Hidden Doc"}
        own_item = next(d for d in data["documents"] if d["id"] == str(own_doc.id))
        assert own_item["author_display_name"] == creator.display_name
        # Other user has not visited this workspace
        assert own_item["last_viewed_at"] is None


@pytest.mark.asyncio
async def test_documents_index_sorts_by_last_viewed_by_me(client: AppClient):
    creator = await client.get_default_user()

    # Create them in the reverse of the expected order so ordering by anything
    # other than last-viewed (e.g. created_at/updated_at) would fail the assert.
    recently_viewed = await create_document(
        title="Recently viewed", creator_id=creator.id, organization_id=creator.organization_id
    )
    viewed_earlier = await create_document(
        title="Viewed earlier", creator_id=creator.id, organization_id=creator.organization_id
    )
    never_older = await create_document(
        title="Never viewed (older)", creator_id=creator.id, organization_id=creator.organization_id
    )
    never_newer = await create_document(
        title="Never viewed (newer)", creator_id=creator.id, organization_id=creator.organization_id
    )

    now = datetime.now(UTC)
    await Visit.record(creator.id, recently_viewed.workspace_id)
    await Visit.filter(user_id=creator.id, workspace_id=recently_viewed.workspace_id).update(updated_at=now)
    await Visit.record(creator.id, viewed_earlier.workspace_id)
    await Visit.filter(user_id=creator.id, workspace_id=viewed_earlier.workspace_id).update(
        updated_at=now - timedelta(hours=1)
    )
    await Document.filter(id=never_newer.id).update(updated_at=now)
    await Document.filter(id=never_older.id).update(updated_at=now - timedelta(hours=1))

    # Opened documents come first (most recent open at the top). Documents the user
    # has never opened sort last, ordered among themselves by most recently updated.
    response = await client.get("/api/documents")
    assert response.status_code == status.HTTP_200_OK
    titles = [d["title"] for d in response.json()["documents"]]
    assert titles == ["Recently viewed", "Viewed earlier", "Never viewed (newer)", "Never viewed (older)"]


@pytest.mark.asyncio
async def test_documents_index_pagination(client: AppClient):
    per_page = settings.pagination_default_per_page
    creator = await client.get_default_user()
    total = per_page + 5
    for i in range(total):
        await create_document(
            title=f"Doc {i:02d}",
            creator_id=creator.id,
            organization_id=creator.organization_id,
            sharing=Sharing.PRIVATE,
        )

    response = await client.get("/api/documents?filter=mine")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["documents"]) == per_page
    assert data["has_more"] is True
    assert data["next_cursor"] is not None
    first_page_ids = {d["id"] for d in data["documents"]}

    response = await client.get(f"/api/documents?filter=mine&cursor={data['next_cursor']}")
    page2 = response.json()
    assert len(page2["documents"]) == 5
    assert page2["has_more"] is False
    assert page2["next_cursor"] is None
    assert first_page_ids.isdisjoint({d["id"] for d in page2["documents"]})


@pytest.mark.asyncio
async def test_documents_index_requires_authentication(client: AppClient):
    with client.logged_out():
        response = await client.get("/api/documents")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_documents_show_returns_metadata(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    document = await create_document(
        title="My Doc",
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    await create_collaborator(workspace_id=document.workspace_id, added_by_id=creator.id, user_id=other_user.id)

    # Creator sees themselves as both collaborator and creator
    response = await client.get(f"/api/documents/{document.id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] == str(document.id)
    assert body["title"] == "My Doc"
    assert body["sharing"] == Sharing.ORGANIZATION.value
    assert body["is_collaborator"] is True
    assert body["is_creator"] is True
    assert body["workspace_id"] == str(document.workspace_id)
    assert body["collaborator_count"] == 2
    assert {c["id"] for c in body["collaborators"]} == {str(creator.id), str(other_user.id)}
    assert body["request_access_url"].endswith(f"/workspaces/{document.workspace_id}/collaborators/access")
    assert body["upload_url"].endswith(f"/workspaces/{document.workspace_id}/attachments")
    # Content lives at the dedicated /content endpoint
    assert "content_markdown" not in body

    # Non-collaborator org member can see the metadata but isn't flagged as collaborator
    non_collab = await create_user(organization_id=creator.organization_id)
    with client.current_user_as(non_collab):
        response = await client.get(f"/api/documents/{document.id}")
    body = response.json()
    assert body["is_collaborator"] is False
    assert body["is_creator"] is False


@pytest.mark.asyncio
async def test_creating_a_document(client: AppClient):
    creator = await client.get_default_user()

    # Empty body → "Untitled document", creator is sole collaborator
    response = await client.post("/api/documents", json={})
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["title"] == "Untitled document"
    assert body["sharing"] == Sharing.PRIVATE.value
    assert body["is_creator"] is True
    assert body["is_collaborator"] is True
    assert body["collaborator_count"] == 1
    assert {c["id"] for c in body["collaborators"]} == {str(creator.id)}
    assert body["upload_url"].endswith(f"/workspaces/{body['workspace_id']}/attachments")

    document = await Document.get(id=body["id"])
    assert document.creator_id == creator.id

    # Title + content → title persisted, content seeded into the live document
    response = await client.post("/api/documents", json={"title": "My New Doc", "content": "# Hello world"})
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["title"] == "My New Doc"

    document = await Document.get(id=body["id"])
    assert "Hello world" in await document.get_live_document_markdown()

    # Whitespace-only title falls back to "Untitled document"
    response = await client.post("/api/documents", json={"title": "   "})
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["title"] == "Untitled document"

    # Title length is capped, matching the PATCH validation
    response = await client.post("/api/documents", json={"title": "x" * 1001})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_creating_a_document_requires_authentication(client: AppClient):
    with client.logged_out():
        response = await client.post("/api/documents", json={})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_documents_content_endpoint(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    # Both collaborators and non-collaborators with visibility can fetch content
    response = await client.get(f"/api/documents/{document.id}/content")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert isinstance(body["markdown"], str)

    with client.current_user_as(other_user):
        response = await client.get(f"/api/documents/{document.id}/content")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_documents_show_missing_returns_404(client: AppClient):
    await client.get_default_user()
    response = await client.get(f"/api/documents/{uuid4()}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_documents_show_access_control(client: AppClient):
    """Now that /documents/{id} serves the SPA shell unconditionally, the show
    endpoint is the sole access gate. For a same-org non-collaborator on a private
    doc, RequestAccessError resolves to a 403 carrying request_access_url (JSON, so
    the React client can offer to request access rather than chase an HTML
    redirect); a cross-org user still gets a 404."""
    creator = await client.get_default_user()
    private_doc = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )

    same_org_user = await create_user(organization_id=creator.organization_id)
    with client.current_user_as(same_org_user):
        response = await client.get(f"/api/documents/{private_doc.id}", follow_redirects=False)
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["request_access_url"].endswith(
            f"/workspaces/{private_doc.workspace_id}/collaborators/access"
        )

    cross_org_user = await create_user()
    with client.current_user_as(cross_org_user):
        response = await client.get(f"/api/documents/{private_doc.id}", follow_redirects=False)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_updating_document_sharing(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    document = await create_document(
        title="Doc",
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )

    response = await client.patch(f"/api/documents/{document.id}", json={"sharing": "organization"})
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["sharing"] == Sharing.ORGANIZATION.value
    # PATCH returns the full show response — same shape as GET — so clients
    # don't have to refetch to refresh derived state.
    assert body["creator"]["id"] == str(creator.id)
    assert body["collaborator_count"] >= 1
    assert "updated_at" in body
    assert "content_markdown" not in body

    await document.refresh_from_db()
    assert document.sharing == Sharing.ORGANIZATION

    # Title + sharing together
    response = await client.patch(
        f"/api/documents/{document.id}",
        json={"title": "Renamed", "sharing": "organization"},
    )
    assert response.status_code == status.HTTP_200_OK
    await document.refresh_from_db()
    assert document.title == "Renamed"
    assert document.sharing == Sharing.ORGANIZATION

    # Sharing is a collaborator-level action, not creator-only. Pinned so the
    # guard doesn't accidentally get tightened to `creator_id == current_user.id`.
    collaborator_user = await create_user(organization_id=creator.organization_id)
    await create_collaborator(workspace_id=document.workspace_id, added_by_id=creator.id, user_id=collaborator_user.id)
    with client.current_user_as(collaborator_user):
        response = await client.patch(f"/api/documents/{document.id}", json={"sharing": "private"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["sharing"] == Sharing.PRIVATE.value
    await document.refresh_from_db()
    assert document.sharing == Sharing.PRIVATE

    # Flip back to organization so the non-collaborator can see the doc and
    # we reach the 403 (otherwise get_document raises RequestAccessError → 302).
    await client.patch(f"/api/documents/{document.id}", json={"sharing": "organization"})
    with client.current_user_as(other_user):
        response = await client.patch(f"/api/documents/{document.id}", json={"sharing": "private"})
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_update_request_must_set_at_least_one_field(client: AppClient):
    creator = await client.get_default_user()
    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )

    response = await client.patch(f"/api/documents/{document.id}", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_deleting_a_document(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )

    # Non-creator collaborator cannot delete
    await create_collaborator(workspace_id=document.workspace_id, added_by_id=creator.id, user_id=other_user.id)
    with client.current_user_as(other_user):
        response = await client.delete(f"/api/documents/{document.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    response = await client.delete(f"/api/documents/{document.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    # Soft-deleted: removed from default manager but still in the DB
    assert await Document.all().count() == 0
    assert await Document.deleted.all().count() == 1

    # Subsequent fetches 404
    response = await client.get(f"/api/documents/{document.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
