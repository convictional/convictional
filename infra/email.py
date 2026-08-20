import hashlib
import hmac
import html
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID
from uuid import uuid4 as generate_uuid

import httpx
import mistune
from fastapi import APIRouter, HTTPException, Request, status
from itsdangerous import URLSafeSerializer
from itsdangerous.exc import BadSignature
from jinja2 import Environment
from starlette.datastructures import FormData, UploadFile
from tortoise import BaseDBAsyncClient

from config import logger, settings
from config.settings import EmailClient as EmailClientEnum
from config.settings import EmailDelivery

#
# Signed attachment download links
#
#

_ATTACHMENT_DOWNLOAD_SALT = "email-attachment-download"


def _download_token_serializer() -> URLSafeSerializer:
    # Pin SHA-256 explicitly (itsdangerous defaults to SHA-1). These tokens never expire,
    # so the digest is effectively permanent — changing it later would invalidate every
    # outstanding link.
    return URLSafeSerializer(
        settings.secret_key.get_secret_value(),
        salt=_ATTACHMENT_DOWNLOAD_SALT,
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def sign_attachment_download_token(attachment_id: UUID) -> str:
    return _download_token_serializer().dumps(str(attachment_id))


def verify_attachment_download_token(token: str) -> UUID | None:
    """Return the attachment id a token grants, or None if it is invalid.

    Tokens never expire: recipients may open the email months later and the attachment
    must still download. The link stays stable while the route mints a fresh, short-lived
    GCS signed URL on each click.
    """
    try:
        attachment_id = _download_token_serializer().loads(token)
    except BadSignature:
        return None
    try:
        return UUID(attachment_id)
    except (ValueError, TypeError):
        return None


#
# Templates
#
#

templates = None


def register_email_templates(env: Environment):
    global templates
    templates = env
    templates.filters["markdown"] = mistune.html


@dataclass
class EmailRenderer:
    templates: Environment

    def __post_init__(self):
        self.templates.filters["markdown"] = mistune.html

    def render(self, message: "EmailMessage", template_name: str, **context) -> "EmailMessage":
        if not message.id:
            message.id = str(generate_uuid())

        template = self.templates.get_template(template_name)
        subject_block = template.blocks.get("subject")
        body_text_block = template.blocks.get("body_text")
        body_markdown_block = template.blocks.get("body_markdown")
        body_html_block = template.blocks.get("body_html")

        if not subject_block:
            raise ValueError("Template must define a subject block")
        if not body_text_block and not body_markdown_block:
            raise ValueError("Template must define a body_text or body_markdown block")
        if not body_markdown_block and not body_html_block:
            raise ValueError("Template must define a body_html or body_markdown block")

        message.subject = html.unescape("".join(subject_block(template.new_context(context))).strip())
        if body_markdown_block:
            rendered_markdown = "".join(body_markdown_block(template.new_context(context))).strip()
            message.text = rendered_markdown
            # Unescape HTML entities before passing to mistune since Jinja's autoescape
            # converts markdown content (e.g., <p> → &lt;p&gt;), but mistune expects
            # raw markdown and doesn't unescape. This prevents double-escaping in the final HTML.
            message.html = str(mistune.html(html.unescape(rendered_markdown))).strip()

        if body_text_block:
            message.text = "".join(body_text_block(template.new_context(context))).strip()
        if body_html_block:
            message.html = "".join(body_html_block(template.new_context(context))).strip()

        # Add invisible metadata to the email
        meta = self.templates.get_template("meta.jinja")
        message.html = message.html + meta.render(message=message, **context)

        return message


#
# Generic DTOs
#
#

MESSAGE_ID_REGEX = re.compile(r"<([^>]+)>")


class EmailHeaders(list):
    _index: dict[str, list[int]]

    def __init__(self, headers: list[dict[str, str]] | None = None):
        super().__init__(headers or [])
        self._index = {}
        for i, h in enumerate(self):
            self._index.setdefault(str(h["name"]).lower(), []).append(i)

    def get_one(self, name: str, default: str | None = None) -> str | None:
        indexes = self._index.get(name.lower())
        if not indexes:
            return default
        return self[indexes[0]]["value"]

    def get_all(self, name: str) -> list[str]:
        indexes = self._index.get(name.lower(), [])
        return [self[i]["value"] for i in indexes]

    @property
    def message_id(self) -> str | None:
        return self.get_one("Message-ID")

    @property
    def in_reply_to(self) -> str | None:
        return self.get_one("In-Reply-To")

    @property
    def reply_to(self) -> str | None:
        return self.get_one("Reply-To")

    @property
    def references(self) -> list[str]:
        raw = self.get_one("References")
        if not raw:
            return []
        hits = MESSAGE_ID_REGEX.findall(raw)
        if hits:
            return hits

        # Fallback: split on whitespace if no angle brackets were found
        return raw.strip().split()


@dataclass
class EmailAttachment:
    id: UUID | None = None
    external_attachment_id: str | None = None
    content_id: str | None = None
    is_inline: bool = False
    filename: str = "attachment"
    content_type: str = "application/octet-stream"
    content: bytes | str = b""
    file_byte_size: int | None = None
    download_url: str | None = None

    @property
    def is_oversized(self) -> bool:
        """The maximum size for a MIME string is 25MB.
        The maximum recommended size for all attachments is 18MB.
        Given there can be multiple attachments, we set a limit of 5MB per attachment.
        Any attachment larger than this will be considered oversized and will be linked instead of attached.
        """
        attachment_size_limit = 5 * 1024 * 1024  # 5 MB
        if self.file_byte_size is None:
            return False
        return self.file_byte_size > attachment_size_limit


@dataclass
class EmailMessage:
    id: str = ""
    to: str = ""
    cc: str = ""
    bcc: str = ""
    send_from: str = settings.email_from
    display_from: str = ""
    subject: str = ""
    text: str = ""
    html: str = ""
    in_reply_to: str = ""
    references: str = ""
    attachments: list[EmailAttachment] = field(default_factory=list)
    sent_at: datetime | None = None
    headers: EmailHeaders = field(default_factory=EmailHeaders)


#
# Outbound email
#
#


@dataclass
class FakeDelivery:
    messages: list[EmailMessage] = field(default_factory=list)

    async def deliver(self, message: EmailMessage) -> str:
        self.messages.append(message)
        return f"<{message.id}@fake.test>"

    def reset(self):
        self.messages = []

    def by_recipient(self, recipient: str):
        return [message for message in self.messages if message.to == recipient]


fake_delivery = FakeDelivery()


async def _delivery_browser(message: EmailMessage) -> str | None:
    import tempfile  # noqa: PLC0415
    import webbrowser  # noqa: PLC0415

    extension = ".html" if message.html else ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=extension, mode="w") as temp_file:
        display_from = f"{message.display_from} <{message.send_from}>" if message.display_from else message.send_from
        temp_file.write(f"<p>From: {display_from}</p>")
        temp_file.write(f"<p>To: {message.to}</p>")
        if message.cc:
            temp_file.write(f"<p>CC: {message.cc}</p>")
        if message.bcc:
            temp_file.write(f"<p>BCC: {message.bcc}</p>")
        temp_file.write(f"<p>Subject: {message.subject}</p>")
        if message.headers:
            temp_file.write("<p>Headers:</p><ul>")
            for header in message.headers:
                temp_file.write(f"<li>{header['name']}: {header['value']}</li>")
            temp_file.write("</ul>")
        temp_file.write(message.html or message.text)
        temp_file.flush()

        temp_file_path = temp_file.name
        webbrowser.open(f"file://{temp_file_path}", new=2)  # new=2 opens in a new tab

    if message.id:
        return f"<{message.id}@browser.local>"
    return None


async def _deliver_mailgun(message: EmailMessage) -> str | None:
    if not settings.has_mailgun:
        raise ValueError("Mailgun settings are not configured")

    url = f"https://api.mailgun.net/v3/{settings.mailgun_domain}/messages"
    auth = ("api", settings.mailgun_api_key.get_secret_value())
    display_from = message.display_from or settings.product_name
    data = {
        "from": f"{display_from} <{message.send_from}>",
        "to": message.to,
        "subject": message.subject,
        "text": message.text,
        "html": message.html,
    }
    if message.cc:
        data["cc"] = message.cc

    # The below fields are required for reply threading
    if message.in_reply_to:
        data["h:In-Reply-To"] = message.in_reply_to
    if message.references:
        data["h:References"] = message.references

    for header in message.headers:
        data[f"h:{header['name']}"] = header["value"]

    files = []
    inline_files = []
    for attachment in message.attachments:
        if attachment.is_inline and attachment.content_id:
            # Use 'inline' parameter for inline attachments with Content-ID
            inline_files.append(("inline", (attachment.content_id, attachment.content)))
        else:
            # Regular attachments
            files.append(("attachment", (attachment.filename, attachment.content)))

    # Combine regular attachments and inline attachments
    all_files = files + inline_files

    async with httpx.AsyncClient() as client:
        response = await client.post(url, auth=auth, data=data, files=all_files)
        response.raise_for_status()
        return response.json().get("id")


MAIL_DELIVERY = {
    EmailDelivery.FAKE: fake_delivery.deliver,
    EmailDelivery.MAILGUN: _deliver_mailgun,
}


class Mailer:
    """Base class for delivering transaction email."""

    def render(self, message: EmailMessage, template_name: str, **context) -> EmailMessage:
        if not templates:
            raise ValueError("Email templates have not been registered")

        renderer = EmailRenderer(templates)
        return renderer.render(message, template_name, **context)

    async def deliver(self, message: EmailMessage) -> str | None:
        sender = settings.email_delivery
        if sender not in MAIL_DELIVERY:
            raise ValueError(f"Invalid email sender: {sender}")

        if not message.id:
            message.id = str(generate_uuid())

        return await MAIL_DELIVERY[sender](message)


#
# Email client
#
#


class EmailClient(ABC):
    @abstractmethod
    async def send_message(
        self, email_thread_id: UUID | None, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass

    @abstractmethod
    async def mark_thread_read(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass

    @abstractmethod
    async def mark_thread_unread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass

    @abstractmethod
    async def archive_thread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass

    @abstractmethod
    async def unarchive_thread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass


email_clients: dict[EmailClientEnum, "EmailClient"] = {}


def register_email_client(key: EmailClientEnum, client: "EmailClient"):
    global email_clients
    email_clients[key] = client


def get_email_client() -> EmailClient:
    if settings.email_client not in email_clients:
        raise ValueError(f"Email client {settings.email_client} is not registered")
    return email_clients[settings.email_client]


#
# Inbound email
#
#


@dataclass
class InboundEmailAttachment:
    filename: str
    content_type: str
    data: bytes


@dataclass
class InboundEmailAttachmentStream:
    filename: str
    content_type: str
    response: httpx.Response


@dataclass
class InboundEmail:
    sender: str
    to: list[str]
    subject: str
    body_plain: str
    body_html: str = ""
    stripped_text: str = ""
    stripped_html: str = ""
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    message_headers: dict[str, str] = field(default_factory=dict)
    message_id: str = ""
    in_reply_to: str = ""
    references: str = ""
    timestamp: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def all_recipients(self):
        return set(self.to + self.cc + self.bcc)

    @property
    def all_recipient_emails(self):
        return [email.split("<")[-1].split(">")[0].strip() for email in self.all_recipients]

    @property
    def reference_ids(self):
        return re.findall(r"<[^>]+>", self.references)

    @property
    def received_at(self) -> datetime:
        return datetime.fromtimestamp(int(self.timestamp), tz=UTC)

    async def get_attachments(self) -> list[InboundEmailAttachment]:
        raise NotImplementedError()

    async def get_attachment_streams(self) -> list[InboundEmailAttachmentStream]:
        raise NotImplementedError()


class InboundEmailHandler(Protocol):
    async def __call__(self, email: InboundEmail) -> Any: ...


@dataclass
class InboundEmailRouter:
    # The address is a callable so a settings-derived route resolves at delivery time
    # rather than at import time, which is what lets an operator configure the inbound
    # address without the module import order deciding the answer.
    handlers: list[tuple[Callable[[], str], InboundEmailHandler]] = field(default_factory=list)
    api: APIRouter = field(default_factory=APIRouter)

    def __post_init__(self):
        self.api.post("/")(self.handle_webhook)

    def register_handler(self, address: Callable[[], str]) -> Any:
        def decorator(func: InboundEmailHandler) -> InboundEmailHandler:
            self.handlers.append((address, func))
            return func

        return decorator

    async def handle_webhook(self, request: Request):
        if not settings.has_mailgun:
            logger.error("Mailgun is not configured but received an inbound email webhook")
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE)

        form_data = await request.form()
        timestamp = form_data.get("timestamp", "")
        token = form_data.get("token", "")
        signature = form_data.get("signature", "")

        if not timestamp or not token or not signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing signature components",
            )

        signing_key = settings.mailgun_webhook_signing_key.get_secret_value()
        expected_signature = hmac.new(
            key=signing_key.encode(),
            msg=f"{timestamp}{token}".encode(),
            digestmod="sha256",
        ).hexdigest()

        if not hmac.compare_digest(str(signature), expected_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature",
            )

        data = self._form_data_without_upload_files(form_data)
        email = MailgunInboundEmail.from_form_data(data)

        await self._process_email(email)
        return {"status": "success"}

    def _form_data_without_upload_files(self, form_data: FormData) -> dict[str, Any]:
        return {key: value for key, value in form_data.items() if not isinstance(value, UploadFile)}

    async def _process_email(self, email: InboundEmail) -> None:
        for resolve_address, handler in self.handlers:
            # An unset address means the route isn't configured, so skip it rather than
            # comparing against the empty string.
            if not (address := resolve_address()):
                continue

            # Compared as whole addresses, not matched as substrings: an operator-supplied
            # route must not also collect mail addressed to `also-research@…`.
            if address.lower() in {recipient.lower() for recipient in email.all_recipient_emails}:
                await handler(email)
                return

        logger.warning(f"No handler found for recipients: {email.all_recipients}")


@dataclass
class MailgunInboundEmail(InboundEmail):
    attachment_count: int = 0
    content_id_map: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_form_data(cls, data: dict[str, Any]) -> "MailgunInboundEmail":
        headers: dict[str, str] = {}
        raw_headers = data.get("message-headers", "[]")
        if raw_headers:
            parsed = json.loads(raw_headers)
            for item in parsed:
                if isinstance(item, list) and len(item) >= 2:
                    headers[item[0]] = item[1]

        def split_recipients(value: str) -> list[str]:
            if not value:
                return []
            return [r.strip() for r in value.split(",") if r.strip()]

        content_id_map: dict[str, str] = {}
        raw_content_id_map = data.get("content-id-map", "{}")
        if raw_content_id_map:
            content_id_map = json.loads(raw_content_id_map)

        return cls(
            sender=data.get("from", ""),
            to=split_recipients(data.get("To", "")),
            cc=split_recipients(data.get("Cc", "")),
            bcc=split_recipients(data.get("Bcc", "")),
            subject=data.get("subject", ""),
            body_plain=data.get("body-plain", ""),
            body_html=data.get("body-html", ""),
            stripped_text=data.get("stripped-text", ""),
            stripped_html=data.get("stripped-html", ""),
            message_headers=headers,
            message_id=data.get("Message-Id", ""),
            in_reply_to=data.get("In-Reply-To", ""),
            references=data.get("References", ""),
            timestamp=data.get("timestamp", ""),
            attachment_count=int(data.get("attachment-count", 0)),
            content_id_map=content_id_map,
            raw=data,
        )

    async def get_attachments(self) -> list[InboundEmailAttachment]:
        attachments: list[InboundEmailAttachment] = []
        for stream in await self.get_attachment_streams():
            data = await stream.response.aread()
            attachments.append(
                InboundEmailAttachment(
                    filename=stream.filename,
                    content_type=stream.content_type,
                    data=data,
                )
            )
        return attachments

    async def get_attachment_streams(self) -> list[InboundEmailAttachmentStream]:
        if self.attachment_count == 0:
            return []

        if not settings.has_mailgun:
            return []

        streams: list[InboundEmailAttachmentStream] = []
        for i in range(1, self.attachment_count + 1):
            url = self.raw.get(f"attachment-{i}")
            if not url:
                continue

            client = httpx.AsyncClient()
            auth = ("api", settings.mailgun_api_key.get_secret_value())
            response = await client.get(url, auth=auth)
            response.raise_for_status()

            content_disposition = response.headers.get("content-disposition", "")
            filename = f"attachment-{i}"
            if "filename=" in content_disposition:
                filename = content_disposition.split("filename=")[-1].strip('"')

            streams.append(
                InboundEmailAttachmentStream(
                    filename=filename,
                    content_type=response.headers.get("content-type", "application/octet-stream"),
                    response=response,
                )
            )

        return streams
