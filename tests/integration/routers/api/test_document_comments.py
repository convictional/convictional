import pytest
from fastapi import status

from app.models.collaboration.workspace import Mention, SubscriptionPreference
from app.models.workspaces.documents import Document, DocumentComment
from config.enums import Sharing, SubscriptionLevel
from infra.email import FakeDelivery
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_document, create_user


@pytest.mark.asyncio
async def test_comment_crud(client: AppClient):
    creator = await client.get_default_user()
    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )

    # GET empty list
    response = await client.get(f"/api/documents/{document.id}/comments")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"comments": [], "next_cursor": None, "has_more": False}

    # POST create
    response = await client.post(
        f"/api/documents/{document.id}/comments",
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
    response = await client.get(f"/api/documents/{document.id}/comments")
    body = response.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["id"] == comment_id

    # PATCH edit
    response = await client.patch(
        f"/api/documents/{document.id}/comments/{comment_id}",
        json={"content": "Updated feedback"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["content"] == "Updated feedback"

    # Add a reply to test thread resolve
    await client.post(
        f"/api/documents/{document.id}/comments",
        json={"content": "Reply", "comment_mark_id": "mark-1"},
    )

    # PATCH resolve — resolves all comments in the thread
    response = await client.patch(
        f"/api/documents/{document.id}/comments/{comment_id}",
        json={"resolved": True},
    )
    thread = response.json()
    assert thread["comment_mark_id"] == "mark-1"
    assert thread["resolved_at"] is not None
    assert len(thread["comments"]) == 2
    assert all(c["resolved_at"] is not None for c in thread["comments"])

    # Re-resolving is a no-op — returns the still-resolved thread.
    response = await client.patch(
        f"/api/documents/{document.id}/comments/{comment_id}",
        json={"resolved": True},
    )
    assert response.json()["resolved_at"] is not None

    # GET excludes resolved comments
    response = await client.get(f"/api/documents/{document.id}/comments")
    assert response.json() == {"comments": [], "next_cursor": None, "has_more": False}

    # Unresolve
    response = await client.patch(
        f"/api/documents/{document.id}/comments/{comment_id}",
        json={"resolved": False},
    )
    thread = response.json()
    assert thread["resolved_at"] is None
    assert all(c["resolved_at"] is None for c in thread["comments"])

    # Content edit and resolve can be combined in one PATCH.
    response = await client.patch(
        f"/api/documents/{document.id}/comments/{comment_id}",
        json={"content": "Final wording", "resolved": True},
    )
    assert response.status_code == status.HTTP_200_OK
    thread = response.json()
    assert thread["resolved_at"] is not None
    edited = next(c for c in thread["comments"] if c["id"] == str(comment_id))
    assert edited["content"] == "Final wording"

    # Empty PATCH body is rejected.
    response = await client.patch(
        f"/api/documents/{document.id}/comments/{comment_id}",
        json={},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # DELETE
    response = await client.delete(f"/api/documents/{document.id}/comments/{comment_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_comment_permissions(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )
    await create_collaborator(workspace_id=document.workspace_id, added_by_id=creator.id, user_id=other_user.id)

    # Creator makes a comment
    response = await client.post(
        f"/api/documents/{document.id}/comments",
        json={"content": "Review this", "quoted_text": "passage", "comment_mark_id": "mark-2"},
    )
    comment_id = response.json()["id"]

    # Collaborator cannot edit or delete creator's comment
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/documents/{document.id}/comments/{comment_id}",
            json={"content": "Hijacked"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await client.delete(f"/api/documents/{document.id}/comments/{comment_id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # But can resolve (collaborative workflow), and cannot smuggle a content
    # edit through the same PATCH.
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/documents/{document.id}/comments/{comment_id}",
            json={"resolved": True},
        )
        assert response.status_code == status.HTTP_200_OK

        response = await client.patch(
            f"/api/documents/{document.id}/comments/{comment_id}",
            json={"content": "Sneaky", "resolved": False},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    comment = await DocumentComment.get(id=comment_id)
    assert comment.is_resolved


@pytest.mark.asyncio
async def test_document_comment_notifications(client: AppClient, email_delivery: FakeDelivery):
    creator = await client.get_default_user()
    subscriber = await create_user(organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    await create_collaborator(workspace_id=document.workspace_id, user_id=subscriber.id)

    await SubscriptionPreference.update_for(subscriber.id, {Document.record_type: SubscriptionLevel.ALL})

    response = await client.post(
        f"/api/documents/{document.id}/comments",
        json={"content": "Please review this section", "quoted_text": "some text", "comment_mark_id": "mark-1"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Subscriber gets notified, creator does not
    assert len(email_delivery.messages) == 1
    assert email_delivery.messages[0].to == subscriber.email
    assert "Please review this section" in email_delivery.messages[0].html
    assert "Re: (Document)" in email_delivery.messages[0].subject

    # Notification includes the quoted text for context
    assert "some text" in email_delivery.messages[0].html

    # Notification links to the specific comment (deep link with fragment)
    comment_id = response.json()["id"]
    assert f"#comment-{comment_id}" in email_delivery.messages[0].html

    creators_email = email_delivery.by_recipient(creator.email)
    assert len(creators_email) == 0


@pytest.mark.asyncio
async def test_document_comment_mentions(client: AppClient, email_delivery: FakeDelivery):
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Wonderland", organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    response = await client.post(
        f"/api/documents/{document.id}/comments",
        json={"content": "Hey @[Alice Wonderland] thoughts?", "quoted_text": "passage", "comment_mark_id": "mark-1"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Alice gets a mention email
    alices_email = email_delivery.by_recipient(alice.email)
    assert len(alices_email) == 1
    assert "mentioned you" in alices_email[0].html
    # The comment body renders with the mention humanized and bolded — the raw
    # @[Name] marker syntax is gone.
    assert "@Alice Wonderland" in alices_email[0].html
    assert "@[Alice Wonderland]" not in alices_email[0].html
    assert "thoughts?" in alices_email[0].html

    # Mention email deep links to the specific comment (not just the document)
    comment_id = response.json()["id"]
    assert f"#comment-{comment_id}" in alices_email[0].html

    # Mention record created
    await document.fetch_related("workspace")
    mentions = await Mention.filter(workspace_id=document.workspace_id).all()
    assert len(mentions) == 1
    assert mentions[0].mentioned_id == alice.id
    assert mentions[0].creator_id == creator.id
    assert mentions[0].event_id is not None


@pytest.mark.asyncio
async def test_document_comment_edit_mentions(client: AppClient, email_delivery: FakeDelivery):
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Editland", organization_id=creator.organization_id)
    bob = await create_user(name="Bob Editland", organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    # Create comment mentioning Alice
    response = await client.post(
        f"/api/documents/{document.id}/comments",
        json={"content": "Hey @[Alice Editland]", "quoted_text": "text", "comment_mark_id": "mark-1"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]

    email_delivery.reset()

    # Edit to also mention Bob — only Bob should get a new mention email
    response = await client.patch(
        f"/api/documents/{document.id}/comments/{comment_id}",
        json={"content": "Hey @[Alice Editland] and @[Bob Editland]"},
    )
    assert response.status_code == status.HTTP_200_OK

    alices_email = email_delivery.by_recipient(alice.email)
    assert len(alices_email) == 0  # Already mentioned, no re-notification

    bobs_email = email_delivery.by_recipient(bob.email)
    assert len(bobs_email) == 1
    assert "mentioned you" in bobs_email[0].html


@pytest.mark.asyncio
async def test_reaction_toggle(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.PRIVATE,
    )
    await create_collaborator(workspace_id=document.workspace_id, added_by_id=creator.id, user_id=other_user.id)

    # Create a comment
    response = await client.post(
        f"/api/documents/{document.id}/comments",
        json={"content": "Test comment", "quoted_text": "text", "comment_mark_id": "mark-1"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]

    # Toggle reaction on
    response = await client.post(
        f"/api/documents/{document.id}/comments/{comment_id}/reactions?reaction_type=thumbs_up"
    )
    assert response.status_code == status.HTTP_200_OK
    reaction_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
    assert str(creator.id) in reaction_ids
    assert response.json()["reactions"]["thumbs_up"][0]["display_name"] == creator.display_name

    # Toggle reaction off
    response = await client.post(
        f"/api/documents/{document.id}/comments/{comment_id}/reactions?reaction_type=thumbs_up"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["reactions"].get("thumbs_up", []) == []

    # Another user can react
    with client.current_user_as(other_user):
        response = await client.post(
            f"/api/documents/{document.id}/comments/{comment_id}/reactions?reaction_type=thumbs_up"
        )
        assert response.status_code == status.HTTP_200_OK
        reaction_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
        assert str(other_user.id) in reaction_ids

    # Multiple reaction types
    response = await client.post(f"/api/documents/{document.id}/comments/{comment_id}/reactions?reaction_type=heart")
    heart_ids = [u["id"] for u in response.json()["reactions"]["heart"]]
    thumbs_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
    assert str(creator.id) in heart_ids
    assert str(other_user.id) in thumbs_ids
