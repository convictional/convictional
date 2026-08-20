from datetime import UTC, datetime
from uuid import uuid4

import pytest
from itsdangerous import URLSafeSerializer
from jinja2 import DictLoader, Environment, select_autoescape

from config import settings
from infra.email import (
    EmailHeaders,
    EmailMessage,
    EmailRenderer,
    InboundEmail,
    InboundEmailRouter,
    MailgunInboundEmail,
    sign_attachment_download_token,
    verify_attachment_download_token,
)


def test_attachment_download_token_round_trip():
    """A signed token round-trips to its attachment id; bad and wrong-salt tokens fail.

    Tokens never expire — the attachment must stay downloadable however long after sending
    the recipient opens the email — so there is no expiry case to assert here.
    """
    attachment_id = uuid4()
    token = sign_attachment_download_token(attachment_id)

    assert verify_attachment_download_token(token) == attachment_id

    # Tampered token
    assert verify_attachment_download_token(token + "x") is None

    # Wrong salt (a token signed for a different purpose must not validate)
    wrong_salt = URLSafeSerializer(settings.secret_key.get_secret_value(), salt="something-else").dumps(
        str(attachment_id)
    )
    assert verify_attachment_download_token(wrong_salt) is None


def test_email_headers_get_one():
    """Test EmailHeaders get_one method for retrieving single header values."""
    headers_data = [
        {"name": "From", "value": "alice@example.com"},
        {"name": "To", "value": "bob@example.com"},
        {"name": "Subject", "value": "Test Subject"},
        {"name": "Date", "value": "Mon, 1 Jan 2024 12:00:00 +0000"},
    ]
    headers = EmailHeaders(headers_data)

    assert headers.get_one("From") == "alice@example.com"
    assert headers.get_one("Subject") == "Test Subject"
    assert headers.get_one("Date") == "Mon, 1 Jan 2024 12:00:00 +0000"
    assert headers.get_one("Missing") is None
    assert headers.get_one("Missing", "default") == "default"


def test_email_headers_get_one_case_insensitive():
    """Test EmailHeaders get_one method is case insensitive."""
    headers_data = [{"name": "Content-Type", "value": "text/html"}]
    headers = EmailHeaders(headers_data)

    assert headers.get_one("content-type") == "text/html"
    assert headers.get_one("CONTENT-TYPE") == "text/html"
    assert headers.get_one("Content-Type") == "text/html"


def test_email_headers_get_all():
    """Test EmailHeaders get_all method for retrieving multiple header values."""
    headers_data = [
        {"name": "Received", "value": "from server1.example.com"},
        {"name": "Received", "value": "from server2.example.com"},
        {"name": "X-Custom", "value": "value1"},
        {"name": "X-Custom", "value": "value2"},
    ]
    headers = EmailHeaders(headers_data)

    received = headers.get_all("Received")
    assert len(received) == 2
    assert "from server1.example.com" in received
    assert "from server2.example.com" in received

    custom = headers.get_all("X-Custom")
    assert len(custom) == 2
    assert "value1" in custom
    assert "value2" in custom

    assert headers.get_all("Missing") == []


def test_email_message_default_headers():
    message = EmailMessage(to="test@example.com", subject="Test")
    assert isinstance(message.headers, EmailHeaders)
    assert len(message.headers) == 0


def test_email_message_custom_headers():
    headers = EmailHeaders(
        [
            {"name": "X-Custom-Header", "value": "custom-value"},
            {"name": "X-Another-Header", "value": "another-value"},
        ]
    )
    message = EmailMessage(to="test@example.com", subject="Test", headers=headers)

    assert len(message.headers) == 2
    assert message.headers.get_one("X-Custom-Header") == "custom-value"
    assert message.headers.get_one("X-Another-Header") == "another-value"


def test_inbound_email_all_recipients():
    email = InboundEmail(
        sender="sender@example.com",
        to=["Name1 <to1@example.com>"],
        cc=["Name2 <cc1@example.com>"],
        bcc=["Name3 <bcc1@example.com>"],
        subject="",
        body_plain="",
    )
    expected_recipients = {"Name1 <to1@example.com>", "Name2 <cc1@example.com>", "Name3 <bcc1@example.com>"}
    assert email.all_recipients == expected_recipients


def test_inbound_email_all_recipient_emails():
    email = InboundEmail(
        sender="sender@example.com",
        to=["Name1 <to1@example.com>"],
        cc=["Name2 <cc1@example.com>"],
        bcc=["Name3 <bcc1@example.com>"],
        subject="",
        body_plain="",
    )
    expected_emails = sorted(["to1@example.com", "cc1@example.com", "bcc1@example.com"])
    assert sorted(email.all_recipient_emails) == expected_emails


@pytest.mark.asyncio
async def test_inbound_email_router_matches_whole_addresses():
    router = InboundEmailRouter()
    routed: list[str] = []

    @router.register_handler(lambda: "research@example.com")
    async def handle(email: InboundEmail) -> None:
        routed.append(email.subject)

    async def route(subject: str, to: list[str]) -> None:
        await router._process_email(InboundEmail(sender="sender@example.com", to=to, subject=subject, body_plain=""))

    # A display name around the address still routes, and case doesn't matter.
    await route("display name", ["Research <Research@example.com>"])
    # Neither a longer local part nor a domain differing by one character may collect it.
    await route("longer local part", ["also-research@example.com"])
    await route("domain lookalike", ["research@exampleXcom"])
    # An unconfigured route matches nothing rather than everything.
    router.handlers = [(lambda: "", handle)]
    await route("unconfigured", ["anyone@example.com"])

    assert routed == ["display name"]


def test_inbound_email_reference_ids():
    email = InboundEmail(
        sender="sender@example.com",
        to=["to@example.com"],
        subject="",
        body_plain="",
        references="<ref1> <ref2>",
    )
    assert email.reference_ids == ["<ref1>", "<ref2>"]


def test_inbound_email_received_at():
    email = InboundEmail(
        sender="sender@example.com",
        to=["to@example.com"],
        subject="",
        body_plain="",
        timestamp="1609459200",
    )
    assert email.received_at == datetime.fromtimestamp(1609459200, UTC)


@pytest.mark.asyncio
async def test_mailgun_inbound_email_from_form_data():
    data = {
        "from": "Alice <alice@example.com>",
        "To": "Bob <bob@example.com>, Carol <carol@example.com>",
        "Cc": "Dave <dave@example.com>",
        "Bcc": "",
        "subject": "Testing",
        "body-plain": "This is a test.",
        "body-html": "<p>This is a test.</p>",
        "stripped-text": "This is a test.",
        "stripped-html": "<p>This is a test.</p>",
        "Message-Id": "msg-123",
        "In-Reply-To": "msg-321",
        "References": "<ref1> <ref2>",
        "timestamp": "1609459200",
        "attachment-count": "0",
    }
    email = MailgunInboundEmail.from_form_data(data)

    assert email.sender == "Alice <alice@example.com>"
    assert email.to == ["Bob <bob@example.com>", "Carol <carol@example.com>"]
    assert email.cc == ["Dave <dave@example.com>"]
    assert email.bcc == []
    assert email.subject == "Testing"
    assert email.body_plain == "This is a test."
    assert email.body_html == "<p>This is a test.</p>"
    assert email.message_id == "msg-123"
    assert email.in_reply_to == "msg-321"
    assert email.references == "<ref1> <ref2>"
    assert email.timestamp == "1609459200"
    assert email.raw == data


@pytest.mark.asyncio
async def test_mailgun_inbound_email_get_attachments_empty():
    email = MailgunInboundEmail(
        sender="sender@example.com",
        to=["to@example.com"],
        subject="Test",
        body_plain="Test body",
        attachment_count=0,
    )
    attachments = await email.get_attachments()
    assert attachments == []

    streams = await email.get_attachment_streams()
    assert streams == []


def test_email_renderer_unescapes_html_entities_in_subject():
    env = Environment(
        loader=DictLoader(
            {
                "test.jinja": (
                    "{% block subject %}(Meeting) {{ title }}{% endblock %}"
                    "{% block body_text %}body{% endblock %}"
                    "{% block body_html %}<p>body</p>{% endblock %}"
                ),
                "meta.jinja": "",
            }
        ),
        autoescape=select_autoescape(["html", "jinja"]),
    )
    renderer = EmailRenderer(templates=env)
    message = EmailMessage(to="test@example.com")

    result = renderer.render(message, "test.jinja", title="Matt <> Roger and Bill")

    assert result.subject == "(Meeting) Matt <> Roger and Bill"
    assert "&lt;" not in result.subject
    assert "&gt;" not in result.subject
