import asyncio
import base64
import html
import io
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import message_from_string
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast

import httplib2
import httpx
from fastapi import status
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp  # type: ignore
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from tortoise import BaseDBAsyncClient

from app.models.accounts import User
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailAttachment, EmailMessage, EmailThread, NewMessageResult
from config import logger, settings
from config.enums import EmailLabel, EmailMessageType
from config.settings import GmailAPIClient as GmailAPIClientEnum
from infra.db import transaction
from infra.email import EmailHeaders
from infra.storage import store_file
from integrations.google.constants import GMAIL_TO_EMAIL_LABEL
from integrations.google.enums import GmailLabel
from integrations.google.models import GmailAccount
from integrations.google.oauth import get_gmail_credentials
from integrations.google.types import (
    GmailAttachment,
    GmailHistoryListResponse,
    GmailMessage,
    GmailMessagePart,
    GmailProfile,
    GmailThread,
    GmailThreadListResponse,
    GmailWatchResponse,
    PeopleConnectionsListResponse,
    PeopleOtherContactsListResponse,
    gmail_headers_to_email_headers,
)


def parse_date(date_str: str | None) -> datetime:
    if not date_str:
        return datetime.now(UTC)

    try:
        parsed_date = parsedate_to_datetime(date_str)
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=UTC)
        return parsed_date
    except Exception:
        return datetime.now(UTC)


class GmailMessageExtractor:
    def extract_email_body(self, payload: GmailMessagePart) -> tuple[str | None, str | None]:
        body_plain = None
        body_html = None

        def extract_parts(part: dict[str, Any]):
            nonlocal body_plain, body_html

            if part.get("parts"):
                for subpart in part["parts"]:
                    extract_parts(subpart)
            else:
                mime_type = part.get("mimeType", "")
                body = part.get("body", {})
                data = body.get("data")
                if data:
                    content = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                    if mime_type == "text/plain" and not body_plain:
                        body_plain = content
                    elif mime_type == "text/html" and not body_html:
                        body_html = content

        extract_parts(cast(dict[str, Any], payload))
        return body_plain, body_html

    def find_attachments(self, payload: GmailMessagePart) -> list[GmailMessagePart]:
        attachments: list[GmailMessagePart] = []

        def find_attachments_recursive(part: dict[str, Any]):
            if part.get("parts"):
                for subpart in part["parts"]:
                    find_attachments_recursive(subpart)
            elif part.get("body", {}).get("attachmentId"):
                attachments.append(cast(GmailMessagePart, part))

        find_attachments_recursive(cast(dict[str, Any], payload))
        return attachments


class GmailMessageLoader:
    def __init__(self, gmail_account: GmailAccount):
        self.gmail_account = gmail_account

    def _safe_parse_sender(self, sender: str) -> str:
        """Safely parse sender address, handling cases where it exceeds length limits or has malformations.

        Attempts multiple strategies to extract usable sender information:
        1. Parse the full sender string
        2. Attempt to repair common email malformations (pipe instead of @, URL paths)
        3. Extract and parse just the email address from angle brackets
        4. Truncate and parse
        5. Fallback to a default unknown sender (preserving display name if possible)
        """
        parsed = EmailAddress.parse_safe(sender)
        if parsed:
            return parsed.display_name

        display_name = None
        email_part = sender
        name_match = re.match(r"^(.+?)\s*<(.+)>$", sender)
        if name_match:
            display_name = name_match.group(1).strip().strip('"')
            email_part = name_match.group(2)

        repaired_email = self._attempt_email_repair(email_part)
        if repaired_email:
            parsed = EmailAddress.parse_safe(repaired_email)
            if parsed:
                logger.info(f"Successfully repaired sender email: '{email_part[:50]}...' -> '{repaired_email}'")
                if display_name:
                    return f"{display_name} <{parsed.email}>"
                return parsed.display_name

        # Try extracting just the email from angle brackets as a fallback
        email_match = re.search(r"<([^>]+)>", sender)
        if email_match:
            email_only = email_match.group(1)
            parsed = EmailAddress.parse_safe(email_only)
            if parsed:
                return parsed.display_name

        if display_name and len(display_name) < 200:
            logger.warning(f"Could not parse sender, using fallback with display name: '{display_name}'")
            return f"{display_name} <unknown@example.com>"

        logger.warning(f"Could not parse sender address: '{sender[:100]}...', using fallback")
        return "Unknown <unknown@example.com>"

    def _attempt_email_repair(self, email: str) -> str | None:
        if not email:
            return None

        if "|" in email:
            email = email.replace("|", "@", 1)

        if "@" in email:
            email_match = re.match(r"^([^@]+@[^/\s]+)", email)
            if email_match:
                email = email_match.group(1)

        if "?" in email:
            email = email.split("?")[0]

        if "@" in email and "." in email.split("@")[-1]:
            return email

        return None

    def determine_message_type(self, filtered_labels: list[EmailLabel]) -> EmailMessageType:
        if EmailLabel.DRAFT in filtered_labels:
            return EmailMessageType.DRAFT
        elif EmailLabel.SENT in filtered_labels:
            return EmailMessageType.SENT
        else:
            return EmailMessageType.RECEIVED

    async def create_email_record(
        self,
        message_data: GmailMessage,
        headers: EmailHeaders,
        body_plain: str | None,
        body_html: str | None,
    ) -> NewMessageResult:
        subject = html.unescape(headers.get_one("subject", "") or "")
        sender = headers.get_one("from") or ""
        preview = html.unescape(
            message_data.get("snippet", body_plain[:200] if body_plain else body_html[:200] if body_html else "")
        )
        received_at = parse_date(headers.get_one("date"))
        gmail_labels = message_data.get("labelIds", [])

        filtered_labels = [
            GMAIL_TO_EMAIL_LABEL[GmailLabel(gmail_label)]
            for gmail_label in gmail_labels
            if gmail_label in [label.value for label in GMAIL_TO_EMAIL_LABEL.keys()]
            and gmail_label != GmailLabel.TRASH.value
        ]
        filtered_labels = EmailMessage.normalize_labels(filtered_labels)

        new_message_result = await EmailThread.receive_new_message(
            {
                "user_id": self.gmail_account.user.id,
                "organization_id": self.gmail_account.user.organization_id,
                "external_message_id": message_data["id"],
                "external_thread_id": message_data["threadId"],
                "external_history_id": message_data["historyId"],
                "message_id": headers.message_id or "",
                "message_type": self.determine_message_type(filtered_labels),
                "subject": subject,
                "sender": self._safe_parse_sender(sender),
                "to": EmailAddress.parse_list_addresses_safe(headers.get_one("to") or ""),
                "cc": EmailAddress.parse_list_addresses_safe(headers.get_one("cc") or ""),
                "bcc": EmailAddress.parse_list_addresses_safe(headers.get_one("bcc") or ""),
                "body_plain": body_plain or "",
                "body_html": body_html,
                "preview": preview,
                "received_at": datetime.fromtimestamp(int(message_data.get("internalDate", 0)) / 1000, tz=UTC),
                "sent_at": received_at,
                "labels": filtered_labels,
                "raw_data": message_data,
                "headers_list": message_data.get("payload", {}).get("headers", []),
                "has_jsonb_migrated": True,
                "deleted_at": datetime.now(UTC) if GmailLabel.TRASH in gmail_labels else None,
            }
        )

        return new_message_result

    async def create_onboarding_sync_email_records_batch(
        self,
        messages_data: list[tuple[GmailMessage, EmailHeaders, str | None, str | None]],
        using_db: BaseDBAsyncClient | None = None,
    ) -> None:
        """Create multiple email records in a single batch operation"""
        if not messages_data:
            return None

        async with transaction(using_db) as connection:
            # First, get or create all unique threads
            thread_map = {}
            for message_data, headers, body_plain, body_html in messages_data:
                external_thread_id = message_data["threadId"]
                if external_thread_id not in thread_map:
                    thread, _ = await EmailThread.get_or_create_for_message(
                        {
                            "user_id": self.gmail_account.user.id,
                            "organization_id": self.gmail_account.user.organization_id,
                            "external_thread_id": external_thread_id,
                        },
                        using_db=connection,
                    )
                    thread_map[external_thread_id] = thread

            # Prepare batch data for bulk creation
            messages_to_create = []
            for message_data, headers, body_plain, body_html in messages_data:
                subject = html.unescape(headers.get_one("subject", "") or "")
                sender = headers.get_one("from") or ""
                preview = html.unescape(
                    message_data.get(
                        "snippet", body_plain[:200] if body_plain else body_html[:200] if body_html else ""
                    )
                )
                received_at = parse_date(headers.get_one("date"))
                gmail_labels = message_data.get("labelIds", [])
                filtered_labels = [
                    GMAIL_TO_EMAIL_LABEL[GmailLabel(gmail_label)]
                    for gmail_label in gmail_labels
                    if gmail_label in [label.value for label in GMAIL_TO_EMAIL_LABEL.keys()]
                    and gmail_label != GmailLabel.TRASH.value
                ]
                filtered_labels = EmailMessage.normalize_labels(filtered_labels)

                file_ref = await EmailMessage.store_raw_data_file(dict(message_data))

                thread = thread_map[message_data["threadId"]]
                message_create_data = {
                    "user_id": self.gmail_account.user.id,
                    "organization_id": self.gmail_account.user.organization_id,
                    "external_message_id": message_data["id"],
                    "external_thread_id": message_data["threadId"],
                    "external_history_id": message_data["historyId"],
                    "message_id": headers.message_id or "",
                    "message_type": self.determine_message_type(filtered_labels),
                    "subject": subject,
                    "sender": self._safe_parse_sender(sender),
                    "to": EmailAddress.parse_list_addresses_safe(headers.get_one("to") or ""),
                    "cc": EmailAddress.parse_list_addresses_safe(headers.get_one("cc") or ""),
                    "bcc": EmailAddress.parse_list_addresses_safe(headers.get_one("bcc") or ""),
                    "body_plain": body_plain or "",
                    "body_html": body_html,
                    "preview": preview,
                    "received_at": datetime.fromtimestamp(int(message_data.get("internalDate", 0)) / 1000, tz=UTC),
                    "sent_at": received_at,
                    "labels": filtered_labels,
                    "raw_data": message_data,
                    "raw_data_file_id": file_ref.id,
                    "headers_list": message_data.get("payload", {}).get("headers", []),
                    "has_jsonb_migrated": True,
                    "deleted_at": datetime.now(UTC) if GmailLabel.TRASH in gmail_labels else None,
                    "thread_id": thread.id,
                }
                messages_to_create.append(message_create_data)

            # Bulk create all messages
            if messages_to_create:
                await EmailMessage.bulk_create(
                    [EmailMessage(**data) for data in messages_to_create], ignore_conflicts=True, using_db=connection
                )

    async def process_attachments(
        self,
        gmail: "GoogleAPIClientBase",
        email_message: EmailMessage,
        attachments_data: list[GmailMessagePart],
    ) -> None:
        for attachment_data in attachments_data:
            logger.info(f"Found attachment for email {email_message.id}")
            try:
                await self._process_single_attachment(gmail, email_message, attachment_data)
            except Exception:
                logger.exception(f"Failed to process attachment for email {email_message.id}")

    async def _process_single_attachment(
        self,
        gmail: "GoogleAPIClientBase",
        message: EmailMessage,
        attachment_data: GmailMessagePart,
    ):
        attachment_id = attachment_data["body"]["attachmentId"]
        filename = attachment_data.get("filename", "attachment")
        content_type = attachment_data.get("mimeType", "application/octet-stream")
        headers = gmail_headers_to_email_headers(attachment_data.get("headers", []))
        content_disposition = headers.get_one("Content-Disposition") or ""
        content_id = headers.get_one("Content-ID") or ""

        existing_attachment = await EmailAttachment.get_or_none(
            email_message_id=message.id, external_attachment_id=attachment_id
        )
        if existing_attachment:
            return

        try:
            attachment = await gmail.fetch_attachment(message.external_message_id or "", attachment_id)
            attachment_content = attachment.get("data", "")
            if isinstance(attachment_content, str):
                file_content = base64.urlsafe_b64decode(attachment_content)
            else:
                raise ValueError(f"Invalid attachment data type: {type(attachment_content)}")
            file = await store_file(content=io.BytesIO(file_content), filename=filename, content_type=content_type)

            # Clean content_id by removing surrounding angle brackets if present
            clean_content_id = None
            if content_id:
                clean_content_id = content_id.strip("<>")

            # Check if the attachment is referenced in the HTML body
            is_referenced_in_html = False
            if clean_content_id and message.body_html:
                is_referenced_in_html = f"cid:{clean_content_id}" in message.body_html

            await EmailAttachment.create(
                email_message_id=message.id,
                external_attachment_id=attachment_id,
                is_inline=content_disposition.startswith("inline"),
                is_referenced_in_html=is_referenced_in_html,
                content_id=clean_content_id,
                file=file,
                thread_id=message.thread_id,
            )

        except HttpError as error:
            if error.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND):
                logger.warning(f"Failed to download attachment {attachment_id}: {error}")
            else:
                raise


def _is_gmail_unavailable(error: HttpError) -> bool:
    if error.status_code != status.HTTP_400_BAD_REQUEST:
        return False
    details: list[Any] = error.error_details if isinstance(error.error_details, list) else []
    return any(isinstance(detail, dict) and detail.get("reason") == "failedPrecondition" for detail in details)


def build_people_client(credentials: Credentials, timeout_seconds: int = 60):
    http = httplib2.Http(timeout=timeout_seconds)
    authed_http = AuthorizedHttp(credentials, http=http)
    return build("people", "v1", http=authed_http, cache_discovery=False)


class GoogleAPIClientBase(ABC):
    @classmethod
    @abstractmethod
    async def create(
        cls, user: User, gmail_account: GmailAccount | None, request_timeout_seconds: int = 60
    ) -> "GoogleAPIClientBase":
        raise NotImplementedError

    # User profile methods

    @abstractmethod
    async def fetch_profile(self) -> GmailProfile | None:
        raise NotImplementedError

    @abstractmethod
    async def setup_watch(self) -> GmailWatchResponse | None:
        raise NotImplementedError

    @abstractmethod
    async def stop_watch(self) -> None:
        raise NotImplementedError

    # Thread methods

    @abstractmethod
    async def fetch_thread_data(self, external_thread_id: str, format: str = "full") -> GmailThread | None:
        raise NotImplementedError

    @abstractmethod
    async def list_threads(
        self,
        query: str | None = None,
        label_ids: list[str] | None = None,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> GmailThreadListResponse | None:
        raise NotImplementedError

    @abstractmethod
    async def modify_thread(self, external_thread_id: str, body: dict) -> GmailThread | None:
        raise NotImplementedError

    # Message methods

    @abstractmethod
    async def fetch_message(self, external_message_id: str, format: str = "full") -> GmailMessage | None:
        raise NotImplementedError

    @abstractmethod
    async def find_thread_id_for_rfc822_message_id(self, rfc822_message_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def send_message(
        self,
        body: dict,
    ) -> GmailMessage | None:
        raise NotImplementedError

    @abstractmethod
    async def fetch_attachment(self, external_message_id: str, attachment_id: str) -> GmailAttachment:
        raise NotImplementedError

    # History methods

    @abstractmethod
    async def list_history(
        self,
        max_results: int = 100,
        start_history_id: int | None = None,
        history_types: list[str] | None = None,
        page_token: str | None = None,
    ) -> GmailHistoryListResponse | None:
        raise NotImplementedError

    # People API methods

    @abstractmethod
    async def list_other_contacts(
        self,
        page_size: int = 100,
        read_mask: str = "names,emailAddresses,photos",
        page_token: str | None = None,
        sync_token: str | None = None,
        request_sync_token: bool = False,
    ) -> PeopleOtherContactsListResponse | None:
        raise NotImplementedError

    @abstractmethod
    async def list_connections(
        self,
        page_size: int = 100,
        person_fields: str = "names,emailAddresses,photos",
        page_token: str | None = None,
        sync_token: str | None = None,
        request_sync_token: bool = False,
    ) -> PeopleConnectionsListResponse | None:
        raise NotImplementedError


@dataclass
class GoogleAPIClient(GoogleAPIClientBase):
    gmail_account: GmailAccount | None
    gmail: Any
    people_service: Any | None = None
    # Serializes .execute() calls. googleapiclient Resource objects, httplib2.Http, and the
    # shared Credentials are not thread-safe, but callers (e.g. onboarding/backfill) fan out
    # fetches via asyncio.gather on a single client, so we need a per-client mutex around
    # every asyncio.to_thread hop.
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @classmethod
    async def create(cls, user: User, gmail_account: GmailAccount | None, request_timeout_seconds: int = 60):
        credentials = await get_gmail_credentials(user)
        gmail_client = await asyncio.to_thread(cls._build_gmail_client, credentials, request_timeout_seconds)
        people_service = await asyncio.to_thread(build_people_client, credentials, request_timeout_seconds)
        return cls(gmail_account, gmail=gmail_client, people_service=people_service)

    @staticmethod
    def _build_gmail_client(credentials: Credentials, timeout_seconds: int = 60):
        http = httplib2.Http(timeout=timeout_seconds)
        authed_http = AuthorizedHttp(credentials, http=http)
        return build("gmail", "v1", http=authed_http, cache_discovery=False)

    async def _execute[T](self, fn: Callable[[], T]) -> T:
        async with self._lock:
            return await asyncio.to_thread(fn)

    async def fetch_profile(self) -> GmailProfile | None:
        try:
            return await self._execute(lambda: self.gmail.users().getProfile(userId="me").execute())
        except HttpError as error:
            # Google returns 400 failedPrecondition when the account has no Gmail
            # (e.g., Workspace account without a Gmail license, or a deleted mailbox).
            if _is_gmail_unavailable(error):
                return None
            raise

    async def setup_watch(self) -> GmailWatchResponse | None:
        if not self.gmail_account:
            raise ValueError("Gmail account is required for setup_watch")

        watch_request: dict[str, Any] = {
            "topicName": f"projects/{settings.gcp_project}/topics/gmail-notifications",
        }

        if not self.gmail:
            raise ValueError("Gmail client not initialized")
        result = await self._execute(lambda: self.gmail.users().watch(userId="me", body=watch_request).execute())
        # Only seed the resume cursor on the first watch. On renewal, history_id is the live cursor
        # that must keep trailing the mailbox historyId — overwriting it with the watch response's
        # current historyId would skip every record between the cursor and now (including the backlog
        # when a self-heal re-watch fires for an account that's already behind).
        if self.gmail_account.history_id in (None, "", "0"):
            self.gmail_account.history_id = str(result.get("historyId", "0"))
        self.gmail_account.watch_expires_at = datetime.fromtimestamp(int(result.get("expiration", 0)) / 1000, UTC)
        # Scope the write to the fields we set here. A bare save() would write back the whole
        # in-memory snapshot and could clobber a concurrent mark_synced() that advanced the cursor
        # mid-renewal, regressing history_id/synced_history_id.
        await self.gmail_account.save(update_fields=["history_id", "watch_expires_at"])

        if self.gmail_account:
            logger.info(f"Gmail watch set up for gmail_account {self.gmail_account.id}")
        return result

    async def stop_watch(self) -> None:
        # Note that the API for stopping watches will stop all watches for the user,
        # it doesn't accept a body or parameters to stop a specific watch.
        # If we add support for multiple watches in the future, we would need to take care when
        # stopping them to ensure we only stop the intended watch.
        await self._execute(lambda: self.gmail.users().stop(userId="me").execute())
        if self.gmail_account:
            logger.info(f"Gmail watch stopped for gmail account {self.gmail_account.id}")

    async def fetch_thread_data(self, external_thread_id: str, format: str = "full") -> GmailThread | None:
        try:
            return await self._execute(
                lambda: self.gmail.users().threads().get(userId="me", id=external_thread_id, format=format).execute()
            )
        except HttpError as error:
            if error.status_code in (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND):
                logger.warning(f"Failed to get Gmail thread {external_thread_id}: {error}")
                return None
            else:
                raise

    async def list_threads(
        self,
        query: str | None = None,
        label_ids: list[str] | None = None,
        page_token: str | None = None,
        max_results: int = 100,
        include_spam_trash: bool = False,
    ) -> GmailThreadListResponse | None:
        params = {"userId": "me", "maxResults": max_results, "includeSpamTrash": include_spam_trash, "q": query}
        if label_ids:
            params["labelIds"] = label_ids
        if page_token:
            params["pageToken"] = page_token

        return await self._execute(lambda: self.gmail.users().threads().list(**params).execute())

    async def modify_thread(self, external_thread_id: str, body: dict) -> GmailThread | None:
        try:
            return await self._execute(
                lambda: self.gmail.users().threads().modify(userId="me", id=external_thread_id, body=body).execute()
            )
        except HttpError as error:
            # A 404 means the thread is gone from Gmail (deleted/expunged) while it still exists
            # locally; retrying can never succeed, so treat it as a no-op. Other statuses (403,
            # 429, 5xx) stay unhandled so genuinely transient failures keep retrying.
            if error.status_code == status.HTTP_404_NOT_FOUND:
                logger.warning(f"Failed to modify Gmail thread {external_thread_id}: {error}")
                return None
            raise

    async def fetch_message(self, external_message_id: str, format: str = "full") -> GmailMessage | None:
        try:
            return await self._execute(
                lambda: self.gmail.users().messages().get(userId="me", id=external_message_id, format=format).execute()
            )
        except HttpError as error:
            if error.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND):
                logger.warning(f"Failed to fetch Gmail message {external_message_id}: {error}")
                return None
            else:
                raise

    async def find_thread_id_for_rfc822_message_id(self, rfc822_message_id: str) -> str | None:
        try:
            response = (
                self.gmail.users()
                .messages()
                .list(userId="me", q=f"rfc822msgid:{rfc822_message_id}", maxResults=1)
                .execute()
            )
        except HttpError as error:
            if error.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND):
                return None
            raise
        messages = response.get("messages", [])
        if not messages:
            return None
        return messages[0].get("threadId")

    async def send_message(
        self,
        body: dict,
    ) -> GmailMessage | None:
        return await self._execute(lambda: self.gmail.users().messages().send(userId="me", body=body).execute())

    async def fetch_attachment(self, external_message_id: str, attachment_id: str) -> GmailAttachment:
        return await self._execute(
            lambda: (
                self.gmail.users()
                .messages()
                .attachments()
                .get(userId="me", messageId=external_message_id, id=attachment_id)
                .execute()
            )
        )

    async def list_history(
        self,
        max_results: int = 100,
        start_history_id: int | None = None,
        history_types: list[str] | None = None,
        page_token: str | None = None,
    ) -> GmailHistoryListResponse | None:
        params = {"userId": "me", "maxResults": max_results}
        if start_history_id:
            params["startHistoryId"] = start_history_id
        if history_types:
            params["historyTypes"] = history_types
        if page_token:
            params["pageToken"] = page_token

        return await self._execute(lambda: self.gmail.users().history().list(**params).execute())

    async def list_other_contacts(
        self,
        page_size: int = 100,
        read_mask: str = "names,emailAddresses,photos",
        page_token: str | None = None,
        sync_token: str | None = None,
        request_sync_token: bool = False,
    ) -> PeopleOtherContactsListResponse | None:
        params = {
            "pageSize": page_size,
            "readMask": read_mask,
        }
        if page_token:
            params["pageToken"] = page_token
        if sync_token:
            params["syncToken"] = sync_token
        if request_sync_token:
            params["requestSyncToken"] = request_sync_token

        return await self._execute(
            lambda: self.people_service.otherContacts().list(**params).execute()  # type: ignore[union-attr]
        )

    async def list_connections(
        self,
        page_size: int = 100,
        person_fields: str = "names,emailAddresses,photos",
        page_token: str | None = None,
        sync_token: str | None = None,
        request_sync_token: bool = False,
    ) -> PeopleConnectionsListResponse | None:
        params = {
            "pageSize": page_size,
            "personFields": person_fields,
        }
        if page_token:
            params["pageToken"] = page_token
        if sync_token:
            params["syncToken"] = sync_token
        if request_sync_token:
            params["requestSyncToken"] = request_sync_token

        return await self._execute(
            lambda: (
                self.people_service.people()  # type: ignore[union-attr]
                .connections()
                .list(resourceName="people/me", **params)
                .execute()
            )
        )


@dataclass
class GmailAPICall:
    """Record of an API call made during testing"""

    method: str
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)


@dataclass
class MockResponse:
    """Mock HTTP response for HttpError simulation"""

    status: int


def track_api_call(method_name: str):
    """Decorator for MockGmailAPIClient async methods to handle call tracking and error simulation"""

    def decorator(func):
        async def wrapper(self, *args, **kwargs):
            self.track_call(method_name, *args, **kwargs)

            if method_name in self.should_raise_errors:
                raise self.should_raise_errors[method_name]

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator


class MockGmailAPIStateRegistry:
    _current_state: "MockGmailAPIState | None" = None

    @classmethod
    def get_state(cls) -> "MockGmailAPIState":
        if cls._current_state is None:
            cls._current_state = MockGmailAPIState()
        return cls._current_state

    @classmethod
    def clear_state(cls) -> None:
        """Clear state for test isolation"""
        cls._current_state = None


class MockGmailAPIState:
    def __init__(self):
        self.profiles: dict[str, dict] = {}
        self.watches: dict[str, dict] = {}
        self.history: dict[str, list[dict[str, Any]]] = {}
        self.messages: dict[str, dict[str, Any]] = {}
        self.threads: dict[str, dict[str, Any]] = {}
        self.history_counters: dict[str, int] = {}  # Track next history ID per account
        self.attachments: dict[str, dict] = {}  # Store attachment data for fetch_attachment
        self.expired_history: set[str] = set()  # Emails whose next list_history should 404 (expired history)

    def set_profile(self, gmail_account: GmailAccount) -> None:
        self.profiles[gmail_account.email] = {
            "emailAddress": gmail_account.email,
            "historyId": gmail_account.history_id or "0",
            "messagesTotal": 0,
            "threadsTotal": 0,
        }
        self.history_counters[gmail_account.email] = int(gmail_account.history_id) or 0

    def create_profile_by_email(self, email: str) -> None:
        """Create a profile for a Gmail account by email address only"""
        self.profiles[email] = {
            "emailAddress": email,
            "historyId": "0",
            "messagesTotal": 0,
            "threadsTotal": 0,
        }
        self.history_counters[email] = 0

    def add_history_event(self, email: str, event_type: str, message_id: str, labels: list[str] | None = None) -> str:
        """
        Add a history event for a Gmail account and return the new history ID.
        This should not be called directly by tests, instead use the higher-level methods like add_message.
        """
        if email not in self.history_counters:
            self.history_counters[email] = 0

        self.history_counters[email] += 1
        history_id = str(self.history_counters[email])

        event: dict[str, Any] = {"id": history_id, "historyId": history_id}

        match event_type:
            case "messageAdded":
                event["messagesAdded"] = [{"message": {"id": message_id}}]
            case "labelsAdded":
                event["labelsAdded"] = [{"message": {"id": message_id}, "labelIds": labels or []}]
            case "labelsRemoved":
                event["labelsRemoved"] = [{"message": {"id": message_id}, "labelIds": labels or []}]
            case "messageDeleted":
                event["messagesDeleted"] = [{"message": {"id": message_id}}]

        if email not in self.history:
            self.history[email] = []

        self.history[email].append(event)
        return history_id

    def get_pending_history_for_account(self, email: str, last_history_id: str) -> list[dict[str, Any]]:
        """Get history events newer than the account's current history_id"""
        all_history = self.history.get(email, [])

        # Return only events with history_id > current checkpoint
        return [event for event in all_history if int(event.get("historyId", "0")) > int(last_history_id)]

    def get_last_pending_history_id_for_account(self, email: str, last_history_id: str) -> str:
        pending_events = self.get_pending_history_for_account(email, last_history_id)
        if not pending_events:
            raise ValueError("No pending history events for this Gmail account")

        return pending_events[-1]["historyId"]

    async def trigger_gmail_webhooks(self, http_client: httpx.AsyncClient) -> None:
        """Trigger processing of all pending Gmail webhook events.

        This simulates Gmail webhooks by processing all pending history events
        by making POST requests to the webhook endpoint.
        """

        for email in self.profiles.keys():
            # Check if there are any pending history events for this account
            pending_events = self.get_pending_history_for_account(email, "0")
            if not pending_events:
                continue  # Skip accounts with no pending history

            # Get the last history ID - we don't care what has been processed so far.
            latest_history_id = pending_events[-1]["historyId"]

            # Get email address from profiles
            profile = self.profiles.get(email)
            if not profile:
                continue

            # Simulate the webhook POST request
            webhook_payload = {
                "message": {
                    "data": base64.b64encode(
                        json.dumps(
                            {"emailAddress": profile["emailAddress"], "historyId": int(latest_history_id)}
                        ).encode()
                    ).decode(),
                    "messageId": f"mock-message-{email}-{latest_history_id}",
                    "publishTime": datetime.now(UTC).isoformat(),
                }
            }

            # Make POST request to the webhook endpoint
            response = await http_client.post("/integrations/gmail/webhook", json=webhook_payload)

            if response.status_code != status.HTTP_200_OK:
                logger.warning(f"Gmail webhook simulation failed with status {response.status_code}: {response.text}")

            # Update the profile's historyId to mark these events as processed
            profile["historyId"] = latest_history_id

    #
    # Builder Methods for Test Setup
    #
    #

    def add_raw_message(self, message: dict[str, Any], email: str) -> dict[str, Any]:
        """
        Store a Gmail API message exactly as-is, without modification.
        Use this when you have a complete Gmail API message structure (e.g., from API export).
        This is the low-level storage method - prefer add_message() for simple test setup.
        """
        self._store_message_in_thread(message)
        self.add_history_event(email, "messageAdded", message["id"], message.get("labelIds", []))
        return message

    def _store_message_in_thread(self, message: dict[str, Any]) -> None:
        """Insert a message into self.messages and create or append its thread. Does not touch history."""
        self.messages[message["id"]] = message

        thread_id = message["threadId"]
        if thread_id not in self.threads:
            self.threads[thread_id] = {
                "id": thread_id,
                "historyId": message.get("historyId", "0"),
                "messages": [message],
            }
        else:
            self.threads[thread_id]["messages"].append(message)

    def _build_simple_payload(
        self, headers_list: list[dict[str, str]], body_plain: str, body_html: str | None
    ) -> dict[str, Any]:
        """Build a simple Gmail API payload structure for basic text messages."""
        payload: dict[str, Any] = {
            "headers": headers_list,
            "mimeType": "multipart/alternative" if body_html else "text/plain",
        }

        if body_html:
            payload["parts"] = [
                {"mimeType": "text/plain", "body": {"data": self._base64_encode(body_plain)}},
                {"mimeType": "text/html", "body": {"data": self._base64_encode(body_html)}},
            ]
        else:
            payload["body"] = {"data": self._base64_encode(body_plain)}

        return payload

    def _build_message(
        self,
        message_id: str,
        thread_id: str,
        history_id: str,
        labels: list[str] | None,
        headers: dict[str, str] | None,
        body_plain: str,
        body_html: str | None = None,
    ) -> dict[str, Any]:
        """Build a simple Gmail API message dict (default headers + text/html payload) for test setup."""
        default_headers = {
            "Subject": "Test Subject",
            "From": "test@example.com",
            "To": "recipient@example.com",
            "Date": "Wed, 25 Dec 2024 10:15:30 +0000",
            "Message-Id": f"<{message_id}@example.com>",
        }
        default_headers.update(headers or {})
        headers_list = [{"name": k, "value": v} for k, v in default_headers.items()]

        return {
            "id": message_id,
            "threadId": thread_id,
            "historyId": history_id,
            "labelIds": labels or ["INBOX"],
            "snippet": body_plain[:50],
            "payload": self._build_simple_payload(headers_list, body_plain, body_html),
            "internalDate": "1640995200000",
        }

    def add_message(
        self,
        message_id: str,
        thread_id: str,
        email: str,
        labels: list[str] | None = None,
        headers: dict[str, str] | None = None,
        body_plain: str = "Test message",
        body_html: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a simple Gmail API message with text content for easy test setup.
        For complex MIME structures or real Gmail API exports, use add_raw_message() instead.
        """
        message = self._build_message(message_id, thread_id, "67890", labels, headers, body_plain, body_html)
        # Store using raw message method to ensure consistency
        return self.add_raw_message(message, email)

    def simulate_history_lag(self, email: str, current_history_id: int) -> None:
        """
        Advance the mailbox's current historyId WITHOUT appending a history record.
        Reproduces Gmail's eventual consistency, where list_history reports a response
        historyId ahead of the records actually present in self.history[email].
        """
        self.history_counters[email] = current_history_id

    def materialize_lagging_message(
        self,
        message_id: str,
        thread_id: str,
        email: str,
        history_id: str,
        labels: list[str] | None = None,
        headers: dict[str, str] | None = None,
        body_plain: str = "Test message",
    ) -> None:
        """
        Store a message and append its messagesAdded history record at an EXPLICIT history_id
        BELOW the current (lagging) counter, without touching the counter. Models a message
        that lagged in after the counter had already moved ahead.

        Deliberately bypasses add_raw_message/add_history_event because both bump and stamp the
        counter, which would destroy the lag invariant.
        """
        message = self._build_message(message_id, thread_id, history_id, labels, headers, body_plain)
        self._store_message_in_thread(message)

        # Append the history record at the explicit (lagging) id without advancing the counter.
        self.history.setdefault(email, []).append(
            {"id": history_id, "historyId": history_id, "messagesAdded": [{"message": {"id": message_id}}]}
        )

    def simulate_history_expired(self, email: str) -> None:
        """Mark the account so its next list_history raises a 404, mirroring Gmail's expired history."""
        self.expired_history.add(email)

    def delete_message(self, email: str, message_id: str) -> None:
        """Delete a message and create a corresponding history event"""
        if message_id in self.messages:
            del self.messages[message_id]
            self.add_history_event(email, "messageDeleted", message_id)

            # Also remove from any threads
            for thread in self.threads.values():
                thread_messages = thread.get("messages", [])
                thread["messages"] = [msg for msg in thread_messages if msg.get("id") != message_id]

    def add_thread(self, thread_id: str, message_ids: list[str] | None = None) -> dict[str, Any]:
        """Add a thread containing the specified messages"""
        message_ids = message_ids or []
        messages = []

        for msg_id in message_ids:
            if msg_id in self.messages:
                messages.append(self.messages[msg_id])

        thread = {
            "id": thread_id,
            "historyId": "67890",
            "messages": messages,
        }

        self.threads[thread_id] = thread
        return thread

    def update_labels(
        self,
        email: str,
        message_id: str,
        labels_to_add: list[str] | None = None,
        labels_to_remove: list[str] | None = None,
    ) -> None:
        """Update message labels and create corresponding history events"""
        if message_id not in self.messages:
            return

        message = self.messages[message_id]
        current_labels = set(message.get("labelIds", []))

        # Apply label changes
        if labels_to_add:
            current_labels.update(labels_to_add)
            self.add_history_event(email, "labelsAdded", message_id, labels_to_add)

        if labels_to_remove:
            current_labels.difference_update(labels_to_remove)
            self.add_history_event(email, "labelsRemoved", message_id, labels_to_remove)

        # Update message labels
        message["labelIds"] = list(current_labels)

        # Also update the message in any threads for consistency
        thread_id = message.get("threadId")
        if thread_id and thread_id in self.threads:
            thread = self.threads[thread_id]
            thread_messages = thread.get("messages", [])
            for thread_message in thread_messages:
                if isinstance(thread_message, dict) and thread_message.get("id") == message_id:
                    thread_message["labelIds"] = list(current_labels)
                    break

    def load_threads_from_directory(self, directory_path: Path, email: str) -> None:
        """
        Load threads and messages from JSON files in a directory for seeding.
        Preserves the complete Gmail API message structure including complex MIME parts.
        """
        for file_path in directory_path.glob("*.json"):
            with file_path.open("r", encoding="utf-8") as f:
                thread_data = json.load(f)
                thread_id = thread_data.get("id")
                if not thread_id:
                    continue
                messages = thread_data.get("messages", [])

                for message in messages:
                    # Use add_raw_message to preserve full message structure
                    # This ensures complex MIME structures (like inline attachments) are maintained
                    self.add_raw_message(message, email)

                    # Extract and store attachment data
                    self._load_attachment_data_from_seeded_message(message)

                # Update thread with complete data
                self.threads[thread_id] = thread_data

    def _load_attachment_data_from_seeded_message(self, message: dict[str, Any]) -> None:
        """Extract attachment data from seed message payloads and store in attachments dict."""
        message_id = message.get("id")
        if not message_id:
            return

        payload = message.get("payload", {})

        def extract_from_part(part: dict[str, Any]) -> None:
            if part.get("parts"):
                for subpart in part["parts"]:
                    extract_from_part(subpart)
            elif part.get("body", {}).get("attachmentId"):
                body = part["body"]
                attachment_id = body["attachmentId"]

                # If the seed has embedded attachment data, store it
                if "data" in body:
                    attachment_key = f"{message_id}:{attachment_id}"
                    self.attachments[attachment_key] = {
                        "data": body["data"],
                        "size": body.get("size", len(body["data"])),
                    }

        extract_from_part(payload)

    #
    # Utilities
    #
    #

    def _base64_encode(self, text: str) -> str:
        """Helper to base64 encode text like Gmail API does"""
        return base64.urlsafe_b64encode(text.encode()).decode()


@dataclass
class MockGoogleAPIClient(GoogleAPIClientBase):
    state: MockGmailAPIState
    gmail_account: GmailAccount | None
    calls_made: list[GmailAPICall] = field(default_factory=list)
    should_raise_errors: dict[str, Exception] = field(default_factory=dict)

    @classmethod
    async def create(cls, user: User, gmail_account: GmailAccount | None, request_timeout_seconds: int = 60):
        state = MockGmailAPIStateRegistry.get_state()
        # Set up profile if not already present
        if gmail_account and gmail_account.email not in state.profiles:
            state.set_profile(gmail_account)
        return cls(state, gmail_account)

    #
    # Call Tracking & Error Management
    #
    #

    def track_call(self, method: str, *args, **kwargs):
        """Track API calls for test assertions"""
        self.calls_made.append(GmailAPICall(method, args, kwargs))

    def should_error(self, method: str, error: Exception):
        """Configure method to raise an error"""
        self.should_raise_errors[method] = error

    def clear_calls(self):
        """Reset call tracking"""
        self.calls_made = []

    #
    # Gmail API
    #
    #

    @track_api_call("fetch_profile")
    async def fetch_profile(self) -> GmailProfile | None:
        if self.gmail_account:
            if self.gmail_account.email in self.state.profiles:
                return cast(GmailProfile, self.state.profiles[self.gmail_account.email])
            raise ValueError("Profile not found for gmail account in mock client state")
        # No gmail_account is the SetupGmailAccountJob path; fall back to any seeded profile.
        if self.state.profiles:
            return cast(GmailProfile, next(iter(self.state.profiles.values())))
        return None

    @track_api_call("setup_watch")
    async def setup_watch(self) -> GmailWatchResponse | None:
        if not self.gmail_account:
            raise ValueError("Gmail account is required for setup_watch in mock client")

        watch_info: GmailWatchResponse = {
            "historyId": self.gmail_account.history_id or "0",
            "expiration": str(int((datetime.now(UTC).timestamp() + 3600) * 1000)),  # 1 hour from now
        }
        self.state.watches[self.gmail_account.email] = watch_info  # type: ignore[assignment]
        return watch_info

    @track_api_call("stop_watch")
    async def stop_watch(self) -> None:
        if self.gmail_account and self.gmail_account.email in self.state.watches:
            del self.state.watches[self.gmail_account.email]

    @track_api_call("fetch_thread_data")
    async def fetch_thread_data(self, external_thread_id: str, format: str = "full") -> GmailThread | None:
        thread = self.state.threads.get(external_thread_id)
        return cast(GmailThread, thread) if thread else None

    @track_api_call("list_threads")
    async def list_threads(
        self,
        query: str | None = None,
        label_ids: list[str] | None = None,
        page_token: str | None = None,
        max_results: int = 100,
    ) -> GmailThreadListResponse | None:
        threads = list(self.state.threads.values())

        # Apply query filtering if query is provided
        if query:
            filtered_threads = []
            for thread in threads:
                # Get all labels from all messages in the thread
                thread_labels = set()
                for message in thread.get("messages", []):
                    thread_labels.update(message.get("labelIds", []))

                # Parse and apply query conditions
                query_parts = query.split()
                matches_query = True

                for part in query_parts:
                    if part.startswith("-in:"):
                        # Negative condition: thread should NOT have this label
                        label = part[4:].upper()
                        if label in thread_labels:
                            matches_query = False
                            break
                    elif part.startswith("in:"):
                        # Positive condition: thread should have this label
                        label = part[3:].upper()
                        if label not in thread_labels:
                            matches_query = False
                            break

                if matches_query:
                    filtered_threads.append(thread)

            threads = filtered_threads

        return cast(GmailThreadListResponse, {"threads": threads[:max_results], "nextPageToken": None})

    @track_api_call("modify_thread")
    async def modify_thread(self, external_thread_id: str, body: dict) -> GmailThread | None:
        if external_thread_id in self.state.threads:
            thread = self.state.threads[external_thread_id]
            # Apply modifications from body
            new_thread = {**thread, **body}
            self.state.threads[external_thread_id] = new_thread
            return cast(GmailThread, new_thread)

        raise ValueError(f"Thread {external_thread_id} not found in mock client state")

    @track_api_call("fetch_message")
    async def fetch_message(self, external_message_id: str, format: str = "full") -> GmailMessage | None:
        message = self.state.messages.get(external_message_id)
        return cast(GmailMessage, message) if message else None

    @track_api_call("find_thread_id_for_rfc822_message_id")
    async def find_thread_id_for_rfc822_message_id(self, rfc822_message_id: str) -> str | None:
        for message in self.state.messages.values():
            payload = message.get("payload") or {}
            for header in payload.get("headers", []) or []:
                if header.get("name", "").lower() == "message-id" and header.get("value") == rfc822_message_id:
                    thread_id = message.get("threadId")
                    return str(thread_id) if thread_id else None
        return None

    async def send_message(
        self,
        body: dict,
    ) -> GmailMessage | None:
        if not self.gmail_account:
            raise ValueError("Gmail account is required for send_message")

        # Generate unique message ID
        message_id = f"sent-{self.gmail_account.email}-{len(self.state.messages) + 1}"

        # Get next history ID for sender
        history_id = self.state.add_history_event(self.gmail_account.email, "messageAdded", message_id)

        # Extract raw message from body to parse headers and body content
        raw_message = body.get("raw", "")
        headers = []
        body_plain = ""
        body_html = None

        if raw_message:
            decoded_message = base64.urlsafe_b64decode(raw_message.encode()).decode()
            # Parse headers and body from the raw message
            email_msg = message_from_string(decoded_message)
            headers = [{"name": k, "value": v} for k, v in email_msg.items()]

            # Extract body content
            if email_msg.is_multipart():
                for part in email_msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain" and not body_plain:
                        payload_data = part.get_payload(decode=True)
                        if isinstance(payload_data, bytes):
                            body_plain = payload_data.decode("utf-8", errors="ignore")
                        elif isinstance(payload_data, str):
                            body_plain = payload_data
                    elif content_type == "text/html" and not body_html:
                        payload_data = part.get_payload(decode=True)
                        if isinstance(payload_data, bytes):
                            body_html = payload_data.decode("utf-8", errors="ignore")
                        elif isinstance(payload_data, str):
                            body_html = payload_data
            else:
                # Single part message
                payload_data = email_msg.get_payload(decode=True)
                if isinstance(payload_data, bytes):
                    body_plain = payload_data.decode("utf-8", errors="ignore")
                elif isinstance(payload_data, str):
                    body_plain = payload_data

        # Ensure each message has a unique Message-ID header
        unique_message_id = f"<{message_id}@mock-gmail.example.com>"
        headers.append({"name": "Message-ID", "value": unique_message_id})

        # Create the sent message
        thread_id = body.get("threadId", f"thread-{message_id}")

        # Create payload structure that GmailMessageExtractor can understand
        payload: dict[str, Any] = {
            "headers": headers,
            "mimeType": "text/plain" if not body_html else "multipart/mixed",
        }

        # Add body content in format that extractor expects
        if body_html:
            # Multipart message
            payload["parts"] = [
                {
                    "mimeType": "text/plain",
                    "body": {"data": base64.urlsafe_b64encode((body_plain or "").encode()).decode()},
                },
                {"mimeType": "text/html", "body": {"data": base64.urlsafe_b64encode(body_html.encode()).decode()}},
            ]
        else:
            # Single part message
            payload["body"] = {"data": base64.urlsafe_b64encode((body_plain or "").encode()).decode()}

        message = {
            "id": message_id,
            "threadId": thread_id,
            "labelIds": ["SENT"],
            "snippet": body_plain[:200] if body_plain else "",
            "historyId": history_id,
            "internalDate": str(int(datetime.now(UTC).timestamp() * 1000)),
            "payload": payload,
        }

        # Store the sent message
        sent_message = cast(GmailMessage, message)
        self.state.messages[message_id] = sent_message  # type: ignore[assignment]

        # Create thread if it doesn't exist
        if thread_id not in self.state.threads:
            self.state.threads[thread_id] = {
                "id": thread_id,
                "historyId": history_id,
                "messages": [message],
            }
        else:
            self.state.threads[thread_id]["messages"].append(message)

        # Find recipients and create received messages
        to_header = next((h["value"] for h in headers if h["name"] == "To"), "")
        if to_header:
            recipients = EmailAddress.parse_list_addresses(to_header)
            for recipient in recipients:
                # Find the recipient's gmail account
                recipient_account = await self._find_gmail_account_by_email(recipient)
                if recipient_account:
                    self._create_received_message(recipient_account, message)

        return sent_message

    async def _find_gmail_account_by_email(self, email: str) -> "GmailAccount | None":
        return await GmailAccount.get_or_none(email=email)

    def _create_received_message(self, recipient_account: GmailAccount, original_message: dict) -> None:
        # Create a received copy of the message
        received_message_id = f"received-{recipient_account.email}-{len(self.state.messages) + 1}"

        # Generate history event for recipient
        history_id = self.state.add_history_event(recipient_account.email, "messageAdded", received_message_id)

        received_message = {
            "id": received_message_id,
            "threadId": original_message["threadId"],
            "labelIds": ["INBOX", "UNREAD"],
            "snippet": original_message["snippet"],
            "historyId": history_id,
            "internalDate": original_message["internalDate"],
            "payload": original_message["payload"].copy(),
        }

        # Store the received message
        self.state.messages[received_message_id] = received_message

        # Update thread for recipient
        thread_id = original_message["threadId"]
        if thread_id not in self.state.threads:
            self.state.threads[thread_id] = {
                "id": thread_id,
                "historyId": history_id,
                "messages": [received_message],
            }
        else:
            self.state.threads[thread_id]["messages"].append(received_message)
            self.state.threads[thread_id]["historyId"] = history_id

    async def fetch_attachment(self, external_message_id: str, attachment_id: str) -> GmailAttachment:
        # Check if we have attachment data stored
        attachment_key = f"{external_message_id}:{attachment_id}"
        if attachment_key in self.state.attachments:
            return cast(GmailAttachment, self.state.attachments[attachment_key])

        # Fallback to default mock attachment
        return cast(
            GmailAttachment,
            {
                "data": base64.urlsafe_b64encode(b"Mock attachment content").decode(),
                "headers": [
                    {"name": "Content-Disposition", "value": 'attachment; filename="mock.txt"'},
                    {"name": "Content-ID", "value": "<mock-content-id>"},
                ],
            },
        )

    async def list_history(
        self,
        max_results: int = 100,
        start_history_id: int | None = None,
        history_types: list[str] | None = None,
        page_token: str | None = None,  # Note history pagination not implemented in mock
    ) -> GmailHistoryListResponse | None:
        if not self.gmail_account:
            return cast(GmailHistoryListResponse, {"history": [], "historyId": "0"})

        if self.gmail_account.email in self.state.expired_history:
            raise HttpError(
                httplib2.Response({"status": "404"}),
                json.dumps({"error": {"code": 404, "message": "Requested entity was not found."}}).encode("utf-8"),
            )

        # Get processed history for this account
        account_history = self.state.history.get(self.gmail_account.email, [])
        # Filter by start_history_id if provided
        if start_history_id is not None:
            account_history = [
                event for event in account_history if int(event.get("historyId", "0")) > start_history_id
            ]

        # Include the current history counter as the response historyId (mirrors real Gmail API)
        current_history_id = str(self.state.history_counters.get(self.gmail_account.email, 0))
        return cast(
            GmailHistoryListResponse, {"history": account_history[:max_results], "historyId": current_history_id}
        )

    async def list_other_contacts(
        self,
        page_size: int = 100,
        read_mask: str = "names,emailAddresses,photos",
        page_token: str | None = None,
        sync_token: str | None = None,
        request_sync_token: bool = False,
    ) -> PeopleOtherContactsListResponse | None:
        return cast(
            PeopleOtherContactsListResponse,
            {
                "otherContacts": [],
                "nextSyncToken": "mock-sync-token",
            },
        )

    async def list_connections(
        self,
        page_size: int = 100,
        person_fields: str = "names,emailAddresses,photos",
        page_token: str | None = None,
        sync_token: str | None = None,
        request_sync_token: bool = False,
    ) -> PeopleConnectionsListResponse | None:
        return cast(
            PeopleConnectionsListResponse,
            {
                "connections": [],
                "nextSyncToken": "mock-sync-token",
            },
        )


async def get_google_api_client(
    user: User, gmail_account: GmailAccount | None, request_timeout_seconds: int = 60
) -> GoogleAPIClientBase:
    if settings.gmail_api_client == GmailAPIClientEnum.MOCK:
        return await MockGoogleAPIClient.create(user, gmail_account, request_timeout_seconds)
    return await GoogleAPIClient.create(user, gmail_account, request_timeout_seconds)
