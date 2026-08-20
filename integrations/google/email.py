from uuid import UUID

from tortoise import BaseDBAsyncClient

from config.enums import EmailLabel
from infra.email import EmailClient
from infra.jobs import enqueue_job
from integrations.google.constants import EMAIL_LABEL_TO_GMAIL
from integrations.google.jobs.gmail import (
    SendEmailThroughGmailJob,
    UpdateGmailThreadLabelsJob,
)


class GmailClient(EmailClient):
    async def send_message(
        self, email_thread_id: UUID | None, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        await enqueue_job(
            SendEmailThroughGmailJob(email_thread_id=email_thread_id, sender_user_id=user_id), using_db=using_db
        )

    async def mark_thread_read(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        await enqueue_job(
            UpdateGmailThreadLabelsJob(
                external_thread_id=external_thread_id,
                user_id=user_id,
                labels_to_remove=[EMAIL_LABEL_TO_GMAIL[EmailLabel.UNREAD]],
            ),
            using_db=using_db,
        )

    async def mark_thread_unread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        await enqueue_job(
            UpdateGmailThreadLabelsJob(
                external_thread_id=external_thread_id,
                user_id=user_id,
                labels_to_add=[EMAIL_LABEL_TO_GMAIL[EmailLabel.UNREAD]],
            ),
            using_db=using_db,
        )

    async def archive_thread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        await enqueue_job(
            UpdateGmailThreadLabelsJob(
                user_id=user_id,
                external_thread_id=external_thread_id,
                labels_to_remove=[EMAIL_LABEL_TO_GMAIL[EmailLabel.INBOX]],
            ),
            using_db=using_db,
        )

    async def unarchive_thread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        await enqueue_job(
            UpdateGmailThreadLabelsJob(
                user_id=user_id,
                external_thread_id=external_thread_id,
                labels_to_add=[EMAIL_LABEL_TO_GMAIL[EmailLabel.INBOX]],
            ),
            using_db=using_db,
        )
