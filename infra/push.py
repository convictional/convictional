import asyncio
import json
import ssl
from collections.abc import Callable
from dataclasses import dataclass, field
from uuid import UUID

import cryptography.exceptions
import httpx
import pywebpush
import requests.exceptions
from fastapi import status
from pywebpush import WebPushException

from config import logger, settings
from config.enums import PushProtocol
from config.settings import PushDelivery


@dataclass
class PushSendResult:
    """Per-attempt outcome.

    `subscription_invalidated` → caller soft-deletes the row (web push: 404/410;
    APNs: DeviceNotRegistered receipt). `retryable` → transient; caller retries.
    """

    success: bool
    subscription_invalidated: bool = False
    retryable: bool = False


# Push relays use HTTP status codes as a delivery signal per RFC 8030 §5:
# 404 Not Found and 410 Gone both mean the subscription will never accept
# another push — the user disabled push, cleared site data, or the device
# rotated keys without notifying us.
_INVALIDATING_STATUSES = {status.HTTP_404_NOT_FOUND, status.HTTP_410_GONE}
# Payload-too-large is permanent: the relay will reject every retry until the
# payload shrinks. Treat it as a delivery failure to alert on, not a retry.
_PAYLOAD_TOO_LARGE_STATUS = status.HTTP_413_CONTENT_TOO_LARGE


@dataclass
class SentPush:
    endpoint: str
    payload: dict
    protocol: PushProtocol = PushProtocol.WEB_PUSH
    # Web-push only; APNs encrypts on the relay side.
    p256dh_key: str | None = None
    auth_key: str | None = None
    subscription_id: UUID | None = None


# A programmable outcome lets a test script the relay's response per call
# without having to swap implementations. The default behaves like a healthy
# relay; tests reset and reassign before exercising failure paths.
OutcomeFn = Callable[[SentPush], PushSendResult]


def _default_outcome(_sent: SentPush) -> PushSendResult:
    return PushSendResult(success=True)


@dataclass
class FakePushDelivery:
    """In-process push relay used in tests and development.

    Mirrors `infra.email.FakeDelivery`. Records every send for assertion and
    routes the outcome through `outcome_fn` so tests can script invalidation,
    retryable, or success responses without monkey-patching `pywebpush` /
    `httpx`. Captures both web-push and APNs deliveries; the `protocol` on
    each recorded `SentPush` distinguishes them.
    """

    sent: list[SentPush] = field(default_factory=list)
    outcome_fn: OutcomeFn = field(default=_default_outcome)

    async def deliver(
        self,
        *,
        endpoint: str,
        protocol: PushProtocol,
        p256dh_key: str | None,
        auth_key: str | None,
        payload: dict,
        subscription_id: UUID | None = None,
    ) -> PushSendResult:
        record = SentPush(
            endpoint=endpoint,
            protocol=protocol,
            p256dh_key=p256dh_key,
            auth_key=auth_key,
            payload=payload,
            subscription_id=subscription_id,
        )
        self.sent.append(record)
        return self.outcome_fn(record)

    def reset(self) -> None:
        self.sent.clear()
        self.outcome_fn = _default_outcome

    def respond_with(self, outcome: PushSendResult | OutcomeFn) -> None:
        """Configure the next (and subsequent) deliveries to return this outcome.

        Accepts either a `PushSendResult` (same outcome for every call) or an
        `OutcomeFn` (per-call decisions, e.g. invalidate only specific endpoints).
        """
        if callable(outcome):
            self.outcome_fn = outcome
        else:
            self.outcome_fn = lambda _sent: outcome

    def by_endpoint(self, endpoint: str) -> list[SentPush]:
        return [push for push in self.sent if push.endpoint == endpoint]


fake_push_delivery = FakePushDelivery()


async def _deliver_pywebpush(
    *,
    endpoint: str,
    p256dh_key: str | None,
    auth_key: str | None,
    payload: dict,
    subscription_id: UUID | None = None,
) -> PushSendResult:
    """Real delivery — pywebpush is synchronous (requests + cryptography).

    asyncio.to_thread hands the call to the default executor so concurrent
    fan-out across devices actually parallelizes instead of serializing under
    the event loop. Never log the subscription_info dict or the vapid private
    key — the p256dh/auth pair is enough to forge a push to this device.
    Never log the `WebPushException` directly either: its `.message` and
    `.response.text` embed endpoint URLs and FCM/Mozilla response bodies that
    leak per-device identifiers into Sentry.
    """
    try:
        await asyncio.to_thread(
            pywebpush.webpush,
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh_key, "auth": auth_key},
            },
            data=json.dumps(payload),
            vapid_private_key=settings.vapid_private_key.get_secret_value(),
            vapid_claims={"sub": settings.vapid_subject},
        )
        return PushSendResult(success=True)
    except WebPushException as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in _INVALIDATING_STATUSES:
            return PushSendResult(success=False, subscription_invalidated=True)
        log_context = {
            "status_code": status_code,
            "subscription_id": str(subscription_id) if subscription_id else None,
        }
        if status_code == _PAYLOAD_TOO_LARGE_STATUS:
            # 413 means the relay rejected the payload for being too large.
            # Retrying it as-is will fail forever — `_finalize_payload` is
            # supposed to keep us under the 4KB ceiling, so this firing means
            # a regression in payload construction. Loud log, no retry.
            logger.error("push send rejected payload as too large", extra=log_context)
            return PushSendResult(success=False)
        # 429 / 5xx / unknown: conservative retry. Cloud Tasks backs off, so a
        # genuinely transient relay outage repairs itself within a few attempts.
        logger.warning("push send failed", extra=log_context)
        return PushSendResult(success=False, retryable=True)
    except (requests.exceptions.RequestException, ssl.SSLError, OSError, cryptography.exceptions.InvalidKey):
        # Genuine infra failures: network, TLS, DNS, key parsing. Programmer
        # errors (TypeError, AttributeError) propagate so the job framework
        # surfaces them in Sentry instead of looping until Cloud Tasks gives up.
        logger.warning(
            "push send raised infra failure",
            extra={"subscription_id": str(subscription_id) if subscription_id else None},
        )
        return PushSendResult(success=False, retryable=True)


# APNs delivery wraps Apple's relay via Expo Push Service; the URL is in
# `settings.expo_push_url` so an Enterprise tenant or a direct-APNs migration
# only needs a config change. Error-code names below are gateway-specific and
# stay inside _deliver_apns.
_EXPO_PUSH_TIMEOUT_SECONDS = 10.0
# Per https://docs.expo.dev/push-notifications/sending-notifications/#push-receipt-errors,
# `DeviceNotRegistered` is the APNs equivalent of web push 410 Gone.
_EXPO_INVALIDATING_ERRORS = {"DeviceNotRegistered"}

# Module-level client gives connection reuse + HTTP/2 multiplexing across the
# per-device fan-out in `app/jobs/push.py`. Lazy-initialized so importing this
# module before an event loop exists is fine.
_apns_client: httpx.AsyncClient | None = None


def _get_apns_client() -> httpx.AsyncClient:
    global _apns_client
    if _apns_client is None:
        _apns_client = httpx.AsyncClient(timeout=_EXPO_PUSH_TIMEOUT_SECONDS)
    return _apns_client


def set_apns_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Test seam: swap the module client's transport (e.g., httpx.MockTransport).

    Passing None resets to the default real-network transport. Production
    callers never touch this; only test fixtures.
    """
    global _apns_client
    if transport is None:
        _apns_client = None
        return
    _apns_client = httpx.AsyncClient(transport=transport, timeout=_EXPO_PUSH_TIMEOUT_SECONDS)


async def _deliver_apns(
    *,
    endpoint: str,
    payload: dict,
    subscription_id: UUID | None = None,
) -> PushSendResult:
    """Deliver to Apple's APNs via the Expo Push Service gateway.

    Reshapes the shared web/native payload into the gateway envelope and
    maps gateway-specific outcomes onto the `PushSendResult` contract.
    """
    expo_message = {
        "to": endpoint,
        "title": payload["title"],
        "body": payload["body"],
        # Non-title/body fields stay in `data` so the native tap handler can
        # read `url_path` and route the WebView.
        "data": {key: value for key, value in payload.items() if key not in ("title", "body")},
        # Without this, Expo delivers silent (banner-only) notifications.
        "sound": "default",
    }
    log_context = {"subscription_id": str(subscription_id) if subscription_id else None}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    # Authenticate the send when a token is configured; Expo's enhanced push
    # security rejects sends that lack it. Unset means an unauthenticated send.
    access_token = settings.expo_access_token.get_secret_value()
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    try:
        response = await _get_apns_client().post(
            str(settings.expo_push_url),
            json=expo_message,
            headers=headers,
        )
    except httpx.HTTPError:
        logger.warning("apns push send raised infra failure", extra=log_context)
        return PushSendResult(success=False, retryable=True)

    if response.status_code >= 500 or response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        logger.warning(
            "apns push send transient failure",
            extra={**log_context, "status_code": response.status_code},
        )
        return PushSendResult(success=False, retryable=True)

    if response.status_code != status.HTTP_200_OK:
        logger.error(
            "apns push send rejected request",
            extra={**log_context, "status_code": response.status_code},
        )
        return PushSendResult(success=False)

    try:
        body = response.json()
    except ValueError:
        logger.warning("apns push send returned non-JSON 200", extra=log_context)
        return PushSendResult(success=False, retryable=True)

    # Single-message POST returns one receipt in `data`; tolerate the
    # batched-style list shape too in case the contract normalizes.
    receipts = body.get("data")
    receipt = receipts[0] if isinstance(receipts, list) and receipts else receipts
    if not isinstance(receipt, dict):
        logger.warning("apns push send returned unexpected body shape", extra=log_context)
        return PushSendResult(success=False, retryable=True)

    if receipt.get("status") == "ok":
        return PushSendResult(success=True)

    error_code = (receipt.get("details") or {}).get("error")
    if error_code in _EXPO_INVALIDATING_ERRORS:
        return PushSendResult(success=False, subscription_invalidated=True)

    logger.warning(
        "apns push send receipt error",
        extra={**log_context, "error_code": error_code or "unknown"},
    )
    return PushSendResult(success=False, retryable=True)


async def _dispatch_by_protocol(
    *,
    endpoint: str,
    protocol: PushProtocol,
    p256dh_key: str | None,
    auth_key: str | None,
    payload: dict,
    subscription_id: UUID | None = None,
) -> PushSendResult:
    if protocol == PushProtocol.APNS:
        return await _deliver_apns(endpoint=endpoint, payload=payload, subscription_id=subscription_id)
    return await _deliver_pywebpush(
        endpoint=endpoint,
        p256dh_key=p256dh_key,
        auth_key=auth_key,
        payload=payload,
        subscription_id=subscription_id,
    )


PUSH_DELIVERY = {
    PushDelivery.FAKE: fake_push_delivery.deliver,
    PushDelivery.NETWORK: _dispatch_by_protocol,
}


async def send_push(
    *,
    endpoint: str,
    protocol: PushProtocol,
    p256dh_key: str | None,
    auth_key: str | None,
    payload: dict,
    subscription_id: UUID | None = None,
) -> PushSendResult:
    """Send a single push to one device through the configured delivery backend."""
    return await PUSH_DELIVERY[settings.push_delivery](
        endpoint=endpoint,
        protocol=protocol,
        p256dh_key=p256dh_key,
        auth_key=auth_key,
        payload=payload,
        subscription_id=subscription_id,
    )
