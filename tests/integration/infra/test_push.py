import json
import ssl
from collections.abc import Callable
from unittest.mock import patch
from uuid import uuid4

import cryptography.exceptions
import httpx
import pytest
import requests.exceptions
from fastapi import status
from pydantic import SecretStr
from pywebpush import WebPushException

from config import settings
from config.enums import PushProtocol
from infra.push import _deliver_apns, _deliver_pywebpush, _dispatch_by_protocol, set_apns_transport


class _FakeResponse:
    """Minimal `.response`-shaped object for WebPushException — pywebpush
    attaches a requests.Response, and our code only reads `.status_code`."""

    def __init__(self, status_code: int):
        self.status_code = status_code


def _raise(exc):
    def _side_effect(*_args, **_kwargs):
        raise exc

    return _side_effect


@pytest.fixture(autouse=True)
def _run_to_thread_inline():
    """Skip the thread pool. Production fans out across devices via
    `asyncio.to_thread`, but the wrapper logic we're exercising here doesn't
    care about threading — and 19 parametrized tests each spawning a worker
    thread under pytest-asyncio's per-test loop reliably races the lifespan
    fixture into timeout."""

    async def _inline(func, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("infra.push.asyncio.to_thread", _inline):
        yield


def _kwargs(**overrides):
    base = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "p256dh_key": "p256",
        "auth_key": "auth",
        "payload": {"title": "t", "body": "b"},
        "subscription_id": uuid4(),
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_success_returns_success_result():
    with patch("infra.push.pywebpush.webpush", return_value=None):
        result = await _deliver_pywebpush(**_kwargs())
    assert result.success is True
    assert result.subscription_invalidated is False
    assert result.retryable is False


@pytest.mark.parametrize("status_code", [status.HTTP_404_NOT_FOUND, status.HTTP_410_GONE])
@pytest.mark.asyncio
async def test_invalidating_statuses_mark_subscription_dead(status_code: int):
    """404 Not Found and 410 Gone are RFC 8030 permanent failures — the caller
    is expected to soft-delete the subscription so retries don't keep firing."""
    exc = WebPushException("gone", response=_FakeResponse(status_code))
    with patch("infra.push.pywebpush.webpush", side_effect=_raise(exc)):
        result = await _deliver_pywebpush(**_kwargs())
    assert result.success is False
    assert result.subscription_invalidated is True
    assert result.retryable is False


@pytest.mark.asyncio
async def test_payload_too_large_is_permanent_not_retryable():
    """413 is a regression in payload construction — relay rejects every retry
    with the same outcome. Surface loudly, do not retry."""
    exc = WebPushException("too big", response=_FakeResponse(status.HTTP_413_CONTENT_TOO_LARGE))
    with patch("infra.push.pywebpush.webpush", side_effect=_raise(exc)):
        result = await _deliver_pywebpush(**_kwargs())
    assert result.success is False
    assert result.subscription_invalidated is False
    assert result.retryable is False


@pytest.mark.parametrize(
    "status_code",
    [
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        status.HTTP_504_GATEWAY_TIMEOUT,
    ],
)
@pytest.mark.asyncio
async def test_transient_statuses_are_retryable(status_code: int):
    """429 (rate limit) and 5xx (relay hiccup) clear themselves; Cloud Tasks's
    default backoff handles the retry cadence."""
    exc = WebPushException("transient", response=_FakeResponse(status_code))
    with patch("infra.push.pywebpush.webpush", side_effect=_raise(exc)):
        result = await _deliver_pywebpush(**_kwargs())
    assert result.success is False
    assert result.subscription_invalidated is False
    assert result.retryable is True


@pytest.mark.asyncio
async def test_unknown_status_is_conservatively_retryable():
    """An unrecognized status doesn't fit the table — conservative retry, log
    the status so we can extend the table if a real relay starts emitting it."""
    # 418 (teapot) stands in for any status not enumerated in the policy table —
    # the conservative-retry branch should catch it regardless of value.
    exc = WebPushException("weird", response=_FakeResponse(status.HTTP_418_IM_A_TEAPOT))
    with patch("infra.push.pywebpush.webpush", side_effect=_raise(exc)):
        result = await _deliver_pywebpush(**_kwargs())
    assert result.retryable is True


@pytest.mark.asyncio
async def test_missing_response_object_is_retryable():
    """pywebpush docstring says the response is sometimes None (e.g. socket
    closed before the headers arrived). No status to act on — retry."""
    exc = WebPushException("no response", response=None)
    with patch("infra.push.pywebpush.webpush", side_effect=_raise(exc)):
        result = await _deliver_pywebpush(**_kwargs())
    assert result.retryable is True


@pytest.mark.parametrize(
    "exc",
    [
        requests.exceptions.ConnectionError("dns failure"),
        requests.exceptions.Timeout("read timeout"),
        ssl.SSLError("handshake failed"),
        OSError("no route to host"),
        cryptography.exceptions.InvalidKey("malformed p256dh"),
    ],
)
@pytest.mark.asyncio
async def test_infra_failures_are_retryable(exc: Exception):
    """Genuine infra failures — network, TLS, DNS, key parsing — clear on
    retry. Narrow set: anything else propagates so it shows up in Sentry."""
    with patch("infra.push.pywebpush.webpush", side_effect=_raise(exc)):
        result = await _deliver_pywebpush(**_kwargs())
    assert result.success is False
    assert result.retryable is True


@pytest.mark.parametrize("exc_class", [TypeError, AttributeError, KeyError])
@pytest.mark.asyncio
async def test_programmer_errors_propagate(exc_class: type[Exception]):
    """A bare `except Exception` would treat programmer bugs as transient,
    looping until Cloud Tasks gives up. Let them propagate so the job
    framework surfaces them to Sentry on the first attempt."""
    with patch("infra.push.pywebpush.webpush", side_effect=_raise(exc_class("boom"))):
        with pytest.raises(exc_class):
            await _deliver_pywebpush(**_kwargs())


#
# APNs delivery (today wrapped through Expo Push Service)
#


def _apns_kwargs(**overrides):
    base = {
        "endpoint": "ExponentPushToken[abc123]",
        "payload": {
            "title": "Project Team",
            "body": "Alice mentioned you",
            "url": "https://convictional.com/chats/abc",
            "url_path": "/chats/abc",
            "tag": "mention-xyz",
        },
        "subscription_id": uuid4(),
    }
    base.update(overrides)
    return base


def _http_response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    return httpx.Response(status_code=status_code, json=json_body or {})


@pytest.fixture
def apns_transport():
    """Swap the APNs client's transport with a scriptable MockTransport.

    Tests assign `apns_transport.handler = ...` to script the per-request
    response. The fixture also exposes `captured_requests` for assertions.
    Restores the production client on teardown.
    """

    captured: list[httpx.Request] = []

    def default_handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("apns_transport.handler not set; test scripted no response")

    holder: dict[str, Callable[[httpx.Request], httpx.Response]] = {"handler": default_handler}

    def dispatch(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return holder["handler"](request)

    set_apns_transport(httpx.MockTransport(dispatch))

    class _Seam:
        @property
        def captured_requests(self) -> list[httpx.Request]:
            return captured

        def respond_with(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
            holder["handler"] = handler

        def respond_with_response(self, response: httpx.Response) -> None:
            holder["handler"] = lambda _request: response

        def respond_with_exception(self, exc: BaseException) -> None:
            def _raise(_request: httpx.Request) -> httpx.Response:
                raise exc

            holder["handler"] = _raise

    yield _Seam()
    set_apns_transport(None)


@pytest.mark.asyncio
async def test_apns_success_returns_success_result():
    result = await _deliver_apns(**_apns_kwargs())
    assert result.success is True
    assert result.subscription_invalidated is False
    assert result.retryable is False


@pytest.mark.asyncio
async def test_apns_device_not_registered_marks_subscription_dead():
    """`DeviceNotRegistered` is the APNs equivalent of web push 410 Gone."""
    result = await _deliver_apns(**_apns_kwargs())
    assert result.success is False
    assert result.subscription_invalidated is True
    assert result.retryable is False


@pytest.mark.asyncio
async def test_apns_list_shape_receipt_is_unwrapped():
    """The gateway's `data` may come back as a 1-element list or a dict."""
    result = await _deliver_apns(**_apns_kwargs())
    assert result.success is True


# MockTransport-based tests opt out of VCR — the session-wide cassette
# interception would otherwise either record a synthetic exchange or fail to
# find a matching cassette. MockTransport is the response source.


@pytest.mark.parametrize(
    "error_code",
    ["MessageTooBig", "MessageRateExceeded", "InvalidCredentials", "ProviderError", "UnknownError"],
)
@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_apns_non_invalidating_receipt_errors_are_retryable(error_code: str, apns_transport):
    apns_transport.respond_with_response(
        _http_response(200, {"data": {"status": "error", "message": "...", "details": {"error": error_code}}})
    )
    result = await _deliver_apns(**_apns_kwargs())
    assert result.success is False
    assert result.retryable is True
    assert result.subscription_invalidated is False


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_apns_send_authenticates_with_bearer_token_when_configured(apns_transport):
    """Expo's enhanced push security rejects sends that lack this Bearer token."""
    apns_transport.respond_with_response(_http_response(200, {"data": {"status": "ok"}}))
    with settings.override():
        settings.expo_access_token = SecretStr("expo-secret-token")
        await _deliver_apns(**_apns_kwargs())
    request = apns_transport.captured_requests[-1]
    assert request.headers["Authorization"] == "Bearer expo-secret-token"


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_apns_send_omits_authorization_when_token_unset(apns_transport):
    """Empty token preserves the pre-hardening unauthenticated send."""
    apns_transport.respond_with_response(_http_response(200, {"data": {"status": "ok"}}))
    with settings.override():
        settings.expo_access_token = SecretStr("")
        await _deliver_apns(**_apns_kwargs())
    request = apns_transport.captured_requests[-1]
    assert "Authorization" not in request.headers


@pytest.mark.parametrize(
    "status_code",
    [
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
    ],
)
@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_apns_transient_http_statuses_are_retryable(status_code: int, apns_transport):
    apns_transport.respond_with_response(_http_response(status_code, {}))
    result = await _deliver_apns(**_apns_kwargs())
    assert result.success is False
    assert result.retryable is True


@pytest.mark.asyncio
async def test_apns_4xx_not_429_is_permanent():
    result = await _deliver_apns(**_apns_kwargs())
    assert result.success is False
    assert result.retryable is False
    assert result.subscription_invalidated is False


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_apns_network_error_is_retryable(apns_transport):
    apns_transport.respond_with_exception(httpx.ConnectError("dns failure"))
    result = await _deliver_apns(**_apns_kwargs())
    assert result.success is False
    assert result.retryable is True


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_apns_payload_reshape_extracts_title_body_routes_rest_to_data(apns_transport):
    apns_transport.respond_with_response(_http_response(200, {"data": {"status": "ok", "id": "r1"}}))
    await _deliver_apns(
        endpoint="ExponentPushToken[abc]",
        payload={
            "title": "Project Team",
            "body": "Alice mentioned you",
            "url": "https://convictional.com/chats/c1",
            "url_path": "/chats/c1",
            "mailbox_entry_url": "https://convictional.com/chats/c1?mailbox_entry_id=e1",
            "mailbox_entry_url_path": "/chats/c1?mailbox_entry_id=e1",
            "tag": "mention-xyz",
        },
    )

    assert len(apns_transport.captured_requests) == 1
    request = apns_transport.captured_requests[0]
    assert str(request.url) == "https://exp.host/--/api/v2/push/send"
    message = json.loads(request.content)
    assert message["to"] == "ExponentPushToken[abc]"
    assert message["title"] == "Project Team"
    assert message["body"] == "Alice mentioned you"
    assert message["sound"] == "default"
    assert message["data"] == {
        "url": "https://convictional.com/chats/c1",
        "url_path": "/chats/c1",
        "mailbox_entry_url": "https://convictional.com/chats/c1?mailbox_entry_id=e1",
        "mailbox_entry_url_path": "/chats/c1?mailbox_entry_id=e1",
        "tag": "mention-xyz",
    }


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_dispatch_by_protocol_dispatches_apns_for_apns_rows(apns_transport):
    apns_transport.respond_with_response(_http_response(200, {"data": {"status": "ok", "id": "receipt-1"}}))
    with patch("infra.push.pywebpush.webpush") as webpush_mock:
        result = await _dispatch_by_protocol(
            endpoint="ExponentPushToken[xyz]",
            protocol=PushProtocol.APNS,
            p256dh_key=None,
            auth_key=None,
            payload={"title": "t", "body": "b"},
            subscription_id=uuid4(),
        )
    assert result.success is True
    webpush_mock.assert_not_called()


@pytest.mark.disable_vcr
@pytest.mark.asyncio
async def test_dispatch_by_protocol_dispatches_pywebpush_for_web_push_rows(apns_transport):
    with patch("infra.push.pywebpush.webpush", return_value=None):
        result = await _dispatch_by_protocol(
            endpoint="https://fcm.googleapis.com/fcm/send/abc",
            protocol=PushProtocol.WEB_PUSH,
            p256dh_key="p256",
            auth_key="auth",
            payload={"title": "t", "body": "b"},
            subscription_id=uuid4(),
        )
    assert result.success is True
    # MockTransport's `captured_requests` is empty: the dispatcher routed to
    # pywebpush, not Expo.
    assert apns_transport.captured_requests == []
