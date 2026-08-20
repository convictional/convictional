import pytest
from fastapi import status

from app.models.accounts import PushSubscription
from config.enums import PushProtocol
from infra.db import allow_soft_deleted
from tests.helpers.app import AppClient
from tests.helpers.factories import create_push_subscription, create_user


def _subscription_body(endpoint: str = "https://fcm.googleapis.com/fcm/send/abc123", **overrides) -> dict:
    body = {
        "endpoint": endpoint,
        "keys": {"p256dh": "p256dh-key-value", "auth": "auth-key-value"},
        "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_create_subscription_persists_and_returns_payload(client: AppClient):
    user = await client.get_default_user()

    response = await client.post("/api/push/subscriptions", json=_subscription_body())
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["endpoint_suffix"].startswith("…")
    assert data["endpoint_suffix"].endswith("end/abc123")
    assert data["platform"] == "Chrome on macOS"

    subscription = await PushSubscription.get(id=data["id"])
    assert subscription.user_id == user.id
    assert subscription.endpoint == "https://fcm.googleapis.com/fcm/send/abc123"
    assert subscription.p256dh_key == "p256dh-key-value"
    assert subscription.auth_key == "auth-key-value"


@pytest.mark.asyncio
async def test_list_subscriptions_returns_only_active_for_current_user(client: AppClient):
    user = await client.get_default_user()
    active = await create_push_subscription(user_id=user.id, platform="Chrome on macOS")
    deleted_sub = await create_push_subscription(user_id=user.id, platform="Firefox on Linux")
    await deleted_sub.soft_delete()
    other = await create_user()
    await create_push_subscription(user_id=other.id)

    response = await client.get("/api/push/subscriptions")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["next_cursor"] is None
    assert body["has_more"] is False
    ids = [d["id"] for d in body["subscriptions"]]
    assert ids == [str(active.id)]


@pytest.mark.asyncio
async def test_create_subscription_same_user_idempotent(client: AppClient):
    """D1: re-POST with the same endpoint returns the existing row, doesn't duplicate."""
    user = await client.get_default_user()

    first = await client.post("/api/push/subscriptions", json=_subscription_body())
    second = await client.post("/api/push/subscriptions", json=_subscription_body())

    # First call creates → 201; second call refreshes the existing row → 200.
    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_200_OK
    assert first.json()["id"] == second.json()["id"]
    assert await PushSubscription.filter(user_id=user.id).count() == 1


@pytest.mark.asyncio
async def test_create_subscription_restores_soft_deleted_row(client: AppClient):
    user = await client.get_default_user()
    existing = await create_push_subscription(user_id=user.id, endpoint="https://fcm.googleapis.com/fcm/send/abc123")
    await existing.soft_delete()

    response = await client.post("/api/push/subscriptions", json=_subscription_body())
    # Restoring a soft-deleted row is a refresh of an existing resource, not a create.
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == str(existing.id)

    refreshed = await PushSubscription.get(id=existing.id)
    assert refreshed.deleted_at is None
    # Re-registration should refresh the keys in case the device rotated them.
    assert refreshed.p256dh_key == "p256dh-key-value"


@pytest.mark.asyncio
async def test_create_subscription_takes_over_endpoint_from_different_user(client: AppClient):
    """D1: a different-user collision means the device changed account; the previous row is removed."""
    user = await client.get_default_user()
    other_user = await create_user()
    stale = await create_push_subscription(
        user_id=other_user.id, endpoint="https://fcm.googleapis.com/fcm/send/abc123"
    )

    response = await client.post("/api/push/subscriptions", json=_subscription_body())
    assert response.status_code == status.HTTP_201_CREATED

    async with allow_soft_deleted():
        assert await PushSubscription.filter(id=stale.id).first() is None
    new = await PushSubscription.get(id=response.json()["id"])
    assert new.user_id == user.id


@pytest.mark.asyncio
async def test_create_subscription_rotated_from_soft_deletes_old(client: AppClient):
    user = await client.get_default_user()
    old = await create_push_subscription(user_id=user.id, endpoint="https://fcm.googleapis.com/fcm/send/old-endpoint")

    response = await client.post(
        "/api/push/subscriptions",
        json=_subscription_body(
            endpoint="https://fcm.googleapis.com/fcm/send/new-endpoint",
            rotated_from="https://fcm.googleapis.com/fcm/send/old-endpoint",
        ),
    )
    assert response.status_code == status.HTTP_201_CREATED

    refreshed_old = await PushSubscription.deleted.get(id=old.id)
    assert refreshed_old.deleted_at is not None


@pytest.mark.asyncio
async def test_create_subscription_rate_limited_at_20_active_rows(client: AppClient):
    user = await client.get_default_user()
    for index in range(PushSubscription.MAX_ACTIVE_PER_USER):
        await create_push_subscription(
            user_id=user.id, endpoint=f"https://fcm.googleapis.com/fcm/send/existing-{index}"
        )

    response = await client.post(
        "/api/push/subscriptions",
        json=_subscription_body(endpoint="https://fcm.googleapis.com/fcm/send/over-the-limit"),
    )
    assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    # Soft-deleted rows should not count toward the cap.
    extra = await create_push_subscription(
        user_id=user.id, endpoint="https://fcm.googleapis.com/fcm/send/will-be-deleted"
    )
    await extra.soft_delete()
    # Free a slot and confirm we can register again.
    one_active = await PushSubscription.filter(user_id=user.id).first()
    assert one_active is not None
    await one_active.soft_delete()

    response = await client.post(
        "/api/push/subscriptions",
        json=_subscription_body(endpoint="https://fcm.googleapis.com/fcm/send/now-allowed"),
    )
    assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.asyncio
async def test_delete_subscription_soft_deletes(client: AppClient):
    user = await client.get_default_user()
    subscription = await create_push_subscription(user_id=user.id)

    response = await client.delete(f"/api/push/subscriptions/{subscription.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    refreshed = await PushSubscription.deleted.get(id=subscription.id)
    assert refreshed.deleted_at is not None


@pytest.mark.asyncio
async def test_delete_subscription_returns_404_for_other_users_row(client: AppClient):
    """404, not 403 — 403 leaks existence of the id to a probing attacker."""
    await client.get_default_user()
    other_user = await create_user()
    other_subscription = await create_push_subscription(user_id=other_user.id)

    response = await client.delete(f"/api/push/subscriptions/{other_subscription.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    refreshed = await PushSubscription.get(id=other_subscription.id)
    assert refreshed.deleted_at is None


@pytest.mark.asyncio
async def test_delete_subscription_returns_404_for_unknown_id(client: AppClient):
    await client.get_default_user()
    response = await client.delete("/api/push/subscriptions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_subscription_endpoints_require_auth(client: AppClient):
    with client.logged_out():
        get_response = await client.get("/api/push/subscriptions")
        post_response = await client.post("/api/push/subscriptions", json=_subscription_body())
        delete_response = await client.delete("/api/push/subscriptions/00000000-0000-0000-0000-000000000000")
    assert get_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert post_response.status_code == status.HTTP_401_UNAUTHORIZED
    assert delete_response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_create_apns_subscription_persists_apns_row(client: AppClient):
    user = await client.get_default_user()

    response = await client.post(
        "/api/push/subscriptions",
        json={
            "protocol": "apns",
            "device_token": "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]",
            "user_agent": "Convictional/1.0 (iPhone17,1; iOS 26.5)",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    subscription = await PushSubscription.get(id=response.json()["id"])
    assert subscription.user_id == user.id
    assert subscription.endpoint == "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"
    assert subscription.protocol == PushProtocol.APNS
    assert subscription.p256dh_key is None
    assert subscription.auth_key is None


@pytest.mark.asyncio
async def test_create_apns_subscription_idempotent_on_repeat(client: AppClient):
    """Re-POSTs (token rotation, WebHost remount) must refresh, not stack."""
    await client.get_default_user()
    body = {"protocol": "apns", "device_token": "ExponentPushToken[same-token]", "user_agent": "ua"}

    first = await client.post("/api/push/subscriptions", json=body)
    second = await client.post("/api/push/subscriptions", json=body)

    assert first.status_code == status.HTTP_201_CREATED
    assert second.status_code == status.HTTP_200_OK
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_create_apns_subscription_requires_auth(client: AppClient):
    with client.logged_out():
        response = await client.post(
            "/api/push/subscriptions",
            json={"protocol": "apns", "device_token": "ExponentPushToken[x]"},
        )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_create_apns_subscription_rejects_empty_token(client: AppClient):
    await client.get_default_user()
    response = await client.post(
        "/api/push/subscriptions",
        json={"protocol": "apns", "device_token": ""},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_apns_and_web_subscriptions_coexist_for_same_user(client: AppClient):
    user = await client.get_default_user()

    web_response = await client.post("/api/push/subscriptions", json=_subscription_body())
    apns_response = await client.post(
        "/api/push/subscriptions",
        json={"protocol": "apns", "device_token": "ExponentPushToken[mobile]"},
    )
    assert web_response.status_code == status.HTTP_201_CREATED
    assert apns_response.status_code == status.HTTP_201_CREATED

    rows = await PushSubscription.filter(user_id=user.id).order_by("protocol").all()
    assert [row.protocol for row in rows] == [PushProtocol.APNS, PushProtocol.WEB_PUSH]


@pytest.mark.asyncio
async def test_legacy_web_push_payload_without_protocol_is_treated_as_web_push(client: AppClient):
    """Back-compat for the deployed service worker, which posts the legacy shape
    (no `protocol` field). The schema's discriminator defaults missing
    `protocol` to `web_push`. Remove this test alongside the discriminator
    fallback once SW telemetry shows zero no-protocol POSTs."""
    user = await client.get_default_user()

    response = await client.post(
        "/api/push/subscriptions",
        json={
            "endpoint": "https://fcm.googleapis.com/fcm/send/legacy",
            "keys": {"p256dh": "p256dh-key-value", "auth": "auth-key-value"},
            "user_agent": "Mozilla/5.0 legacy SW",
        },
    )
    assert response.status_code == status.HTTP_201_CREATED

    subscription = await PushSubscription.get(id=response.json()["id"])
    assert subscription.user_id == user.id
    assert subscription.protocol == PushProtocol.WEB_PUSH


@pytest.mark.asyncio
async def test_update_working_hours_persists_both_fields(client: AppClient):
    user = await client.get_default_user()

    response = await client.patch("/api/push/working_hours", json={"start": "09:00", "end": "17:30"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"start": "09:00", "end": "17:30"}

    await user.refresh_from_db()
    assert user.push_working_hours_start is not None
    assert user.push_working_hours_start.strftime("%H:%M") == "09:00"
    assert user.push_working_hours_end is not None
    assert user.push_working_hours_end.strftime("%H:%M") == "17:30"


@pytest.mark.asyncio
async def test_update_working_hours_accepts_cross_midnight(client: AppClient):
    await client.get_default_user()
    response = await client.patch("/api/push/working_hours", json={"start": "22:00", "end": "06:00"})
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_update_working_hours_null_pair_clears_window(client: AppClient):
    user = await client.get_default_user()
    await client.patch("/api/push/working_hours", json={"start": "09:00", "end": "17:00"})

    response = await client.patch("/api/push/working_hours", json={"start": None, "end": None})
    assert response.status_code == status.HTTP_200_OK
    assert response.json() is None

    await user.refresh_from_db()
    assert user.push_working_hours_start is None
    assert user.push_working_hours_end is None


@pytest.mark.asyncio
async def test_update_working_hours_rejects_half_set(client: AppClient):
    await client.get_default_user()
    response = await client.patch("/api/push/working_hours", json={"start": "09:00", "end": None})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_update_working_hours_rejects_equal_start_end(client: AppClient):
    await client.get_default_user()
    response = await client.patch("/api/push/working_hours", json={"start": "09:00", "end": "09:00"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_update_working_hours_requires_auth(client: AppClient):
    with client.logged_out():
        response = await client.patch("/api/push/working_hours", json={"start": None, "end": None})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
