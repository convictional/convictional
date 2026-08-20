from unittest.mock import patch
from uuid import uuid4 as generate_uuid

import pytest
from fastapi import status

from app.models.collaboration.workspace import Attachment
from config.enums import Sharing
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_collaborator,
    create_document,
    create_email_thread,
    create_meeting,
    create_user,
)


@pytest.mark.asyncio
async def test_attachment_upload(client: AppClient):
    creator = await client.get_default_user()
    meeting = await create_meeting(title="Movie", creator_id=creator.id, organization_id=creator.organization_id)
    csv_bytes = b"Title,Year\nThe Shawshank Redemption,1994\nThe Godfather,1972\nThe Dark Knight,2008\n"
    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/attachments",
        files={"files": ("test.csv", csv_bytes, "text/csv")},
    )
    assert response.status_code == status.HTTP_201_CREATED
    response_json = response.json()
    assert "attachments" in response_json
    assert len(response_json["attachments"]) == 1
    assert "download_url" in response_json["attachments"][0]

    attachments = await Attachment.filter(workspace_id=meeting.workspace_id).all()
    assert len(attachments) == 1
    assert attachments[0].user_id == creator.id


@pytest.mark.asyncio
async def test_attachment_upload_rejects_oversized(client: AppClient):
    creator = await client.get_default_user()
    meeting = await create_meeting(title="Movie", creator_id=creator.id, organization_id=creator.organization_id)
    # Shrink the limit rather than allocate a real 25 MB payload.
    with patch("app.routers.api.workspace_attachments.MAX_ATTACHMENT_BYTES", 8):
        response = await client.post(
            f"/api/workspaces/{meeting.workspace_id}/attachments",
            files={"files": ("big.txt", b"way too many bytes", "text/plain")},
        )
    assert response.status_code == status.HTTP_413_CONTENT_TOO_LARGE

    # Nothing was stored — the request is rejected before any blob or row is created.
    assert await Attachment.filter(workspace_id=meeting.workspace_id).count() == 0


@pytest.mark.asyncio
async def test_attachment_claiming(client: AppClient):
    creator = await client.get_default_user()
    claim_id = str(generate_uuid())

    # Create an attachment not associated with any workspace
    csv_bytes = b"Title,Year\nThe Shawshank Redemption,1994\nThe Godfather,1972\nThe Dark Knight,2008\n"
    response = await client.post(
        "/api/workspaces/attachments",
        files={"files": ("test.csv", csv_bytes, "text/csv")},
        data={"claim_id": claim_id},
    )
    assert response.status_code == status.HTTP_201_CREATED

    attachments = await Attachment.all()
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment.user_id == creator.id
    assert attachment.claim_id is not None
    assert attachment.workspace_id is None

    # Now, create a workspace and attach the file
    response = await client.post(
        "/api/posts",
        json={
            "title": "Movies",
            "content": "What are your favorite movies?",
            "attachment_claim_id": claim_id,
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Attachment is claimed to the workspace
    await attachment.refresh_from_db()
    assert attachment.user_id == creator.id
    assert attachment.claim_id is None
    assert attachment.workspace_id is not None
    assert attachment.comment_gid is not None


@pytest.mark.asyncio
async def test_attachment_claiming_security(client: AppClient):
    creator = await client.get_default_user()
    claim_id = str(generate_uuid())

    # Create an attachment not associated with any workspace
    csv_bytes = b"Title,Year\nThe Shawshank Redemption,1994\nThe Godfather,1972\nThe Dark Knight,2008\n"
    response = await client.post(
        "/api/workspaces/attachments",
        files={"files": ("test.csv", csv_bytes, "text/csv")},
        data={"claim_id": claim_id},
    )
    assert response.status_code == status.HTTP_201_CREATED

    attachments = await Attachment.all()
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment.user_id == creator.id

    # As another user, create a workspace
    user = await create_user(organization_id=creator.organization_id)

    with client.current_user_as(user):
        response = await client.post(
            "/api/posts",
            json={
                "title": "Movies",
                "content": "What are your favorite movies?",
                "attachment_claim_id": claim_id,
            },
        )
        assert response.status_code == status.HTTP_201_CREATED

    # Attachment is not claimed to the workspace
    await attachment.refresh_from_db()
    assert attachment.user_id == creator.id
    assert attachment.claim_id is not None
    assert attachment.workspace_id is None


@pytest.mark.asyncio
async def test_attachment_claiming_comments(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    claim_id = str(generate_uuid())

    # Upload an attachment scoped to the email thread's workspace
    csv_bytes = b"Title,Year\nThe Shawshank Redemption,1994\nThe Godfather,1972\nThe Dark Knight,2008\n"
    response = await client.post(
        f"/api/workspaces/{thread.workspace_id}/attachments",
        files={"files": ("test.csv", csv_bytes, "text/csv")},
        data={"claim_id": claim_id},
    )
    assert response.status_code == status.HTTP_201_CREATED

    attachments = await Attachment.all()
    assert len(attachments) == 1
    attachment = attachments[0]
    assert attachment.user_id == creator.id
    assert attachment.claim_id is not None
    assert attachment.workspace_id is not None

    # Create an email-thread comment that claims the uploaded attachment
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "Great movies!", "attachment_claim_id": claim_id},
    )
    assert response.status_code == status.HTTP_201_CREATED

    # The attachment is claimed to the comment, and surfaced in the comment response
    await attachment.refresh_from_db()
    assert attachment.user_id == creator.id
    assert attachment.claim_id is None
    assert attachment.comment_gid is not None
    assert len(response.json()["attachments"]) == 1


@pytest.mark.asyncio
async def test_document_image_accessible_to_collaborators(client: AppClient):
    creator = await client.get_default_user()
    collaborator = await create_user(organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )
    await create_collaborator(workspace_id=document.workspace_id, added_by_id=creator.id, user_id=collaborator.id)

    # Creator uploads a file via the workspace-scoped endpoint (as the document editor does)
    response = await client.post(
        f"/api/workspaces/{document.workspace_id}/attachments",
        files={"files": ("photo.svg", b"<svg></svg>", "image/svg+xml")},
    )
    assert response.status_code == status.HTTP_201_CREATED
    download_url = response.json()["attachments"][0]["download_url"]

    # Creator can download
    response = await client.get(download_url, follow_redirects=False)
    assert response.status_code == status.HTTP_302_FOUND

    # Collaborator can also download — this was the bug (previously 404)
    with client.current_user_as(collaborator):
        response = await client.get(download_url, follow_redirects=False)
        assert response.status_code == status.HTTP_302_FOUND

    # Non-collaborator in same org cannot download
    outsider = await create_user(organization_id=creator.organization_id)
    with client.current_user_as(outsider):
        response = await client.get(download_url, follow_redirects=False)
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_multiple_attachment_upload(client: AppClient):
    creator = await client.get_default_user()
    meeting = await create_meeting(title="Movie", creator_id=creator.id, organization_id=creator.organization_id)

    # Upload multiple files at once
    file1_bytes = b"File 1 content"
    file2_bytes = b"File 2 content"
    file3_bytes = b"File 3 content"

    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/attachments",
        files=[
            ("files", ("file1.txt", file1_bytes, "text/plain")),
            ("files", ("file2.txt", file2_bytes, "text/plain")),
            ("files", ("file3.txt", file3_bytes, "text/plain")),
        ],
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Verify response structure
    response_json = response.json()
    assert "attachments" in response_json
    assert len(response_json["attachments"]) == 3

    # Verify all attachments have download URLs
    for attachment_data in response_json["attachments"]:
        assert "download_url" in attachment_data
        assert "/workspaces/" in attachment_data["download_url"]
        assert "/attachments/" in attachment_data["download_url"]
        assert "/download" in attachment_data["download_url"]

    # Verify all attachments were created in the database
    attachments = await Attachment.filter(workspace_id=meeting.workspace_id).all().order_by("created_at")
    assert len(attachments) == 3

    # Verify attachment properties
    assert attachments[0].user_id == creator.id
    assert attachments[0].title == "file1.txt"
    assert attachments[1].user_id == creator.id
    assert attachments[1].title == "file2.txt"
    assert attachments[2].user_id == creator.id
    assert attachments[2].title == "file3.txt"

    # Verify the response URLs correspond to the created attachments
    attachment_ids = {att.id for att in attachments}
    for attachment_data in response_json["attachments"]:
        # Extract attachment ID from URL (format: /workspaces/{id}/attachments/{attachment_id}/download)
        url_parts = attachment_data["download_url"].split("/")
        attachment_id_from_url = url_parts[-2]  # The ID is second to last in the path
        assert str(attachment_id_from_url) in {str(aid) for aid in attachment_ids}
