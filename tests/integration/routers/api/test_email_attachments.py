import io
from uuid import uuid4

import pytest
from fastapi import status

from app.models.workspaces.email.thread import EmailAttachment, EmailThread
from config.enums import EmailMessageType
from infra.storage import store_file
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_message


async def _seed_draft_with_attachment(user):
    draft = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Draft",
        to=["x@y.com"],
    )
    file_ref = await store_file(content=io.BytesIO(b"hi"), filename="hi.txt", content_type="text/plain")
    attachment = await EmailAttachment.create(
        email_message_id=draft.id,
        thread_id=draft.thread_id,
        file=file_ref,
        is_inline=False,
    )
    return draft, attachment


@pytest.mark.asyncio
async def test_list_returns_attachments(client: AppClient):
    user = await client.get_default_user()
    draft, attachment = await _seed_draft_with_attachment(user)

    response = await client.get(f"/api/email_threads/{draft.thread_id}/draft/attachments")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert len(body["attachments"]) == 1
    item = body["attachments"][0]
    assert item["id"] == str(attachment.id)
    assert item["filename"] == "hi.txt"
    assert item["is_inline"] is False
    assert item["download_url"]


@pytest.mark.asyncio
async def test_delete_existing_attachment(client: AppClient):
    user = await client.get_default_user()
    draft, attachment = await _seed_draft_with_attachment(user)

    response = await client.delete(f"/api/email_threads/{draft.thread_id}/draft/attachments/{attachment.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert await EmailAttachment.get_or_none(id=attachment.id) is None


@pytest.mark.asyncio
async def test_delete_missing_attachment_returns_404(client: AppClient):
    user = await client.get_default_user()
    draft = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Draft",
        to=["x@y.com"],
    )
    thread = await EmailThread.get(id=draft.thread_id)

    response = await client.delete(f"/api/email_threads/{thread.id}/draft/attachments/{uuid4()}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
