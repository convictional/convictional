from datetime import UTC, datetime
from uuid import uuid4

import pytest
from starlette import status

from app.models.collaboration.workspace import Attachment
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_chat,
    create_chat_message,
    create_collaborator,
    create_user,
)


@pytest.mark.asyncio
async def test_upload_and_download_by_chat_collaborator(client: AppClient):
    user = await create_user(email="uploader@convictional.com")
    other_member = await create_user(email="downloader@convictional.com", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other_member.id)

    claim_id = str(uuid4())

    # Chat uploads now flow through the shared workspace-scoped endpoint, gated by
    # get_workspace (which resolves the chat as the workspace resource).
    with client.current_user_as(user):
        response = await client.post(
            f"/api/workspaces/{chat.workspace_id}/attachments",
            files={"files": ("test.txt", b"hello world", "text/plain")},
            data={"claim_id": claim_id},
        )
        assert response.status_code == status.HTTP_201_CREATED

        download_url = response.json()["attachments"][0]["download_url"]
        assert f"/workspaces/{chat.workspace_id}/attachments/" in download_url
        assert "/download" in download_url

    attachment = await Attachment.filter(user_id=user.id).first()
    assert attachment is not None
    assert attachment.workspace_id == chat.workspace_id
    assert attachment.claim_id is not None

    # Simulate the claim flow: create a message and claim the attachment
    message = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Check this file")
    attachment.comment_gid = message.global_id
    attachment.claim_id = None
    await attachment.save()

    with client.current_user_as(other_member):
        # Collaborator can download via the workspace route the upload returned.
        response = await client.get(download_url, follow_redirects=False)
        assert response.status_code == status.HTTP_302_FOUND

        # The retained chat download route still serves claimed attachments, since
        # historical messages embed its URLs in their content.
        response = await client.get(
            f"/chats/{chat.id}/attachments/{attachment.id}/download",
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_302_FOUND


@pytest.mark.asyncio
async def test_non_member_denied_upload_and_download(client: AppClient):
    member = await create_user(email="member@convictional.com")
    outsider = await create_user(email="outsider@convictional.com", organization_id=member.organization_id)

    chat = await create_chat(organization_id=member.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=member.id)

    # Non-members can't upload to the chat's workspace.
    with client.current_user_as(outsider):
        response = await client.post(
            f"/api/workspaces/{chat.workspace_id}/attachments",
            files={"files": ("secret.txt", b"should not work", "text/plain")},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    message = await create_chat_message(chat_id=chat.id, user_id=member.id, content="Check this file")
    attachment = await create_attachment(user_id=member.id, workspace_id=None)
    attachment.comment_gid = message.global_id
    attachment.claim_id = None
    await attachment.save()

    with client.current_user_as(outsider):
        response = await client.get(
            f"/chats/{chat.id}/attachments/{attachment.id}/download",
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_cross_chat_access_denial(client: AppClient):
    user_a = await create_user(email="user-a@convictional.com")
    user_b = await create_user(email="user-b@convictional.com", organization_id=user_a.organization_id)

    chat_a = await create_chat(organization_id=user_a.organization_id)
    await create_collaborator(workspace_id=chat_a.workspace_id, user_id=user_a.id)

    chat_b = await create_chat(organization_id=user_a.organization_id)
    await create_collaborator(workspace_id=chat_b.workspace_id, user_id=user_b.id)

    # Create a message and attachment in chat_b
    message = await create_chat_message(chat_id=chat_b.id, user_id=user_b.id, content="Private file")
    attachment = await create_attachment(user_id=user_b.id, workspace_id=None)
    attachment.comment_gid = message.global_id
    attachment.claim_id = None
    await attachment.save()

    # user_a is a member of chat_a but NOT chat_b -- should get 404 via chat_b's download route
    with client.current_user_as(user_a):
        response = await client.get(
            f"/chats/{chat_b.id}/attachments/{attachment.id}/download",
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_uploader_can_preview_unclaimed_attachments(client: AppClient):
    user = await create_user(email="uploader-preview@convictional.com")
    other_member = await create_user(email="other-preview@convictional.com", organization_id=user.organization_id)

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other_member.id)

    # Pending claim (has claim_id but no comment_gid) — uploader can preview
    attachment_pending = await create_attachment(
        user_id=user.id, workspace_id=None, claim_id=uuid4(), comment_gid=None
    )
    # Freshly uploaded (no claim_id, no comment_gid) — same code path, also uploader-only
    attachment_fresh = await create_attachment(user_id=user.id, workspace_id=None, claim_id=None, comment_gid=None)

    with client.current_user_as(user):
        for attachment in [attachment_pending, attachment_fresh]:
            response = await client.get(
                f"/chats/{chat.id}/attachments/{attachment.id}/download",
                follow_redirects=False,
            )
            assert response.status_code == status.HTTP_302_FOUND

    # Other member cannot download another user's unclaimed attachment
    with client.current_user_as(other_member):
        for attachment in [attachment_pending, attachment_fresh]:
            response = await client.get(
                f"/chats/{chat.id}/attachments/{attachment.id}/download",
                follow_redirects=False,
            )
            assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_download_blocked_for_invalid_attachment_states(client: AppClient):
    user = await create_user(email="states@convictional.com")

    chat = await create_chat(organization_id=user.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=user.id)

    # Soft-deleted message
    message = await create_chat_message(chat_id=chat.id, user_id=user.id, content="Ephemeral file")
    attachment_deleted = await create_attachment(user_id=user.id, workspace_id=None)
    attachment_deleted.comment_gid = message.global_id
    attachment_deleted.claim_id = None
    await attachment_deleted.save()

    message.deleted_at = datetime.now(UTC)
    await message.save()

    with client.current_user_as(user):
        response = await client.get(
            f"/chats/{chat.id}/attachments/{attachment_deleted.id}/download",
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
