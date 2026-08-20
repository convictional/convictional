import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import httplib2
import pytest
from googleapiclient.errors import HttpError

from integrations.google.gmail import (
    GmailMessageExtractor,
    GmailMessageLoader,
    GoogleAPIClient,
    _is_gmail_unavailable,
    parse_date,
)
from integrations.google.models import GmailAccount
from integrations.google.types import GmailMessagePart


def _build_http_error(status_code: int, errors: list[dict] | None = None) -> HttpError:
    body: dict = {"error": {"code": status_code, "message": "boom"}}
    if errors is not None:
        body["error"]["errors"] = errors
    resp = httplib2.Response({"status": str(status_code)})
    return HttpError(resp, json.dumps(body).encode("utf-8"))


def _build_client_raising(error: Exception) -> GoogleAPIClient:
    gmail = MagicMock()
    gmail.users.return_value.threads.return_value.modify.return_value.execute.side_effect = error
    return GoogleAPIClient(gmail_account=None, gmail=gmail)


@pytest.mark.asyncio
async def test_modify_thread_handles_missing_thread():
    # A 404 means the thread is gone from Gmail; treat as a no-op so the job stops retrying.
    client = _build_client_raising(_build_http_error(404))
    assert await client.modify_thread("thread-1", {"removeLabelIds": ["UNREAD"]}) is None

    # Other statuses must propagate so genuinely transient failures keep retrying.
    for status_code in (403, 500):
        client = _build_client_raising(_build_http_error(status_code))
        with pytest.raises(HttpError):
            await client.modify_thread("thread-1", {"removeLabelIds": ["UNREAD"]})


def test_is_gmail_unavailable():
    failed_precondition = [{"message": "Precondition failed.", "domain": "global", "reason": "failedPrecondition"}]

    # 400 with failedPrecondition reason → Gmail is unavailable on the account
    assert _is_gmail_unavailable(_build_http_error(400, failed_precondition)) is True

    # 400s for other reasons should not be treated as unavailable
    assert (
        _is_gmail_unavailable(
            _build_http_error(400, [{"message": "Bad request", "domain": "global", "reason": "invalidArgument"}])
        )
        is False
    )
    assert _is_gmail_unavailable(_build_http_error(400, errors=None)) is False

    # Non-400 statuses are out of scope, even when the reason matches
    assert _is_gmail_unavailable(_build_http_error(401, failed_precondition)) is False


def test_parse_date_none():
    result = parse_date(None)
    assert isinstance(result, datetime)
    assert result.tzinfo == UTC


def test_parse_date_valid_rfc2822():
    result = parse_date("Thu, 13 Feb 1969 23:32:54 -0330")
    assert result.year == 1969
    assert result.month == 2
    assert result.day == 13

    # Test another valid RFC 2822 format
    result = parse_date("Wed, 25 Dec 2024 10:15:30 +0000")
    assert result.year == 2024
    assert result.month == 12
    assert result.day == 25


def test_parse_date_invalid_string():
    result = parse_date("invalid date")
    assert isinstance(result, datetime)
    assert result.tzinfo == UTC


def test_extract_email_body_plain_text_only():
    extractor = GmailMessageExtractor()

    payload: GmailMessagePart = {
        "partId": "0",
        "mimeType": "text/plain",
        "headers": [],
        "body": {
            "data": "SGVsbG8gV29ybGQ="  # "Hello World" in base64
        },
    }

    plain, html = extractor.extract_email_body(payload)
    assert plain == "Hello World"
    assert html is None


def test_extract_email_body_html_only():
    extractor = GmailMessageExtractor()

    payload: GmailMessagePart = {
        "partId": "0",
        "mimeType": "text/html",
        "headers": [],
        "body": {
            "data": "PGI+SGVsbG8gV29ybGQ8L2I+"  # "<b>Hello World</b>" in base64
        },
    }

    plain, html = extractor.extract_email_body(payload)
    assert plain is None
    assert html == "<b>Hello World</b>"


def test_extract_email_body_multipart():
    extractor = GmailMessageExtractor()

    payload: GmailMessagePart = {
        "partId": "0",
        "mimeType": "multipart/alternative",
        "headers": [],
        "parts": [
            {
                "partId": "0.0",
                "mimeType": "text/plain",
                "headers": [],
                "body": {
                    "data": "SGVsbG8gV29ybGQ="  # "Hello World" in base64
                },
            },
            {
                "partId": "0.1",
                "mimeType": "text/html",
                "headers": [],
                "body": {
                    "data": "PGI+SGVsbG8gV29ybGQ8L2I+"  # "<b>Hello World</b>" in base64
                },
            },
        ],
    }

    plain, html = extractor.extract_email_body(payload)
    assert plain == "Hello World"
    assert html == "<b>Hello World</b>"


def test_find_attachments_no_attachments():
    extractor = GmailMessageExtractor()

    payload: GmailMessagePart = {
        "partId": "0",
        "mimeType": "text/plain",
        "headers": [],
        "body": {"data": "SGVsbG8gV29ybGQ="},
    }

    attachments = extractor.find_attachments(payload)
    assert attachments == []


def test_find_attachments_with_attachment():
    extractor = GmailMessageExtractor()

    payload: GmailMessagePart = {
        "partId": "0",
        "mimeType": "multipart/mixed",
        "headers": [],
        "parts": [
            {
                "partId": "0.0",
                "mimeType": "application/pdf",
                "headers": [],
                "body": {"attachmentId": "attachment123"},
                "filename": "test.pdf",
            }
        ],
    }

    attachments = extractor.find_attachments(payload)
    assert len(attachments) == 1
    assert attachments[0]["body"]["attachmentId"] == "attachment123"


def test_find_attachments_nested_parts():
    extractor = GmailMessageExtractor()

    payload: GmailMessagePart = {
        "partId": "0",
        "mimeType": "multipart/mixed",
        "headers": [],
        "parts": [
            {"partId": "0.0", "mimeType": "text/plain", "headers": [], "body": {"data": "test"}},
            {
                "partId": "0.1",
                "mimeType": "multipart/mixed",
                "headers": [],
                "parts": [
                    {
                        "partId": "0.1.0",
                        "mimeType": "application/pdf",
                        "headers": [],
                        "body": {"attachmentId": "att123"},
                        "filename": "test.pdf",
                    }
                ],
            },
        ],
    }

    attachments = extractor.find_attachments(payload)
    assert len(attachments) == 1
    assert attachments[0]["body"]["attachmentId"] == "att123"


def test_safe_parse_sender():
    loader = GmailMessageLoader(GmailAccount())

    # Normal parsing should work as expected
    result = loader._safe_parse_sender("John Doe <john@example.com>")
    assert result == "John Doe <john@example.com>"

    result = loader._safe_parse_sender("john@example.com")
    assert result == "john <john@example.com>"

    # Email repair: pipe instead of @ symbol
    result = loader._safe_parse_sender("eDocu <donotreply|us06web.zoom.us>")
    assert result == "eDocu <donotreply@us06web.zoom.us>"

    result = loader._safe_parse_sender("donotreply|domain.com")
    assert result == "donotreply <donotreply@domain.com>"

    # Email repair: URL paths in email addresses
    result = loader._safe_parse_sender("Calendar <noreply@calendar.google.com/some/path>")
    assert result == "Calendar <noreply@calendar.google.com>"

    # Email repair: both pipe and URL path
    result = loader._safe_parse_sender("eDocu <donotreply|us06web.zoom.us/meeting/abc123>")
    assert result == "eDocu <donotreply@us06web.zoom.us>"

    # Email repair: query parameters
    result = loader._safe_parse_sender("Service <email@domain.com?token=abc123>")
    assert result == "Service <email@domain.com>"

    # Display name preserved when email cannot be repaired
    result = loader._safe_parse_sender("Short Name <totally-invalid-no-at-or-domain>")
    assert result == "Short Name <unknown@example.com>"

    # Long senders exceeding 255 chars should extract email or fallback gracefully
    long_name = "A" * 300
    sender = f'"{long_name}" <valid@example.com>'
    result = loader._safe_parse_sender(sender)
    assert "valid@example.com" in result or result == "Unknown <unknown@example.com>"

    long_name = "Very Long Display Name " * 20
    sender = f"{long_name} <john@example.com>"
    result = loader._safe_parse_sender(sender)
    assert "john@example.com" in result

    long_name = "X" * 250
    sender = f'"{long_name}" <truncate@example.com>'
    result = loader._safe_parse_sender(sender)
    assert "example.com" in result or result == "Unknown <unknown@example.com>"

    # Completely malformed input should use fallback
    malformed = "X" * 500
    result = loader._safe_parse_sender(malformed)
    assert result == "Unknown <unknown@example.com>"
