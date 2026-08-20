import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.models.accounts import Group, GroupMember, PushSubscription, User
from app.models.collaboration.workspace import (
    SubscriptionPreference,
    workspace_registry,
)
from app.models.workspaces.posts import Post, PostGroupMute
from app.routers.api.push import subscription_to_response, working_hours_to_response
from app.routers.api.schemas import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdateRequest,
    NotificationsResponse,
    PostGroupMuteResponse,
    PostGroupMuteUpdateRequest,
    PushSettingsResponse,
)
from app.routers.dependencies import get_current_user
from config import settings
from config.enums import SubscriptionLevel

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=NotificationsResponse)
async def api_notifications_show(current_user: User = Depends(get_current_user)) -> NotificationsResponse:
    preferences, memberships, push_subscriptions, muted_group_ids_list = await asyncio.gather(
        SubscriptionPreference.defaults_for(current_user.id),
        GroupMember.filter(user_id=current_user.id).prefetch_related("group").all(),
        PushSubscription.filter(user_id=current_user.id).order_by("-created_at"),
        PostGroupMute.filter(user_id=current_user.id).values_list("group_id", flat=True),
    )

    preference_responses = [
        NotificationPreferenceResponse(
            resource_type=preference.resource_type,
            default_level=preference.default_level,
        )
        for preference in sorted(preferences, key=lambda p: p.resource_type)
    ]

    user_groups = sorted(
        (m.group for m in memberships if not m.group.is_deleted),
        key=lambda g: g.name.lower(),
    )
    muted_group_ids = set(muted_group_ids_list)

    post_group_mutes = [
        PostGroupMuteResponse(
            group_id=str(group.id),
            group_name=group.name,
            muted=group.id in muted_group_ids,
        )
        for group in user_groups
    ]

    push = PushSettingsResponse(
        devices=[subscription_to_response(sub) for sub in push_subscriptions],
        vapid_public_key=settings.vapid_public_key,
        working_hours=working_hours_to_response(current_user),
    )

    return NotificationsResponse(
        preferences=preference_responses,
        post_group_mutes=post_group_mutes,
        push=push,
    )


def _resolve_resource_type(resource_type: str) -> str:
    # Accept lowercase URL params ("post") and resolve to the registry key ("Post").
    for registered in workspace_registry.keys():
        if registered.lower() == resource_type.lower():
            return registered
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource type")


@router.patch("/notifications/{resource_type}", response_model=NotificationPreferenceResponse)
async def api_notification_preference_update(
    resource_type: str,
    body: NotificationPreferenceUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> NotificationPreferenceResponse:
    canonical_type = _resolve_resource_type(resource_type)

    if body.default_level == SubscriptionLevel.BROADCASTS and canonical_type != Post.record_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="broadcasts level is only valid for Post",
        )

    preference = await SubscriptionPreference.get_or_init(subscriber_id=current_user.id, resource_type=canonical_type)
    preference.default_level = body.default_level
    await preference.save()

    return NotificationPreferenceResponse(
        resource_type=canonical_type,
        default_level=preference.default_level,
    )


@router.patch("/notifications/posts/groups/{group_id}/mute", response_model=PostGroupMuteResponse)
async def api_post_group_mute_update(
    group_id: UUID,
    body: PostGroupMuteUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> PostGroupMuteResponse:
    group = await Group.get_or_none(id=group_id, organization_id=current_user.organization_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    # Mute only makes semantic sense for members — the resolver intersects mutes with
    # group_member_ids, so a non-member mute row would have no effect. Reject the write
    # outright rather than silently inserting a phantom row. Existing rows survive a
    # leave-then-rejoin so the user's mute preference is preserved across cycles.
    if not await GroupMember.filter(group_id=group.id, user_id=current_user.id).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")

    if body.muted:
        await PostGroupMute.mute(user_id=current_user.id, group_id=group.id)
    else:
        await PostGroupMute.unmute(user_id=current_user.id, group_id=group.id)

    return PostGroupMuteResponse(group_id=str(group.id), group_name=group.name, muted=body.muted)
