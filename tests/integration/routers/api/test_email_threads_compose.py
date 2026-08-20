import pytest
from fastapi import status

from app.models.workspaces.email.thread import EmailMessage, EmailThread
from config.enums import EmailMessageType, EmailReplyType
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_message


@pytest.mark.asyncio
async def test_create_thread_returns_thread_id_and_starts_draft(client: AppClient):
    await client.get_default_user()

    response = await client.post("/api/email_threads")
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["thread_id"]
    assert "redirect_url" not in body
    assert "draft_message_id" not in body

    thread = await EmailThread.get(id=body["thread_id"])
    draft = await EmailMessage.get(thread_id=thread.id, message_type=EmailMessageType.DRAFT)
    assert draft.message_type == EmailMessageType.DRAFT


@pytest.mark.asyncio
async def test_reply_happy_path(client: AppClient):
    user = await client.get_default_user()
    received = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="reply_happy_path",
        subject="Original",
        sender="sender@example.com",
    )

    response = await client.post(
        f"/api/email_threads/{received.thread_id}/email_messages/{received.id}/reply",
        json={"reply_type": EmailReplyType.REPLY.value, "replace_existing": False},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["draft_message_id"]

    thread = await EmailThread.get(id=received.thread_id)
    draft = await thread.get_draft()
    assert draft is not None
    assert str(draft.message.id) == body["draft_message_id"]


@pytest.mark.asyncio
async def test_reply_conflict_returns_409(client: AppClient):
    user = await client.get_default_user()
    received = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="reply_conflict",
        subject="Original",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=received.thread_id)
    await thread.start_draft(user=user, subject="Re: Original", body_plain="content")

    response = await client.post(
        f"/api/email_threads/{received.thread_id}/email_messages/{received.id}/reply",
        json={"reply_type": EmailReplyType.REPLY.value, "replace_existing": False},
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json() == {"existing_draft": True}


@pytest.mark.asyncio
async def test_reply_replace_existing_swaps_draft(client: AppClient):
    user = await client.get_default_user()
    received = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="reply_replace",
        subject="Original",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=received.thread_id)
    first = await thread.start_draft(user=user, subject="Re: Original", body_plain="content")

    response = await client.post(
        f"/api/email_threads/{received.thread_id}/email_messages/{received.id}/reply",
        json={"reply_type": EmailReplyType.REPLY.value, "replace_existing": True},
    )
    assert response.status_code == status.HTTP_201_CREATED

    # The original draft is gone, replaced by a new one.
    assert await EmailMessage.get_or_none(id=first.message.id) is None
    current = await thread.get_draft()
    assert current is not None
    assert current.message.id != first.message.id


@pytest.mark.asyncio
async def test_forward_clones_attachments(client: AppClient):
    user = await client.get_default_user()
    received = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="forward_attach",
        subject="Original",
        sender="sender@example.com",
    )

    response = await client.post(
        f"/api/email_threads/{received.thread_id}/email_messages/{received.id}/forward",
        json={"replace_existing": False},
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["draft_message_id"]
