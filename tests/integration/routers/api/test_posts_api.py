import io
from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Attachment, Collaborator, Event, SubscriptionPreference
from app.models.workspaces.posts import Post
from config.enums import EventAction, PostStatusFilter, SubscriptionLevel
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_group, create_post, create_user


@pytest.mark.asyncio
async def test_patch_title(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id, title="Original")

    response = await client.patch(f"/api/posts/{post.id}", json={"title": "New title"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["title"] == "New title"
    assert (await Post.get(id=post.id)).title == "New title"


@pytest.mark.asyncio
async def test_patch_content_updates_original_comment(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    response = await client.patch(f"/api/posts/{post.id}", json={"content": "Updated body"})
    assert response.status_code == status.HTTP_200_OK

    refreshed = await Post.get(id=post.id).prefetch_related("comments")
    assert refreshed.original_comment.content == "Updated body"


@pytest.mark.asyncio
async def test_patch_group_assignment(client: AppClient):
    user = await client.get_default_user()
    group = await create_group(organization_id=user.organization_id)
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    response = await client.patch(f"/api/posts/{post.id}", json={"group_id": str(group.id)})
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["group"]["id"] == str(group.id)

    response = await client.patch(f"/api/posts/{post.id}", json={"clear_group_id": True})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["group"] is None


@pytest.mark.asyncio
async def test_patch_pin_admin_only(client: AppClient):
    creator = await client.get_default_user()
    admin = await create_user(organization_id=creator.organization_id, is_admin=True)
    subscriber = await create_user(organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(subscriber.id, {Post.record_type: SubscriptionLevel.ALL})
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=creator.id, user_id=subscriber.id)

    # Creator (non-admin) cannot pin
    response = await client.patch(f"/api/posts/{post.id}/pin", json={"pinned": True})
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # Admin can pin and triggers POST_PINNED notification
    with client.current_user_as(admin):
        response = await client.patch(f"/api/posts/{post.id}/pin", json={"pinned": True})
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["is_pinned"] is True
        assert body["pinned_at"] is not None

    events = await Event.filter(workspace_id=post.workspace_id, action=EventAction.POST_PINNED).all()
    assert len(events) == 1

    # Subscribers get a mailbox entry when a post is pinned
    entry = await MailboxEntry.filter(owner_id=subscriber.id, resource_gid=str(post.global_id)).first()
    assert entry is not None

    # Admin can unpin
    with client.current_user_as(admin):
        response = await client.patch(f"/api/posts/{post.id}/pin", json={"pinned": False})
        assert response.status_code == status.HTTP_200_OK
        body = response.json()
        assert body["is_pinned"] is False
        assert body["pinned_at"] is None


@pytest.mark.asyncio
async def test_patch_empty_body_rejected(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    response = await client.patch(f"/api/posts/{post.id}", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_patch_noop_bodies_rejected(client: AppClient):
    # at_least_one_edit checks effective edits, not just model_fields_set, so
    # explicit false/null defaults that don't change anything are rejected.
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    for body in ({"clear_group_id": False}, {"title": None}, {"content": None}):
        response = await client.patch(f"/api/posts/{post.id}", json=body)
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, body


@pytest.mark.asyncio
async def test_patch_whitespace_title_rejected(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    response = await client.patch(f"/api/posts/{post.id}", json={"title": "   "})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_patch_rejects_group_id_and_clear_group_id_together(client: AppClient):
    user = await client.get_default_user()
    group = await create_group(organization_id=user.organization_id)
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    response = await client.patch(
        f"/api/posts/{post.id}",
        json={"group_id": str(group.id), "clear_group_id": True},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_patch_group_id_must_belong_to_organization(client: AppClient):
    user = await client.get_default_user()
    other_org_group = await create_group()  # different organization by default
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    response = await client.patch(f"/api/posts/{post.id}", json={"group_id": str(other_org_group.id)})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_patch_content_resolves_mentions(client: AppClient):
    creator = await client.get_default_user()
    mentioned = await create_user(organization_id=creator.organization_id, name="Mentioned")
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.patch(
        f"/api/posts/{post.id}",
        json={"content": f"updated body @[{mentioned.display_name}]"},
    )
    assert response.status_code == status.HTTP_200_OK

    collaborator = await Collaborator.get_or_none(workspace_id=post.workspace_id, user_id=mentioned.id)
    assert collaborator is not None


@pytest.mark.asyncio
async def test_patch_non_creator_non_admin_forbidden(client: AppClient):
    creator = await client.get_default_user()
    other = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    with client.current_user_as(other):
        response = await client.patch(f"/api/posts/{post.id}", json={"title": "nope"})
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_delete_by_creator(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    response = await client.delete(f"/api/posts/{post.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert "Location" in response.headers
    assert await Post.filter(id=post.id).count() == 0  # soft-deleted, excluded by default


@pytest.mark.asyncio
async def test_delete_by_admin(client: AppClient):
    user = await client.get_default_user()
    admin = await create_user(organization_id=user.organization_id, is_admin=True)
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)

    with client.current_user_as(admin):
        response = await client.delete(f"/api/posts/{post.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_delete_forbidden_for_other_user(client: AppClient):
    creator = await client.get_default_user()
    other = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    with client.current_user_as(other):
        response = await client.delete(f"/api/posts/{post.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_delete_draft_points_back_to_drafts(client: AppClient):
    creator = await client.get_default_user()
    draft = await create_post(creator_id=creator.id, organization_id=creator.organization_id, published_at=None)

    response = await client.delete(f"/api/posts/{draft.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    # Deleting a draft sends the client back to the drafts filter, not the open feed.
    assert f"status={PostStatusFilter.DRAFTS.value}" in response.headers["Location"]
    assert await Post.filter(id=draft.id).count() == 0


@pytest.mark.asyncio
async def test_patch_content_claims_attachments_for_team_visibility(client: AppClient):
    creator = await client.get_default_user()
    other = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    # Upload an image via the GLOBAL endpoint, so the attachment has no workspace yet
    # (this reproduces the composer's workspace-less upload).
    claim_id = uuid4()
    response = await client.post(
        "/api/workspaces/attachments",
        files={"files": ("image.png", io.BytesIO(b"image data"), "image/png")},
        data={"claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_201_CREATED
    download_url = response.json()["attachments"][0]["download_url"]
    attachment = await Attachment.get(claim_id=claim_id)

    # Editing the post body to reference the image claims the attachment onto the post.
    response = await client.patch(
        f"/api/posts/{post.id}",
        json={"content": f'<p>See <img src="{download_url}"></p>', "attachment_claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_200_OK

    # The attachment is now scoped to the post's workspace and the original comment.
    refreshed_post = await Post.get(id=post.id).prefetch_related("comments")
    await attachment.refresh_from_db()
    assert attachment.workspace_id == post.workspace_id
    assert attachment.claim_id is None
    assert attachment.comment_gid == refreshed_post.original_comment.global_id

    # A teammate can download the now-claimed attachment (the bug: it 404s while unclaimed).
    with client.current_user_as(other):
        response = await client.get(f"/workspaces/attachments/{attachment.id}/download", follow_redirects=False)
        assert response.status_code == status.HTTP_302_FOUND

    # Editing again to remove the image deletes the now-unreferenced attachment.
    response = await client.patch(
        f"/api/posts/{post.id}",
        json={"content": "<p>image removed</p>", "attachment_claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_200_OK
    assert await Attachment.get_or_none(id=attachment.id) is None
