import io
from urllib.parse import urljoin
from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Attachment, Collaborator, LinkPreview, SubscriptionPreference
from app.models.workspaces.posts import Post, PostComment
from config.enums import SubscriptionLevel
from config.settings import settings
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_post,
    create_post_comment,
    create_user,
)


@pytest.mark.asyncio
async def test_create_top_level_and_reply(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    response = await client.post(
        f"/api/posts/{post.id}/comments",
        json={"content": "Top-level comment"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    top_level = response.json()
    assert top_level["parent_id"] is None
    assert top_level["user"]["id"] == str(user.id)
    top_level_id = top_level["id"]

    response = await client.post(
        f"/api/posts/{post.id}/comments",
        json={"content": "A reply", "parent_id": top_level_id},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["parent_id"] == top_level_id


@pytest.mark.asyncio
async def test_comment_link_preview_association(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    # A comment with a URL unfurls and associates a link preview
    response = await client.post(
        f"/api/posts/{post.id}/comments",
        json={"content": "See https://github.com/anthropics/claude-code"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment = await PostComment.get(id=response.json()["id"])
    assert comment.link_preview_id is not None
    assert await LinkPreview.all().count() == 1

    # A second comment with the same URL shares the cached link preview
    response = await client.post(
        f"/api/posts/{post.id}/comments",
        json={"content": "Also https://github.com/anthropics/claude-code"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment2 = await PostComment.get(id=response.json()["id"])
    assert comment2.link_preview_id == comment.link_preview_id
    assert await LinkPreview.all().count() == 1

    # Editing a comment to remove the URL drops the association but keeps the LinkPreview
    response = await client.patch(
        f"/api/posts/{post.id}/comments/{comment2.id}",
        json={"content": "No links here anymore"},
    )
    assert response.status_code == status.HTTP_200_OK
    await comment2.refresh_from_db()
    assert comment2.link_preview_id is None
    assert await LinkPreview.all().count() == 1

    # unfurl_links=False skips re-association even when the content still has a URL
    response = await client.patch(
        f"/api/posts/{post.id}/comments/{comment2.id}",
        json={"content": "See https://github.com/anthropics/claude-code", "unfurl_links": False},
    )
    assert response.status_code == status.HTTP_200_OK
    await comment2.refresh_from_db()
    assert comment2.link_preview_id is None


@pytest.mark.asyncio
async def test_comment_attachment_link_serializes_file_card(client: AppClient):
    # A pasted attachment link on a post comment carries resource_kind="file" AND re-resolved
    # file metadata (content type/size) so the shared LinkPreviewCard renders a full file card,
    # matching chat (both were omitted on this surface before).
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    content = b"%PDF-1.4 spec body"
    attachment = await create_attachment(
        user_id=user.id, workspace_id=None, filename="spec.pdf", content_type="application/pdf", content=content
    )
    url = urljoin(str(settings.base_url), f"/workspaces/attachments/{attachment.id}/download")

    create = await client.post(f"/api/posts/{post.id}/comments", json={"content": f"See {url}"})
    assert create.status_code == status.HTTP_201_CREATED
    comment_id = create.json()["id"]

    # associate() updates the row after construction, so the preview surfaces on a fresh read
    # (as the frontend fetches it), not on the create response.
    listing = await client.get(f"/api/posts/{post.id}/comments")
    preview = next(c["link_preview"] for c in listing.json()["comments"] if c["id"] == comment_id)
    assert preview is not None
    assert preview["resource_kind"] == "file"
    assert preview["title"] == "spec.pdf"
    assert preview["file"] == {
        "file_name": "spec.pdf",
        "content_type": "application/pdf",
        "byte_size": len(content),
    }


@pytest.mark.asyncio
async def test_create_resolves_mentions_and_adds_collaborator(client: AppClient):
    creator = await client.get_default_user()
    mentioned = await create_user(organization_id=creator.organization_id, name="Mentioned User")
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.post(
        f"/api/posts/{post.id}/comments",
        json={"content": f"Hey @[{mentioned.display_name}], what do you think?"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    collaborator = await Collaborator.get_or_none(workspace_id=post.workspace_id, user_id=mentioned.id)
    assert collaborator is not None


@pytest.mark.asyncio
async def test_announcement_comment_creates_mailbox_entry(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(creator.id, {Post.record_type: SubscriptionLevel.ALL})
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, is_announcement=True)

    with client.current_user_as(other_user):
        response = await client.post(f"/api/posts/{post.id}/comments", json={"content": "Great announcement!"})
        assert response.status_code == status.HTTP_201_CREATED

    entry = await MailboxEntry.filter(owner_id=creator.id, resource_gid=str(post.global_id)).first()
    assert entry is not None
    assert entry.is_inbox


@pytest.mark.asyncio
async def test_unreferenced_attachment_cleanup_on_edit(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    # Upload an attachment and claim it
    claim_id = uuid4()
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/attachments",
        files={"files": ("image.png", io.BytesIO(b"image data"), "image/png")},
        data={"claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_201_CREATED
    download_url = response.json()["attachments"][0]["download_url"]
    attachment = await Attachment.get(claim_id=claim_id)

    # Create a comment that references the attachment
    response = await client.post(
        f"/api/posts/{post.id}/comments",
        json={"content": f'<p>Check this: <img src="{download_url}"></p>', "attachment_claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]

    # Editing to remove the image deletes the now-unreferenced attachment
    response = await client.patch(
        f"/api/posts/{post.id}/comments/{comment_id}",
        json={"content": "<p>Image removed</p>", "attachment_claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_200_OK
    assert await Attachment.get_or_none(id=attachment.id) is None


@pytest.mark.asyncio
async def test_edit_only_by_author(client: AppClient):
    creator = await client.get_default_user()
    other = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="original")

    # Author edits successfully
    response = await client.patch(
        f"/api/posts/{post.id}/comments/{comment.id}",
        json={"content": "edited"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["content"] == "edited"

    # Non-author is forbidden
    with client.current_user_as(other):
        response = await client.patch(
            f"/api/posts/{post.id}/comments/{comment.id}",
            json={"content": "hijack"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_edit_response_preserves_replies(client: AppClient):
    # PATCH on a top-level comment with replies must return the reply list so
    # the React reducer doesn't drop nested replies when it replaces state.
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    top_level = await create_post_comment(post_id=post.id, user_id=user.id, content="parent")
    await create_post_comment(post_id=post.id, user_id=user.id, parent_id=top_level.id, content="reply 1")
    await create_post_comment(post_id=post.id, user_id=user.id, parent_id=top_level.id, content="reply 2")

    response = await client.patch(
        f"/api/posts/{post.id}/comments/{top_level.id}",
        json={"content": "edited parent"},
    )
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["content"] == "edited parent"
    assert len(body["replies"]) == 2
    assert {r["content"] for r in body["replies"]} == {"reply 1", "reply 2"}


@pytest.mark.asyncio
async def test_delete_only_by_author(client: AppClient):
    creator = await client.get_default_user()
    other = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="bye")

    with client.current_user_as(other):
        response = await client.delete(f"/api/posts/{post.id}/comments/{comment.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    response = await client.delete(f"/api/posts/{post.id}/comments/{comment.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await PostComment.filter(id=comment.id).count() == 0  # soft-deleted, excluded by default


@pytest.mark.asyncio
async def test_reaction_toggle(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=user.id, content="React")

    response = await client.post(f"/api/posts/{post.id}/comments/{comment.id}/reactions?reaction_type=thumbs_up")
    assert response.status_code == status.HTTP_200_OK
    reaction_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
    assert str(user.id) in reaction_ids

    response = await client.post(f"/api/posts/{post.id}/comments/{comment.id}/reactions?reaction_type=thumbs_up")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["reactions"].get("thumbs_up", []) == []


@pytest.mark.asyncio
async def test_list_includes_original_and_top_level(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    top_level = await create_post_comment(post_id=post.id, user_id=user.id, content="top")
    await create_post_comment(post_id=post.id, user_id=user.id, parent_id=top_level.id, content="reply")

    response = await client.get(f"/api/posts/{post.id}/comments")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["next_cursor"] is None
    assert body["has_more"] is False
    # original_comment + top_level (both top-level, parent_id is null)
    assert len(body["comments"]) == 2
    matched = [c for c in body["comments"] if c["id"] == str(top_level.id)]
    assert len(matched[0]["replies"]) == 1


@pytest.mark.asyncio
async def test_create_empty_content_rejected(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    response = await client.post(f"/api/posts/{post.id}/comments", json={"content": "   "})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_create_reply_to_a_reply_rejected(client: AppClient):
    # Post threading is one level deep. Depth-2 replies would be invisible on
    # the show endpoint (one replies__ prefetch level), so the API must reject.
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    top_level = await create_post_comment(post_id=post.id, user_id=user.id, content="top")
    reply = await create_post_comment(post_id=post.id, user_id=user.id, parent_id=top_level.id, content="reply")

    response = await client.post(
        f"/api/posts/{post.id}/comments",
        json={"content": "depth-2", "parent_id": str(reply.id)},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_reply_with_wrong_post_404(client: AppClient):
    user = await client.get_default_user()
    post_a = await create_post(creator_id=user.id, organization_id=user.organization_id)
    post_b = await create_post(creator_id=user.id, organization_id=user.organization_id)
    other_parent = await create_post_comment(post_id=post_b.id, user_id=user.id)

    response = await client.post(
        f"/api/posts/{post_a.id}/comments",
        json={"content": "reply", "parent_id": str(other_parent.id)},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_draft_post_comment_endpoints_return_404(client: AppClient):
    # Drafts are not yet public resources; their comments aren't either.
    # api_posts_show already 404s drafts; mutation endpoints should match.
    user = await client.get_default_user()
    draft = await create_post(creator_id=user.id, organization_id=user.organization_id, published_at=None)
    comment = await create_post_comment(post_id=draft.id, user_id=user.id)

    paths = [
        ("GET", f"/api/posts/{draft.id}/comments", None),
        ("POST", f"/api/posts/{draft.id}/comments", {"content": "hi"}),
        ("PATCH", f"/api/posts/{draft.id}/comments/{comment.id}", {"content": "edit"}),
        ("DELETE", f"/api/posts/{draft.id}/comments/{comment.id}", None),
        ("POST", f"/api/posts/{draft.id}/comments/{comment.id}/reactions?reaction_type=thumbs_up", None),
    ]
    for method, path, body in paths:
        response = await client.request(method, path, json=body)
        assert response.status_code == status.HTTP_404_NOT_FOUND, f"{method} {path} should 404 on a draft"
