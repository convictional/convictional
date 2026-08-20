import html
import mimetypes
import re
from dataclasses import dataclass
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import format_datetime

from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailDraft
from app.routers.email_attachments import signed_attachment_download_url
from infra.email import EmailAttachment as EmailAttachmentPayload
from infra.email import EmailMessage as EmailPayload

MAX_TOTAL_ATTACHMENT_SIZE = 18 * 1024 * 1024  # 18 MB total limit


@dataclass
class EmailMimeBuilder:
    """Handles building MIME messages from email data with attachment processing."""

    @classmethod
    async def build_mime_string_from_draft(cls, email_draft: EmailDraft, include_bcc: bool = False) -> str:
        """Build a properly formatted RFC 2822 MIME message directly from an EmailMessage."""
        payload = await email_draft.as_payload()

        # Check if any attachments need to be replaced with download links
        _, attachments_to_replace = cls._process_attachments_with_size_limits(payload.attachments or [])

        # If we have attachments to replace, modify the email body to include download links
        if attachments_to_replace:
            # Add the notice to both text and HTML versions
            if payload.text:
                text_notice = cls._build_text_attachment_replacement_notice(attachments_to_replace)
                payload.text = payload.text + "\n\n" + text_notice

            if payload.html:
                html_notice = cls._build_html_attachment_replacement_notice(attachments_to_replace)
                payload.html = payload.html + html_notice

        return cls.build_mime_string(payload, include_bcc)

    @classmethod
    def build_mime_string(cls, email_message: EmailPayload, include_bcc: bool = False) -> str:
        """Build a properly formatted RFC 2822 MIME message with body and attachments."""
        # Process attachments with size limits in original order
        attachments_to_include, _ = cls._process_attachments_with_size_limits(email_message.attachments or [])

        has_inline_attachments = any(att.is_inline for att in attachments_to_include)

        msg = MIMEMultipart("mixed")

        alt = MIMEMultipart("alternative")
        if email_message.text:
            alt.attach(MIMEText(email_message.text, "plain", "utf-8"))
        if email_message.html:
            # Convert HTML for email MIME (replace attachment URLs with cid: references)
            email_html = cls._convert_html_for_email_mime(email_message.html, attachments_to_include)
            email_html = cls._strip_internal_attachment_links(email_html, attachments_to_include)
            email_html = cls._preserve_whitespace_for_external_clients(email_html)
            alt.attach(MIMEText(email_html, "html", "utf-8"))

        if has_inline_attachments:
            related = MIMEMultipart("related")
            related.attach(alt)

            for att in attachments_to_include:
                if att.is_inline:
                    inline_part = cls._build_attachment_part(att)
                    inline_part.add_header("Content-ID", f"<{att.content_id}>")
                    inline_part.add_header("Content-Disposition", "inline", filename=att.filename)
                    related.attach(inline_part)

            msg.attach(related)
        else:
            msg.attach(alt)

        # Regular attachments
        for att in attachments_to_include:
            if not att.is_inline:
                attachment_part = cls._build_attachment_part(att)
                attachment_part.add_header("Content-Disposition", "attachment", filename=att.filename)
                msg.attach(attachment_part)

        # Set headers
        cls._set_message_headers(msg, email_message, include_bcc=include_bcc)
        return msg.as_string()

    @classmethod
    def _build_text_attachment_replacement_notice(cls, attachments_to_replace: list[EmailAttachmentPayload]) -> str:
        """Build a notice explaining replaced attachments with download links."""
        if not attachments_to_replace:
            return ""

        notice_lines = [
            "The following attachments were too large to include in this email and are available for download:",
            "",
        ]

        for attachment in attachments_to_replace:
            size_mb = (attachment.file_byte_size or 0) / (1024 * 1024)
            # The signed public link is the capability external recipients can actually use;
            # attachment.download_url is the auth-gated internal route they can't reach.
            download_url = (
                signed_attachment_download_url(attachment.id) if attachment.id else None
            ) or attachment.download_url
            if download_url:
                notice_lines.append(f"- {attachment.filename} ({size_mb:.1f}MB) - Download: {download_url}")
            else:  # This should never happen, but handle gracefully
                notice_lines.append(f"- {attachment.filename} ({size_mb:.1f}MB) - Contact sender for download link")

        return "\n".join(notice_lines)

    @classmethod
    def _build_html_attachment_replacement_notice(cls, attachments_to_replace: list[EmailAttachmentPayload]) -> str:
        """Build an HTML notice explaining replaced attachments with download links."""
        if not attachments_to_replace:
            return ""

        html_parts = [
            "<br><br>",
            (
                "<p><strong>"
                "The following attachments were too large to include in this email and are available for download:"
                "</strong></p>"
            ),
            "<ul>",
        ]

        for attachment in attachments_to_replace:
            size_mb = (attachment.file_byte_size or 0) / (1024 * 1024)
            # Filenames are attacker-controllable and land in the recipient's HTML email,
            # so escape them to prevent markup injection (e.g. a swapped-in phishing link).
            filename = html.escape(attachment.filename or "")
            # The signed public link is the capability external recipients can actually use;
            # attachment.download_url is the auth-gated internal route they can't reach.
            download_url = (
                signed_attachment_download_url(attachment.id) if attachment.id else None
            ) or attachment.download_url
            if download_url:
                html_parts.append(f"<li>{filename} ({size_mb:.1f}MB) - <a href='{download_url}'>Download</a></li>")
            else:  # This should never happen, but handle gracefully
                html_parts.append(f"<li>{filename} ({size_mb:.1f}MB) - Contact sender for download link</li>")

        html_parts.extend(["</ul>"])

        return "".join(html_parts)

    @classmethod
    def _process_attachments_with_size_limits(
        cls,
        attachments: list[EmailAttachmentPayload],
    ) -> tuple[list[EmailAttachmentPayload], list[EmailAttachmentPayload]]:
        if not attachments:
            return [], []

        attachments_to_include = []
        attachments_to_replace = []
        current_total_size = 0

        # Process attachments in their original order
        for attachment in attachments:
            attachment_size = attachment.file_byte_size or 0

            # Check individual size limit
            if attachment.is_oversized:
                attachments_to_replace.append(attachment)
                continue

            # Check total size limit
            if current_total_size + attachment_size > MAX_TOTAL_ATTACHMENT_SIZE:
                attachments_to_replace.append(attachment)
                continue

            # Attachment can be included
            attachments_to_include.append(attachment)
            current_total_size += attachment_size

        return attachments_to_include, attachments_to_replace

    @classmethod
    def _convert_html_for_email_mime(cls, html_content: str, attachments: list[EmailAttachmentPayload]) -> str:
        """Convert HTML content for email MIME by replacing attachment URLs with cid: references."""
        if not html_content or not attachments:
            return html_content

        email_html = html_content

        for attachment in attachments:
            if attachment.is_inline and attachment.content_id and attachment.download_url:
                # Replace exact download URL with cid reference
                email_html = email_html.replace(attachment.download_url, f"cid:{attachment.content_id}")

        return email_html

    @classmethod
    def _strip_internal_attachment_links(cls, html_content: str, attachments: list[EmailAttachmentPayload]) -> str:
        if not html_content or not attachments:
            return html_content

        # External recipients can't reach the auth-gated internal workspace download route,
        # so the anchor is dead; the file still arrives as a real MIME attachment.
        download_urls = {
            attachment.download_url
            for attachment in attachments
            if not attachment.is_inline and attachment.download_url
        }
        if not download_urls:
            return html_content

        # Substitute on the raw string, not via BeautifulSoup: str(soup) re-serializes
        # the whole body and silently mutates unrelated content (decodes entities like
        # &nbsp;, rewrites <br> to <br/>, reorders attributes). This must touch only the
        # matched anchors.
        result = html_content
        for url in download_urls:
            pattern = re.compile(
                rf'<a\b[^>]*\bhref\s*=\s*(["\']){re.escape(url)}\1[^>]*>(.*?)</a\s*>',
                re.DOTALL | re.IGNORECASE,
            )
            result = pattern.sub(lambda match: match.group(2), result)

        return result

    @classmethod
    def _preserve_whitespace_for_external_clients(cls, html_content: str) -> str:
        # External clients (Gmail, Outlook, Apple Mail) render with their own engines and
        # don't load our email.css, so carry authored whitespace fidelity in an inline
        # white-space: pre-wrap container. The body is already whitespace-tight from
        # render_email_html, so this only adds the wrapper. Best-effort only — byte-exact
        # rendering in third-party clients is not guaranteed (see the whitespace-fidelity
        # plan's scope boundaries). <pre>/<code> keep their own white-space via the UA
        # stylesheet, which wins over the inherited pre-wrap value.
        if not html_content:
            return html_content
        return f'<div style="white-space: pre-wrap;">{html_content}</div>'

    @classmethod
    def _build_attachment_part(cls, attachment: EmailAttachmentPayload) -> MIMEBase:
        """Build and encode an attachment part."""
        mime_type, _ = mimetypes.guess_type(attachment.filename or "")
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)

        part = MIMEBase(maintype, subtype)
        part.set_payload(attachment.content)
        encoders.encode_base64(part)
        return part

    @classmethod
    def _set_message_headers(cls, msg: MIMEMultipart, email_message: EmailPayload, include_bcc: bool = False) -> None:
        msg["From"] = email_message.display_from or ""

        filtered_to = cls._filter_valid_emails(email_message.to or "")
        if filtered_to:
            msg["To"] = filtered_to
        else:
            msg["To"] = ""

        filtered_cc = cls._filter_valid_emails(email_message.cc or "")
        if filtered_cc:
            msg["Cc"] = filtered_cc

        if include_bcc:
            filtered_bcc = cls._filter_valid_emails(email_message.bcc or "")
            if filtered_bcc:
                msg["Bcc"] = filtered_bcc

        msg["Subject"] = email_message.subject or ""
        if email_message.sent_at:
            msg["Date"] = format_datetime(email_message.sent_at)

        # Add threading headers for proper email thread association
        if email_message.in_reply_to:
            msg["In-Reply-To"] = email_message.in_reply_to
        if email_message.references:
            msg["References"] = email_message.references

    @classmethod
    def _filter_valid_emails(cls, email_list: str | None) -> str:
        if not email_list:
            return ""

        emails = [email.strip() for email in email_list.split(",")]
        valid_emails = [email for email in emails if EmailAddress.is_valid_email(email)]

        return ", ".join(valid_emails)
