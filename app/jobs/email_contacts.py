from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.jobs.content import ContentIndexingJob
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.contact import EmailContact
from app.models.workspaces.email.thread import EmailMessage, EmailMessageFilters
from config import logger
from config.enums import JobQueue
from infra.jobs import JobDefinition, enqueue_job

BATCH_SIZE = 100


class UpdateContactInteractionsJob(JobDefinition):
    default_queue = JobQueue.MISCELLANEOUS
    user_id: UUID
    window_hours: int | None = 336  # 14 days

    async def perform(self):
        contacts = await EmailContact.filter(user_id=self.user_id).all()

        if not contacts:
            return

        contact_emails = set()
        for contact in contacts:
            parsed = EmailAddress.parse_safe(contact.email)
            if parsed:
                contact_emails.add(parsed.email.lower().strip())

        email_timestamps: dict[str, datetime] = {}

        since = None
        if self.window_hours is not None:
            since = datetime.now(UTC) - timedelta(hours=self.window_hours)

        offset = 0
        while len(email_timestamps) < len(contact_emails):
            received_messages = (
                await EmailMessage.filter(EmailMessageFilters.by_user(self.user_id))
                .filter(EmailMessageFilters.by_received(since))
                .order_by("-received_at")
                .only("sender", "received_at")
                .offset(offset)
                .limit(BATCH_SIZE)
            )

            if not received_messages:
                break

            for message in received_messages:
                if not message.sender:
                    continue
                sender_parsed = EmailAddress.parse_safe(message.sender)
                if not sender_parsed:
                    continue
                sender_email = sender_parsed.email.lower().strip()

                if sender_email in contact_emails and sender_email not in email_timestamps and message.received_at:
                    email_timestamps[sender_email] = message.received_at

            # Stop once we've found timestamps for all contacts (ordered newest first)
            if len(email_timestamps) == len(contact_emails):
                break

            offset += BATCH_SIZE

        offset = 0
        while len(email_timestamps) < len(contact_emails):
            sent_messages = (
                await EmailMessage.filter(EmailMessageFilters.by_user(self.user_id))
                .filter(EmailMessageFilters.by_sent(since))
                .order_by("-sent_at")
                .only("to", "cc", "bcc", "sent_at")
                .offset(offset)
                .limit(BATCH_SIZE)
            )

            if not sent_messages:
                break

            for message in sent_messages:
                if not message.sent_at:
                    continue
                for recipient in message.recipient_addresses:
                    recipient_email = recipient.email.lower().strip()
                    if recipient_email not in contact_emails:
                        continue

                    existing = email_timestamps.get(recipient_email)
                    if existing is None or message.sent_at > existing:
                        email_timestamps[recipient_email] = message.sent_at

            # Stop once we've found timestamps for all contacts (ordered newest first)
            if len(email_timestamps) == len(contact_emails):
                break

            offset += BATCH_SIZE

        updated_count = 0
        for contact in contacts:
            parsed = EmailAddress.parse_safe(contact.email)
            if not parsed:
                continue

            normalized_email = parsed.email.lower().strip()
            timestamp = email_timestamps.get(normalized_email)

            if timestamp and (contact.last_interacted_at is None or timestamp > contact.last_interacted_at):
                contact.last_interacted_at = timestamp
                await contact.save(update_fields=["last_interacted_at"])
                # Reindex so the lookup recency boost and display timestamp reflect the new interaction.
                await enqueue_job(ContentIndexingJob.from_model(contact.organization_id, contact))
                updated_count += 1

        logger.info(f"Updated {updated_count} contact interaction timestamps for user {self.user_id}")
