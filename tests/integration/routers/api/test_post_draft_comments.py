import pytest
from fastapi import status

from app.models.workspaces.posts import PostDraftComment
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_post, create_user


@pytest.mark.asyncio
async def test_comment_crud(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        published_at=None,
    )

    # GET empty list
    response = await client.get(f"/api/posts/{post.id}/draft/comments")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"comments": [], "next_cursor": None, "has_more": False}

    # POST create
    response = await client.post(
        f"/api/posts/{post.id}/draft/comments",
        json={"content": "Needs revision", "quoted_text": "some text", "comment_mark_id": "mark-1"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["content"] == "Needs revision"
    assert data["quoted_text"] == "some text"
    assert data["comment_mark_id"] == "mark-1"
    assert data["resolved_at"] is None
    assert data["user"]["id"] == str(creator.id)
    assert data["user"]["display_name"] == creator.display_name
    comment_id = data["id"]

    # GET returns the comment
    response = await client.get(f"/api/posts/{post.id}/draft/comments")
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["id"] == comment_id

    # PATCH edit
    response = await client.patch(
        f"/api/posts/{post.id}/draft/comments/{comment_id}",
        json={"content": "Updated feedback"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["content"] == "Updated feedback"

    # Add a reply to test thread resolve
    await client.post(
        f"/api/posts/{post.id}/draft/comments",
        json={"content": "Reply", "comment_mark_id": "mark-1"},
    )

    # PATCH resolve — resolves all comments in the thread
    response = await client.patch(
        f"/api/posts/{post.id}/draft/comments/{comment_id}",
        json={"resolved": True},
    )
    thread = response.json()
    assert thread["comment_mark_id"] == "mark-1"
    assert thread["resolved_at"] is not None
    assert len(thread["comments"]) == 2
    assert all(c["resolved_at"] is not None for c in thread["comments"])

    # Re-resolving is a no-op.
    response = await client.patch(
        f"/api/posts/{post.id}/draft/comments/{comment_id}",
        json={"resolved": True},
    )
    assert response.json()["resolved_at"] is not None

    # GET excludes resolved comments
    response = await client.get(f"/api/posts/{post.id}/draft/comments")
    assert response.json() == {"comments": [], "next_cursor": None, "has_more": False}

    # Unresolve
    response = await client.patch(
        f"/api/posts/{post.id}/draft/comments/{comment_id}",
        json={"resolved": False},
    )
    thread = response.json()
    assert thread["resolved_at"] is None
    assert all(c["resolved_at"] is None for c in thread["comments"])

    # Content edit and resolve can be combined.
    response = await client.patch(
        f"/api/posts/{post.id}/draft/comments/{comment_id}",
        json={"content": "Final wording", "resolved": True},
    )
    assert response.status_code == status.HTTP_200_OK
    thread = response.json()
    assert thread["resolved_at"] is not None
    edited = next(c for c in thread["comments"] if c["id"] == str(comment_id))
    assert edited["content"] == "Final wording"

    # Empty PATCH body is rejected.
    response = await client.patch(
        f"/api/posts/{post.id}/draft/comments/{comment_id}",
        json={},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # DELETE
    response = await client.delete(f"/api/posts/{post.id}/draft/comments/{comment_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_comment_permissions(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)

    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        published_at=None,
    )
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=creator.id, user_id=other_user.id)

    # Creator makes a comment
    response = await client.post(
        f"/api/posts/{post.id}/draft/comments",
        json={"content": "Review this", "quoted_text": "passage", "comment_mark_id": "mark-2"},
    )
    comment_id = response.json()["id"]

    # Collaborator cannot edit or delete creator's comment
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/posts/{post.id}/draft/comments/{comment_id}",
            json={"content": "Hijacked"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await client.delete(f"/api/posts/{post.id}/draft/comments/{comment_id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # But can resolve (collaborative workflow), and cannot smuggle a content
    # edit through the same PATCH.
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/posts/{post.id}/draft/comments/{comment_id}",
            json={"resolved": True},
        )
        assert response.status_code == status.HTTP_200_OK

        response = await client.patch(
            f"/api/posts/{post.id}/draft/comments/{comment_id}",
            json={"content": "Sneaky", "resolved": False},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    comment = await PostDraftComment.get(id=comment_id)
    assert comment.is_resolved


@pytest.mark.asyncio
async def test_published_post_returns_404(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
    )
    # post is published by default (published_at=now)
    response = await client.get(f"/api/posts/{post.id}/draft/comments")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_reaction_toggle(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)

    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        published_at=None,
    )
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=creator.id, user_id=other_user.id)

    # Create a comment
    response = await client.post(
        f"/api/posts/{post.id}/draft/comments",
        json={"content": "Test comment", "quoted_text": "text", "comment_mark_id": "mark-1"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]

    # Toggle reaction on
    response = await client.post(f"/api/posts/{post.id}/draft/comments/{comment_id}/reactions?reaction_type=thumbs_up")
    assert response.status_code == status.HTTP_200_OK
    reaction_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
    assert str(creator.id) in reaction_ids

    # Toggle reaction off
    response = await client.post(f"/api/posts/{post.id}/draft/comments/{comment_id}/reactions?reaction_type=thumbs_up")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["reactions"].get("thumbs_up", []) == []

    # Another user can react
    with client.current_user_as(other_user):
        response = await client.post(
            f"/api/posts/{post.id}/draft/comments/{comment_id}/reactions?reaction_type=thumbs_up"
        )
        assert response.status_code == status.HTTP_200_OK
        reaction_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
        assert str(other_user.id) in reaction_ids
