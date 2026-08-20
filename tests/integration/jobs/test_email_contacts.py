from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.email_contacts import UpdateContactInteractionsJob
from app.models.workspaces.email.contact import EmailContact
from config.enums import EmailMessageType
from tests.helpers.factories import create_email_message, create_user


@pytest.mark.asyncio
async def test_update_contact_interactions_job():
    user = await create_user(email="test@example.com")

    contact1 = await EmailContact.create(
        email="contact1@example.com",
        name="Contact 1",
        user_id=user.id,
        organization_id=user.organization_id,
    )
    contact2 = await EmailContact.create(
        email="contact2@example.com",
        name="Contact 2",
        user_id=user.id,
        organization_id=user.organization_id,
    )
    contact3 = await EmailContact.create(
        email="contact3@example.com",
        name="Contact 3",
        user_id=user.id,
        organization_id=user.organization_id,
    )

    very_old_time = datetime.now(UTC) - timedelta(days=10)
    older_time = datetime.now(UTC) - timedelta(days=5)
    recent_time = datetime.now(UTC) - timedelta(hours=1)

    contact1.last_interacted_at = very_old_time
    await contact1.save(update_fields=["last_interacted_at"])
    contact2.last_interacted_at = very_old_time
    await contact2.save(update_fields=["last_interacted_at"])
    contact3.last_interacted_at = very_old_time
    await contact3.save(update_fields=["last_interacted_at"])

    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.RECEIVED,
        sender="contact1@example.com",
        received_at=older_time,
    )

    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.SENT,
        to=["contact1@example.com"],
        sent_at=recent_time,
    )

    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.RECEIVED,
        sender="contact2@example.com",
        received_at=older_time,
    )

    initial_contact1_timestamp = contact1.last_interacted_at
    initial_contact2_timestamp = contact2.last_interacted_at
    initial_contact3_timestamp = contact3.last_interacted_at

    job = UpdateContactInteractionsJob(user_id=user.id)
    await job.perform()

    await contact1.refresh_from_db()
    await contact2.refresh_from_db()
    await contact3.refresh_from_db()

    assert contact1.last_interacted_at > initial_contact1_timestamp
    assert (contact1.last_interacted_at - recent_time).total_seconds() < 2

    assert contact2.last_interacted_at > initial_contact2_timestamp
    assert (contact2.last_interacted_at - older_time).total_seconds() < 2

    assert contact3.last_interacted_at == initial_contact3_timestamp


@pytest.mark.asyncio
async def test_update_contact_interactions_job_with_date_filter():
    user = await create_user(email="test@example.com")

    contact1 = await EmailContact.create(
        email="contact1@example.com",
        name="Contact 1",
        user_id=user.id,
        organization_id=user.organization_id,
    )
    contact2 = await EmailContact.create(
        email="contact2@example.com",
        name="Contact 2",
        user_id=user.id,
        organization_id=user.organization_id,
    )

    very_old_time = datetime.now(UTC) - timedelta(hours=240)
    old_time = datetime.now(UTC) - timedelta(hours=192)
    recent_time = datetime.now(UTC) - timedelta(hours=48)

    contact1.last_interacted_at = very_old_time
    await contact1.save(update_fields=["last_interacted_at"])
    contact2.last_interacted_at = very_old_time
    await contact2.save(update_fields=["last_interacted_at"])

    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.RECEIVED,
        sender="contact1@example.com",
        received_at=old_time,
    )

    await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.SENT,
        to=["contact2@example.com"],
        sent_at=recent_time,
    )

    initial_contact1_timestamp = contact1.last_interacted_at
    initial_contact2_timestamp = contact2.last_interacted_at

    job = UpdateContactInteractionsJob(user_id=user.id, window_hours=168)
    await job.perform()

    await contact1.refresh_from_db()
    await contact2.refresh_from_db()

    assert contact1.last_interacted_at == initial_contact1_timestamp
    assert contact2.last_interacted_at > initial_contact2_timestamp
    assert (contact2.last_interacted_at - recent_time).total_seconds() < 2
