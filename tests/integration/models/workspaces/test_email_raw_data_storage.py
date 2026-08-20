import json

import pytest

from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailThread
from config.enums import EmailLabel, EmailMessageType
from infra.email import EmailHeaders
from infra.storage import FileReference
from tests.helpers.factories import create_user


@pytest.mark.asyncio
async def test_receive_message_creates_file_reference_for_raw_data():
    user = await create_user()

    raw_data = {
        "id": "msg123",
        "threadId": "thread123",
        "labelIds": ["INBOX"],
        "snippet": "Test message",
        "payload": {"headers": [{"name": "Subject", "value": "Test"}]},
        "internalDate": "1234567890000",
    }

    message_data = {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "external_message_id": "msg123",
        "external_thread_id": "thread123",
        "message_type": EmailMessageType.RECEIVED,
        "subject": "Test",
        "sender": "sender@example.com",
        "to": ["test@example.com"],
        "cc": [],
        "bcc": [],
        "body_plain": "Test body",
        "labels": [EmailLabel.INBOX],
        "raw_data": raw_data,
        "headers_list": [{"name": "Subject", "value": "Test"}],
        "has_jsonb_migrated": True,
    }

    result = await EmailThread.receive_new_message(message_data)
    message = result.email

    # Verify raw_data_file_id is set
    assert message.raw_data_file_id is not None

    # Verify the FileReference exists
    file_ref = await FileReference.get(id=message.raw_data_file_id)
    assert file_ref is not None
    assert file_ref.content_type == "application/json"
    assert "raw_data_" in file_ref.filename

    # Verify the file content matches the raw_data
    file_content = await file_ref.download()
    stored_data = json.loads(file_content.decode())
    assert stored_data == raw_data


@pytest.mark.asyncio
async def test_receive_message_without_raw_data_no_file_reference():
    user = await create_user()

    message_data = {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "external_message_id": "msg456",
        "external_thread_id": "thread456",
        "message_type": EmailMessageType.RECEIVED,
        "subject": "Test",
        "sender": "sender@example.com",
        "to": ["test@example.com"],
        "cc": [],
        "bcc": [],
        "body_plain": "Test body",
        "labels": [EmailLabel.INBOX],
        "headers_list": [{"name": "Subject", "value": "Test"}],
        "has_jsonb_migrated": True,
    }

    result = await EmailThread.receive_new_message(message_data)
    message = result.email

    # Verify no file reference is created when raw_data is not provided
    assert message.raw_data_file_id is None


@pytest.mark.asyncio
async def test_mark_draft_as_sent_creates_file_reference_for_raw_data():
    user = await create_user()

    thread = await EmailThread.create(
        creator_id=user.id,
        organization_id=user.organization_id,
        title="Test Thread",
        labels=[EmailLabel.DRAFT],
        has_unread=False,
    )

    draft = await thread.start_draft(
        user=user,
        subject="Test Draft",
        to=["recipient@example.com"],
        body_plain="Draft body",
    )

    raw_data = {
        "id": "sent123",
        "threadId": "thread789",
        "labelIds": ["SENT"],
        "snippet": "Sent message",
    }

    await draft.mark_as_sent(
        sent_from=EmailAddress.build(user.email, user.name),
        external_message_id="sent123",
        external_thread_id="thread789",
        external_history_id="hist123",
        message_id="<sent123@example.com>",
        headers=EmailHeaders([{"name": "Subject", "value": "Test Draft"}]),
        preview="Sent message",
        raw_data=raw_data,
    )

    # Refresh the message
    await draft.message.refresh_from_db()

    # Verify raw_data_file_id is set
    assert draft.message.raw_data_file_id is not None

    # Verify the FileReference exists
    file_ref = await FileReference.get(id=draft.message.raw_data_file_id)
    assert file_ref is not None
    assert file_ref.content_type == "application/json"

    # Verify the file content matches the raw_data
    file_content = await file_ref.download()
    stored_data = json.loads(file_content.decode())
    assert stored_data == raw_data


@pytest.mark.asyncio
async def test_mark_draft_as_sent_without_raw_data_no_file_reference():
    user = await create_user()

    thread = await EmailThread.create(
        creator_id=user.id,
        organization_id=user.organization_id,
        title="Test Thread",
        labels=[EmailLabel.DRAFT],
        has_unread=False,
    )

    draft = await thread.start_draft(
        user=user,
        subject="Test Draft",
        to=["recipient@example.com"],
        body_plain="Draft body",
    )

    await draft.mark_as_sent(
        sent_from=EmailAddress.build(user.email, user.name),
        external_message_id="sent456",
        external_thread_id="thread999",
        external_history_id="hist456",
        message_id="<sent456@example.com>",
        headers=EmailHeaders([{"name": "Subject", "value": "Test Draft"}]),
        preview="Sent message",
        raw_data=None,
    )

    # Refresh the message
    await draft.message.refresh_from_db()

    # Verify no file reference is created when raw_data is None
    assert draft.message.raw_data_file_id is None


@pytest.mark.asyncio
async def test_get_raw_data_reads_from_gcs_file():
    user = await create_user()

    raw_data = {
        "id": "msg_gcs",
        "threadId": "thread_gcs",
        "labelIds": ["INBOX"],
        "snippet": "GCS Test",
    }

    message_data = {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "external_message_id": "msg_gcs",
        "external_thread_id": "thread_gcs",
        "message_type": EmailMessageType.RECEIVED,
        "subject": "GCS Test",
        "sender": "sender@example.com",
        "to": ["test@example.com"],
        "cc": [],
        "bcc": [],
        "body_plain": "Test body",
        "labels": [EmailLabel.INBOX],
        "raw_data": raw_data,
        "headers_list": [{"name": "Subject", "value": "GCS Test"}],
        "has_jsonb_migrated": True,
    }

    result = await EmailThread.receive_new_message(message_data)
    message = result.email

    retrieved_data = await message.get_raw_data()
    assert retrieved_data == raw_data


@pytest.mark.asyncio
async def test_get_raw_data_returns_none_without_file():
    user = await create_user()

    message_data = {
        "user_id": user.id,
        "organization_id": user.organization_id,
        "external_message_id": "msg_column",
        "external_thread_id": "thread_column",
        "message_type": EmailMessageType.RECEIVED,
        "subject": "Column Test",
        "sender": "sender@example.com",
        "to": ["test@example.com"],
        "cc": [],
        "bcc": [],
        "body_plain": "Test body",
        "labels": [EmailLabel.INBOX],
        "headers_list": [{"name": "Subject", "value": "Column Test"}],
        "has_jsonb_migrated": True,
    }

    result = await EmailThread.receive_new_message(message_data)
    message = result.email

    message.raw_data_file_id = None
    await message.save(update_fields=["raw_data_file_id"])

    retrieved_data = await message.get_raw_data()
    assert retrieved_data is None
