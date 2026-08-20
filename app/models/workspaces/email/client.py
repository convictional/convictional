from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import formatdate
from uuid import UUID
from uuid import uuid4 as generate_uuid

from tortoise import BaseDBAsyncClient

from app.models.accounts import User
from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.email.address import EmailAddress
from app.models.workspaces.email.thread import EmailThread
from config.enums import EmailLabel, EmailMessageType
from infra.email import EmailClient, EmailHeaders, EmailMessage, _delivery_browser


@dataclass
class FakeEmailClient(EmailClient):
    async def save_draft(
        self, email_thread_id: UUID | None, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        thread = await EmailThread.get_or_none(id=email_thread_id, creator_id=user_id, using_db=using_db)
        if not thread:
            return

        draft = await thread.get_draft()
        if not draft:
            return

        draft.external_thread_id = thread.external_thread_id or f"external-thread-{generate_uuid()}"
        draft.external_message_id = f"external-message-{generate_uuid()}"
        await draft.save(update_fields=draft.changes.keys())

        await thread.update_metadata_from_messages()
        await Mailbox.sync(thread)

    async def send_message(
        self, email_thread_id: UUID | None, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        thread = await EmailThread.get_or_none(id=email_thread_id).prefetch_related("messages", "workspace")
        if not thread:
            return
        draft = await thread.get_draft(EmailMessageType.SENDING)
        if not draft:
            return

        sender = await User.get_or_none(id=user_id, organization_id=thread.organization_id)
        if not sender or not thread.can_reply(sender):
            return

        headers = EmailHeaders(
            [
                {"name": "From", "value": draft.sender or ""},
                {"name": "To", "value": draft.to or ""},
                {"name": "Cc", "value": draft.cc or ""},
                {"name": "Bcc", "value": draft.bcc or ""},
                {"name": "Subject", "value": draft.subject or ""},
                {"name": "Date", "value": formatdate(datetime.now(UTC).timestamp())},
                {"name": "Message-ID", "value": f"<message-id-{generate_uuid()}@example.com>"},
                {"name": "MIME-Version", "value": "1.0"},
                {"name": "Content-Type", "value": 'text/plain; charset="UTF-8"'},
                {"name": "Content-Transfer-Encoding", "value": "7bit"},
                {"name": "In-Reply-To", "value": draft.in_reply_to or ""},
                {"name": "References", "value": draft.references or ""},
                {"name": "X-Mailer", "value": "Fake Email Client"},
                {"name": "X-Draft-ID", "value": str(draft.id)},
                {"name": "X-Thread-ID", "value": str(thread.id)},
                {"name": "X-User-ID", "value": str(user_id)},
            ]
        )

        await thread.mark_draft_sent(
            draft,
            sender=sender,
            external_thread_id=thread.external_thread_id or f"external-thread-{generate_uuid()}",
            external_message_id=draft.external_message_id or f"external-message-{generate_uuid()}",
            external_history_id=str(random.randint(1, 1_000_000)),
            message_id=headers.message_id or "",
            headers=headers,
            preview=draft.message.preview or draft.message.body_plain[:255] if draft.message.body_plain else "",
        )
        await thread.update_metadata_from_messages()
        await Mailbox.sync(thread)
        await self._deliver_to_local_users(draft, thread)

    async def _deliver_to_local_users(self, draft, thread: EmailThread) -> None:
        """Deliver sent message to recipient inboxes for users that exist in the app."""
        recipient_emails = (draft.message.to or []) + (draft.message.cc or []) + (draft.message.bcc or [])
        delivered_user_ids: set[UUID] = set()
        for email in recipient_emails:
            user = await local_user_for_address(email)
            if not user or user.id in delivered_user_ids:
                continue
            delivered_user_ids.add(user.id)

            result = await EmailThread.receive_new_message(
                {
                    "creator_id": user.id,
                    "user_id": user.id,
                    "organization_id": user.organization_id,
                    "external_thread_id": thread.external_thread_id,
                    "subject": draft.message.subject or "(no subject)",
                    "sender": draft.message.sender or "",
                    "to": draft.message.to or [],
                    "cc": draft.message.cc or [],
                    "body_plain": draft.message.body_plain or "",
                    "body_html": draft.message.body_html or "",
                    "preview": (draft.message.body_plain or "")[:200],
                    "message_type": EmailMessageType.RECEIVED,
                    "received_at": datetime.now(UTC),
                    "labels": [EmailLabel.INBOX, EmailLabel.UNREAD],
                }
            )
            await Mailbox(user).touch(result.thread)

    async def mark_thread_read(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass

    async def mark_thread_unread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass

    async def archive_thread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass

    async def unarchive_thread(
        self, external_thread_id: str, user_id: UUID, using_db: BaseDBAsyncClient | None = None
    ) -> None:
        pass


async def local_user_for_address(address: str) -> User | None:
    """Resolve a recipient address to a local user, tolerating display-name format
    ("Ben <ben@example.com>") and matching on email aliases as well as the primary
    address. Mirrors how inbound mail resolves recipients, so the local-only dev/test
    delivery shortcut reaches the same users a real send would."""
    parsed = EmailAddress.parse_safe(address)
    if not parsed:
        return None
    return await User.filter(User.filters.by_any_email([parsed.email])).first()


async def deliver_development(message: EmailMessage) -> str | None:
    """Opens email in browser AND creates an inbox entry for the recipient."""
    result = await _delivery_browser(message)

    user = await local_user_for_address(message.to)
    if not user:
        return result

    new_message = await EmailThread.receive_new_message(
        {
            "creator_id": user.id,
            "user_id": user.id,
            "organization_id": user.organization_id,
            "external_thread_id": f"dev_{message.id or generate_uuid().hex}",
            "subject": message.subject or "(no subject)",
            "sender": message.send_from,
            "to": [message.to],
            "body_plain": message.text,
            "body_html": message.html,
            "preview": (message.text or "")[:200],
            "message_type": EmailMessageType.RECEIVED,
            "received_at": datetime.now(UTC),
            "labels": [EmailLabel.INBOX, EmailLabel.UNREAD],
            "headers_list": list(message.headers),
        }
    )

    await Mailbox(user).touch(new_message.thread)
    return result
