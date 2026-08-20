from urllib.parse import urljoin
from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.workspace import LinkPreview
from app.models.workspaces.posts import PostComment
from config.settings import settings
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_chat,
    create_document,
    create_email_thread,
    create_goal,
    create_meeting,
    create_post,
    create_user,
)


def _internal_url(path: str) -> str:
    return urljoin(str(settings.base_url), path)


@pytest.mark.asyncio
async def test_unfurl_link_preview(client: AppClient):
    user = await create_user(email="link-preview@convictional.com")

    with client.current_user_as(user):
        # POST valid URL → 200 with preview data
        response = await client.post(
            "/api/link_previews/unfurl", json={"url": "https://github.com/anthropics/claude-code"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["link_preview"] is not None
        assert data["link_preview"]["url"] == "https://github.com/anthropics/claude-code"
        assert data["link_preview"]["domain"] == "github.com"
        # External links carry no resource kind, so the card renders its plain variant.
        assert data["link_preview"]["resource_kind"] is None

        # POST same URL again → cached (LinkPreview count == 1)
        await client.post("/api/link_previews/unfurl", json={"url": "https://github.com/anthropics/claude-code"})
        count = await LinkPreview.all().count()
        assert count == 1


@pytest.mark.asyncio
async def test_unfurl_link_preview_errors(client: AppClient):
    user = await create_user(email="link-preview-err@convictional.com")

    with client.current_user_as(user):
        # Unsafe URL → 200 with null preview (request was valid, URL just didn't produce a preview)
        response = await client.post("/api/link_previews/unfurl", json={"url": "javascript:alert(1)"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["link_preview"] is None

        # Validation errors use FastAPI's default format
        response = await client.post("/api/link_previews/unfurl", json={})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], list)

        # Field constraint violation (max_length) also returns standard validation format
        response = await client.post("/api/link_previews/unfurl", json={"url": "https://x.com/" + "a" * 2048})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
        data = response.json()
        assert "detail" in data
        assert isinstance(data["detail"], list)


@pytest.mark.asyncio
async def test_unfurl_internal_link_previews(client: AppClient):
    user = await create_user()
    org_id = user.organization_id

    goal = await create_goal(
        creator_id=user.id, organization_id=org_id, title="Quarterly OKRs", description="Grow revenue 20%"
    )
    post = await create_post(creator_id=user.id, organization_id=org_id, title="Lunch plans")
    document = await create_document(creator_id=user.id, organization_id=org_id, title="Spec")
    meeting = await create_meeting(creator_id=user.id, organization_id=org_id, title="Standup")
    thread = await create_email_thread(creator_id=user.id, organization_id=org_id, title="Re: Budget")
    chat = await create_chat(creator_id=user.id, organization_id=org_id, title="Project chat")
    comment = await PostComment.filter(post_id=post.id).first()
    assert comment is not None

    # path -> (expected title, expected description, expected resource_kind). Covers friendly URLs
    # for every resource type (documents and chats included, which never unfurled before), the goal
    # detail page and index fragment (with and without a query string), and a comment fragment
    # resolving to its parent. Goals surface their long-form description as the title (not the short
    # "Quarterly OKRs" title), leaving the description slot empty.
    cases = {
        f"/goals/{goal.id}": ("Grow revenue 20%", None, "goal"),
        f"/goals#goal-{goal.id}": ("Grow revenue 20%", None, "goal"),
        f"/goals?is_closed=true#goal-{goal.id}": ("Grow revenue 20%", None, "goal"),
        f"/posts/{post.id}": ("Lunch plans", "What should we eat for lunch?", "post"),
        f"/posts/{post.id}#comment-{comment.id}": ("Lunch plans", "What should we eat for lunch?", "post"),
        f"/documents/{document.id}": ("Spec", None, "document"),
        f"/documents/{document.id}/edit": ("Spec", None, "document"),
        f"/meetings/{meeting.id}": ("Standup", None, "meeting"),
        f"/email_threads/{thread.id}": ("Re: Budget", None, "email_thread"),
        f"/chats/{chat.id}": ("Project chat", None, "chat"),
        # GlobalID /gid/{param} form resolves identically to the friendly URL.
        f"/gid/{goal.global_id.to_param}": ("Grow revenue 20%", None, "goal"),
    }

    with client.current_user_as(user):
        for path, (title, description, resource_kind) in cases.items():
            response = await client.post("/api/link_previews/unfurl", json={"url": _internal_url(path)})
            assert response.status_code == status.HTTP_200_OK, path
            preview = response.json()["link_preview"]
            assert preview is not None, path
            assert preview["title"] == title, path
            assert preview["description"] == description, path
            assert preview["resource_kind"] == resource_kind, path

    # Internal previews resolve in-process and are never written to the URL-keyed cache.
    assert await LinkPreview.all().count() == 0


@pytest.mark.asyncio
async def test_unfurl_attachment_link_preview(client: AppClient):
    user = await create_user()
    content = b"%PDF-1.4 fake pdf body"
    attachment = await create_attachment(
        user_id=user.id, workspace_id=None, filename="report.pdf", content_type="application/pdf", content=content
    )

    with client.current_user_as(user):
        response = await client.post(
            "/api/link_previews/unfurl",
            json={"url": _internal_url(f"/workspaces/attachments/{attachment.id}/download")},
        )
    assert response.status_code == status.HTTP_200_OK
    preview = response.json()["link_preview"]
    assert preview["resource_kind"] == "file"
    assert preview["title"] == "report.pdf"
    assert preview["file"] == {
        "file_name": "report.pdf",
        "content_type": "application/pdf",
        "byte_size": len(content),
    }
    # Attachment previews resolve in-process and are never cached.
    assert await LinkPreview.all().count() == 0


@pytest.mark.asyncio
async def test_unfurl_internal_link_preview_denied_and_missing(client: AppClient):
    user = await create_user()

    # Same org, private, owned by a teammate the user does not collaborate with.
    teammate = await create_user(organization_id=user.organization_id)
    private_document = await create_document(creator_id=teammate.id, organization_id=user.organization_id)

    # A post in a different organization entirely.
    foreign_post = await create_post(title="Roadmap")

    denied_or_missing = [
        f"/documents/{private_document.id}",
        f"/posts/{foreign_post.id}",
        f"/posts/{uuid4()}",
        f"/goals#goal-{uuid4()}",
        "/gid/!!!not-base64!!!",
    ]

    with client.current_user_as(user):
        for path in denied_or_missing:
            response = await client.post("/api/link_previews/unfurl", json={"url": _internal_url(path)})
            assert response.status_code == status.HTTP_200_OK, path
            assert response.json()["link_preview"] is None, path

    assert await LinkPreview.all().count() == 0


@pytest.mark.asyncio
async def test_api_unauthenticated_returns_401(client: AppClient):
    # Unauthenticated requests to /api/ return 401 JSON, not a 307 redirect
    with client.logged_out():
        response = await client.post(
            "/api/link_previews/unfurl",
            json={"url": "https://example.com"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        data = response.json()
        assert data == {"detail": "Authentication required"}
