import logging
import re
from typing import Any

import pytest
import vcr.stubs.httpx_stubs  # type: ignore[import]
from fastapi import status
from pytest import FixtureRequest


# Patch VCR's HTTPX stubs to handle WebSocket upgrade responses properly.
#
# This is necessary because VCR's default integration with httpx does not account for WebSocket upgrade responses from
# httpx_ws that we use for testing WebSocket channels in integration tests.
#
def _patch_vcr_httpx_stubs() -> None:
    # vcrpy 8 reworked _serialize_response into a synchronous function that
    # receives the already-read response content. We still need to special-case
    # WebSocket upgrade (101) responses, which have no body to serialize.
    original_serialize_response = vcr.stubs.httpx_stubs._serialize_response

    def patched_serialize_response(real_response: Any, real_response_content: bytes) -> dict[str, Any]:
        is_websocket_upgrade_response = (
            getattr(real_response, "status_code", None) == status.HTTP_101_SWITCHING_PROTOCOLS
            and real_response.headers.get("upgrade", "").lower() == "websocket"
        )

        if is_websocket_upgrade_response:
            return {
                "status": {
                    "code": real_response.status_code,
                    "message": getattr(real_response, "reason_phrase", "Switching Protocols"),
                },
                "headers": dict(real_response.headers),
                "body": {"string": b""},
            }

        return original_serialize_response(real_response, real_response_content)

    vcr.stubs.httpx_stubs._serialize_response = patched_serialize_response


_patch_vcr_httpx_stubs()

# Because the model responses are so large, the VCR cassette INFO logs are too verbose
logging.getLogger("vcr").setLevel(logging.WARNING)

SENSITIVE_GOOGLE_QUERY_PARAMS = ["key", "cx"]
SENSITIVE_MICROSOFT_BODY_PARAMS = ["client_id", "client_secret"]

SENSITIVE_BODY_PARAM_PATTERN = re.compile(rf"(^|&)({'|'.join(SENSITIVE_MICROSOFT_BODY_PARAMS)})=[^&]*")

# Credentials that arrive in a response body rather than a header, so `filter_headers` cannot
# reach them. recall.ai returns a signed calendar auth token this way.
SENSITIVE_BODY_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{16,}"), "REDACTED"),
    (re.compile(r'("(?:access_token|refresh_token|id_token|client_secret|token)"\s*:\s*")[^"]+'), r"\1REDACTED"),
]


def scrub_request(request: Any) -> Any:
    """Redacts OAuth client credentials from a form-encoded request body.

    vcrpy's own `filter_post_data_parameters` cannot do this job: it decodes every POST body as
    UTF-8, which raises on the multipart uploads the attachment tests record, and it re-serializes
    every JSON body whether or not it holds a filtered parameter.
    """
    if not isinstance(request.body, bytes | str):
        return request

    try:
        text = request.body.decode() if isinstance(request.body, bytes) else request.body
    except UnicodeDecodeError:
        return request  # Multipart upload or other binary body, which never carries these.

    scrubbed = SENSITIVE_BODY_PARAM_PATTERN.sub(r"\1\2=REDACTED", text)
    if scrubbed != text:
        request.body = scrubbed.encode() if isinstance(request.body, bytes) else scrubbed
    return request


def scrub_body(body: bytes | str) -> bytes | str:
    """Redacts credential-shaped values in a recorded response body.

    Bodies are scrubbed as text, so the UnicodeDecodeError bail-out below is where the limit
    sits: a body that stops being decodable passes through unscrubbed. Nothing recorded today is
    compressed or binary. If an integration starts returning compressed auth tokens, decompress
    here before scrubbing.
    """
    try:
        text = body.decode() if isinstance(body, bytes) else body
    except UnicodeDecodeError:
        return body

    for pattern, replacement in SENSITIVE_BODY_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.encode() if isinstance(body, bytes) else text


@pytest.fixture(scope="session", autouse=True)
def vcr_config(request: FixtureRequest):
    def scrub_response(response):
        response["headers"].pop("Set-Cookie", None)
        response["headers"].pop("openai-organization", None)

        body = (response.get("body") or {}).get("string")
        if body:
            response["body"]["string"] = scrub_body(body)

        return response

    config = {
        "ignore_localhost": True,
        "ignore_hosts": [
            "testserver",  # The app under test
            "o4506098477236224.ingest.sentry.io",  # DeepEval's telemetry
            "openaipublic.blob.core.windows.net",  # OpenAI Tokenization Tables
        ],
        "filter_headers": [
            "authorization",
            "api-key",
            "baggage",  # Sentry distributed trace context, carries our public key and org id
            "cookie",
            "openai-organization",
            "sentry-trace",
            "user-agent",
            "x-recallcalendarauthtoken",
            "x-api-key",
        ],
        "filter_query_parameters": SENSITIVE_GOOGLE_QUERY_PARAMS,
        "before_record_request": scrub_request,
        "before_record_response": scrub_response,
    }

    # Default to "new_episodes" only when the CLI didn't specify a mode. When --record-mode is
    # passed (e.g. "rewrite"), leave it out of the config so pytest-recording owns it — putting it
    # here would re-inject the raw value into vcr.use_cassette and bypass pytest-recording's
    # "rewrite" translation, which vcrpy >=8 rejects as an invalid mode.
    if request.config.getoption("--record-mode") is None:
        config["record_mode"] = "new_episodes"

    return config


def mark_as_vcr(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        # Apply a custom marker, e.g., a marker named "vcr"
        # Check if the test already has a "vcr" marker to avoid duplication
        if not any(marker.name == "vcr" for marker in item.iter_markers()):
            item.add_marker(pytest.mark.vcr)
