from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.models.accounts import (
    PushSubscription,
    PushSubscriptionLimitError,
    PushSubscriptionUserCollisionError,
    User,
)
from app.routers.api.schemas import (
    ApnsPushSubscriptionCreateRequest,
    PushSubscriptionCreateRequest,
    PushSubscriptionListResponse,
    PushSubscriptionResponse,
    PushWorkingHoursResponse,
    PushWorkingHoursUpdateRequest,
    WebPushSubscriptionCreateRequest,
)
from app.routers.dependencies import get_current_user

router = APIRouter(tags=["push subscriptions"])


def _endpoint_suffix(endpoint: str) -> str:
    return f"…{endpoint[-12:]}" if len(endpoint) > 12 else f"…{endpoint}"


def working_hours_to_response(user: User) -> PushWorkingHoursResponse | None:
    if user.push_working_hours_start is None or user.push_working_hours_end is None:
        return None
    return PushWorkingHoursResponse(start=user.push_working_hours_start, end=user.push_working_hours_end)


def subscription_to_response(subscription: PushSubscription) -> PushSubscriptionResponse:
    return PushSubscriptionResponse(
        id=str(subscription.id),
        protocol=subscription.protocol,
        endpoint_suffix=_endpoint_suffix(subscription.endpoint),
        user_agent=subscription.user_agent,
        platform=subscription.platform,
        created_at=subscription.created_at,
    )


async def _register(response: Response, **register_kwargs: Any) -> PushSubscriptionResponse:
    """Shared body for the web-push and native register endpoints. Maps
    `register_for_user` exceptions to the wire-level status codes and flips
    the response from 201 to 200 when the call refreshed an existing row."""
    try:
        subscription, created = await PushSubscription.register_for_user(**register_kwargs)
    except PushSubscriptionLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many push subscriptions (limit {exc.limit}).",
        )
    except PushSubscriptionUserCollisionError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Subscription state changed; retry.",
        )
    if not created:
        response.status_code = status.HTTP_200_OK
    return subscription_to_response(subscription)


@router.get("/push/subscriptions", response_model=PushSubscriptionListResponse)
async def api_push_subscriptions_list(
    current_user: User = Depends(get_current_user),
) -> PushSubscriptionListResponse:
    subscriptions = await PushSubscription.filter(user_id=current_user.id).order_by("-created_at")
    return PushSubscriptionListResponse(
        subscriptions=[subscription_to_response(sub) for sub in subscriptions],
    )


# CSRF-exempt at the middleware: authenticated by session cookie, intrinsically
# per-user idempotent (dedupe on endpoint), and rate-limited. Load-bearing for
# the SW pushsubscriptionchange handler, which has no DOM and therefore no way
# to read the CSRF cookie.
@router.post(
    "/push/subscriptions",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def api_push_subscriptions_create(
    body: PushSubscriptionCreateRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> PushSubscriptionResponse:
    if isinstance(body, ApnsPushSubscriptionCreateRequest):
        return await _register(
            response,
            user_id=current_user.id,
            endpoint=body.device_token,
            protocol=body.protocol,
            user_agent=body.user_agent,
        )
    # WebPushSubscriptionCreateRequest — default branch covers the legacy
    # service-worker payload (no `protocol` field) via the schema's
    # discriminator fallback.
    assert isinstance(body, WebPushSubscriptionCreateRequest)
    return await _register(
        response,
        user_id=current_user.id,
        endpoint=body.endpoint,
        protocol=body.protocol,
        p256dh_key=body.keys.p256dh,
        auth_key=body.keys.auth,
        user_agent=body.user_agent,
        rotated_from_endpoint=body.rotated_from,
    )


@router.patch("/push/working_hours", response_model=PushWorkingHoursResponse | None)
async def api_push_working_hours_update(
    body: PushWorkingHoursUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> PushWorkingHoursResponse | None:
    await current_user.set_push_working_hours(body.start, body.end)
    return working_hours_to_response(current_user)


@router.delete("/push/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_push_subscriptions_delete(
    subscription_id: UUID,
    current_user: User = Depends(get_current_user),
) -> None:
    subscription = await PushSubscription.filter(id=subscription_id, user_id=current_user.id).first()
    # 404, not 403, when the row exists but belongs to a different user: 403
    # leaks the existence of the id to a probing attacker.
    if not subscription:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Push subscription not found")
    if not subscription.is_deleted:
        await subscription.soft_delete()
