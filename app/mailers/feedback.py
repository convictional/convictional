from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.models.collaboration.workspace import Attachment
from config import settings
from infra.email import EmailAttachment, EmailMessage, Mailer


@dataclass
class FeedbackMailer(Mailer):
    url: str = ""
    description: str = ""
    user_email: str = ""
    attachment_ids: list[UUID] | None = None
    sentry_event_id: str | None = None

    def __post_init__(self):
        if self.attachment_ids is None:
            self.attachment_ids = []

    async def send(self):
        # No operator contact address configured means nobody is meant to receive
        # feedback mail, not that it should be sent to an empty recipient.
        if not settings.feedback_email:
            return None

        message = await self.feedback_received_email()
        return await self.deliver(message)

    async def feedback_received_email(self) -> EmailMessage:
        message = EmailMessage(to=settings.feedback_email)

        # Process attachments and convert URLs to inline attachments
        processed_description, inline_attachments = await self._process_attachment_urls(self.description)
        message.attachments = inline_attachments

        return self.render(
            message,
            "feedback_received.jinja",
            url=self.url,
            description=processed_description,
            user_email=self.user_email,
            now=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            sentry_feedback_url=self._build_sentry_feedback_url(),
        )

    def _build_sentry_feedback_url(self) -> str | None:
        if not (self.sentry_event_id and settings.has_sentry):
            return None
        return (
            f"https://{settings.sentry_org}.sentry.io/issues/feedback/"
            f"?projectSlug={settings.sentry_project}&eventId={self.sentry_event_id}"
            f"&project={settings.sentry_project_id}"
        )

    async def _process_attachment_urls(self, text: str) -> tuple[str, list[EmailAttachment]]:
        """Parse text for attachment URLs and replace them with inline references."""
        if not self.attachment_ids:
            return text, []

        inline_attachments = []
        processed_text = text

        # Process each claimed attachment
        for attachment_id in self.attachment_ids:
            try:
                attachment = await Attachment.get(id=attachment_id).prefetch_related("file")

                # Get all possible download URLs for this attachment
                download_urls = attachment.download_urls

                # Check if any of the download URLs appear in the text
                found_in_text = False
                for url in download_urls:
                    if url in text:
                        found_in_text = True
                        break

                if not found_in_text:
                    continue

                # Generate unique content ID for this attachment
                content_id = f"attachment_{attachment_id}"

                # Download file content
                file_content = await attachment.file.download()

                # Create inline email attachment
                email_attachment = EmailAttachment(
                    content_id=content_id,
                    is_inline=True,
                    filename=attachment.file.filename,
                    content_type=attachment.file.content_type,
                    content=file_content,
                    file_byte_size=attachment.file.byte_size,
                )
                inline_attachments.append(email_attachment)

                # Replace all download URLs for this attachment with cid reference
                new_cid_ref = f"cid:{content_id}"
                for url in download_urls:
                    processed_text = processed_text.replace(url, new_cid_ref)

            except Exception:
                # If attachment processing fails, leave the original URLs
                continue

        return processed_text, inline_attachments
