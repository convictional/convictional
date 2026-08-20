#!/usr/bin/env python3
import argparse
import asyncio
import random
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from app.helpers.strings import html_to_plain_text
from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.email.thread import EmailThread
from config.enums import EmailLabel, EmailMessageType
from scripts.helpers import in_app_lifespan


async def main(thread_id: str, sender: str | None, subject: str | None, body_file: str | None):
    thread = await EmailThread.get(id=UUID(thread_id)).prefetch_related("creator")

    print(f"Adding message to thread: {thread.title}")

    unique_id = uuid4().hex[:8]
    sender = sender or "John Doe <john@example.com>"
    subject = subject or thread.title

    if body_file:
        body_path = Path(body_file)
        if not body_path.exists():
            raise FileNotFoundError(f"Body file not found: {body_file}")
        body_html = body_path.read_text(encoding="utf-8")
        body_plain = html_to_plain_text(body_html)
    else:
        body_plain = "Hello world!"
        body_html = f"<p>{body_plain}</p>"

    message_data = {
        "user_id": thread.creator_id,
        "organization_id": thread.organization_id,
        "external_message_id": f"msg_{unique_id}",
        "external_thread_id": thread.external_thread_id,
        "external_history_id": str(random.randint(10000, 999999)),
        "message_id": f"message_{unique_id}@example.com",
        "message_type": EmailMessageType.RECEIVED,
        "subject": subject,
        "sender": sender,
        "to": [thread.creator.email],
        "cc": [],
        "bcc": [],
        "body_plain": body_plain,
        "body_html": body_html,
        "preview": body_plain[:100] if len(body_plain) > 100 else body_plain,
        "received_at": datetime.now(UTC),
        "sent_at": datetime.now(UTC),
        "labels": [EmailLabel.INBOX, EmailLabel.UNREAD],
        "raw_data": {},
        "headers_list": [
            {"name": "From", "value": sender},
            {"name": "To", "value": thread.creator.email},
            {"name": "Subject", "value": subject},
        ],
    }

    result = await EmailThread.receive_new_message(message_data)

    # Sync the thread the message actually landed in, not the one we looked up:
    # when the looked-up thread has no external_thread_id (e.g. demo-seeded), the
    # message resolves into a fresh thread. Mirrors the production inbound path
    # (integrations/google/jobs/gmail.py).
    await Mailbox.sync(result.thread)

    print(f"Message added successfully: {result.email.id}")
    if result.thread.id != thread.id:
        print(
            f"Note: message landed in a different thread ({result.thread.id}) — "
            "original thread had no external_thread_id"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add a new message to an existing email thread.")
    parser.add_argument("thread_id", help="ID of the email thread to add the message to")
    parser.add_argument("--sender", help="Sender email address (defaults to 'John Doe <john@example.com>')")
    parser.add_argument("--subject", help="Message subject (defaults to thread title)")
    parser.add_argument("--body-file", help="Path to file containing the message body HTML")
    args = parser.parse_args()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    loop.run_until_complete(
        in_app_lifespan(
            main(
                thread_id=args.thread_id,
                sender=args.sender,
                subject=args.subject,
                body_file=args.body_file,
            )
        )
    )
