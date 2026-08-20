from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.jobs.mailers import UserInvitedEmailJob
from app.models.accounts import Group, GroupMember, Invite, Organization, User
from app.routers.api.schemas import (
    OrganizationMembersResponse,
    OrganizationResponse,
    OrganizationUpdateRequest,
    OrganizationUserInviteRequest,
    OrganizationUserResponse,
    OrganizationUsersListResponse,
    OrganizationUserUpdateRequest,
)
from app.routers.api.serializers import group_response, organization_user_response, user_response
from app.routers.dependencies import (
    Channel,
    get_admin_user,
    get_all_org_groups,
    get_current_user,
    get_org_users,
    handle_stream,
)
from config import logger
from config.enums import ChannelEventAction, ChannelEventResource
from infra.jobs import enqueue_job

router = APIRouter(tags=["organization"])


def _organization_response(organization: Organization, current_user: User) -> OrganizationResponse:
    # system_prompt is only *set* on the model for superusers, so response_model_exclude_unset
    # omits the key entirely for everyone else (rather than returning a misleading null).
    if current_user.is_superuser:
        return OrganizationResponse(
            id=str(organization.id),
            name=organization.name,
            system_prompt=organization.system_prompt,
        )
    return OrganizationResponse(id=str(organization.id), name=organization.name)


# Org settings are admin-only. (/organization/members below stays open to all users — many
# islands need the member list for @mentions, ownership, etc.)
@router.get("/organization", response_model=OrganizationResponse, response_model_exclude_unset=True)
async def api_organization_show(current_user: User = Depends(get_admin_user)):
    organization = await Organization.get(id=current_user.organization_id)
    return _organization_response(organization, current_user)


@router.patch("/organization", response_model=OrganizationResponse, response_model_exclude_unset=True)
async def api_organization_update(
    body: OrganizationUpdateRequest,
    current_user: User = Depends(get_admin_user),
):
    # system_prompt is the superuser-only "Support Fields" value — only superusers may set it.
    if "system_prompt" in body.model_fields_set and not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can edit the system prompt.",
        )

    organization = await Organization.get(id=current_user.organization_id)
    if body.name is not None:
        organization.name = body.name
    if "system_prompt" in body.model_fields_set:
        organization.system_prompt = body.system_prompt
    await organization.save()

    return _organization_response(organization, current_user)


async def _organization_user_detail(user_id: UUID, organization_id: UUID) -> OrganizationUserResponse:
    # Refetch fresh state for a single member after a mutation. The model's manager includes
    # soft-deleted rows (accounts.py overrides it), so this resolves deactivated members too.
    user = await User.get(id=user_id, organization_id=organization_id)
    memberships = await GroupMember.filter(user_id=user.id).prefetch_related("group").all()
    return organization_user_response(user, [m.group for m in memberships])


@router.get("/organization/users", response_model=OrganizationUsersListResponse)
async def api_organization_users_index(current_user: User = Depends(get_admin_user)):
    organization_id = current_user.organization_id
    users = await User.filter(User.filters.by_organization(organization_id)).all()

    user_ids = [u.id for u in users]
    memberships = await GroupMember.filter(user_id__in=user_ids).prefetch_related("group").all()
    groups_by_user: dict[UUID, list[Group]] = {}
    for membership in memberships:
        groups_by_user.setdefault(membership.user_id, []).append(membership.group)

    # Active first, then deactivated, each alphabetised by email. The `active` flag lets the
    # client split the two tabs without separate requests.
    ordered = sorted(users, key=lambda u: (u.is_deleted, u.email))

    return OrganizationUsersListResponse(
        users=[organization_user_response(user, groups_by_user.get(user.id, [])) for user in ordered],
    )


@router.post("/organization/users", response_model=OrganizationUserResponse, status_code=status.HTTP_201_CREATED)
async def api_organization_users_create(
    body: OrganizationUserInviteRequest,
    response: Response,
    current_user: User = Depends(get_admin_user),
):
    invite = Invite(inviter=current_user, email=body.email)
    await invite.process()
    if not invite.success or not invite.invited:
        # Semantic rejection (banned domain, belongs to another org) — not malformed input.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=invite.error or "User could not be invited.",
        )

    invited = invite.invited
    await enqueue_job(UserInvitedEmailJob(user_id=invited.id, note=body.note))
    # No "new user" team notification here: an invite pre-creates the account, so that fires on the
    # invitee's first login instead.
    if invite.is_existing_user:
        # Re-inviting an existing member refreshes (and restores) rather than creating — 200, not 201.
        response.status_code = status.HTTP_200_OK

    return await _organization_user_detail(invited.id, current_user.organization_id)


@router.patch("/organization/users/{user_id}", response_model=OrganizationUserResponse)
async def api_organization_users_update(
    user_id: UUID,
    body: OrganizationUserUpdateRequest,
    current_user: User = Depends(get_admin_user),
):
    # An admin can't demote or deactivate their own account through this endpoint.
    if user_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="You can't modify your own membership.",
        )

    user = await User.get(id=user_id, organization_id=current_user.organization_id)

    if body.is_admin is not None:
        user.is_admin = body.is_admin
        await user.save(update_fields=["is_admin"])

    # deactivate/reactivate own the soft-delete + logout + roster broadcast, and no-op cleanly when
    # the member is already in the requested state.
    if body.active is True:
        await user.reactivate()
    elif body.active is False:
        await user.deactivate()

    return await _organization_user_detail(user.id, current_user.organization_id)


@router.get("/organization/members", response_model=OrganizationMembersResponse)
async def api_organization_members(
    current_user: User = Depends(get_current_user),
    organization_users: list[User] = Depends(get_org_users),
    organization_groups: list[Group] = Depends(get_all_org_groups),
):
    return OrganizationMembersResponse(
        users=[user_response(u) for u in organization_users],
        groups=[group_response(g) for g in organization_groups],
    )


# Producer payloads that mean "the org's user or group list changed". The client
# refetches the full payload regardless of which one fired, so they all collapse to
# a single UPDATED event. Listed explicitly so an unrecognised payload surfaces as a
# no-op anomaly rather than a misleading event.
_MEMBERSHIP_CHANGE_KEYS = {
    "added_user_id",
    "removed_user_id",
    "group_added_id",
    "group_removed_id",
    "group_updated_id",
}


@handle_stream("organization_members")
async def handle_organization_members_json(channel: Channel, **data):
    if _MEMBERSHIP_CHANGE_KEYS.isdisjoint(data):
        logger.warning("Unrecognised organization_members broadcast payload keys: %s", sorted(data))
        return
    await channel.send_event(ChannelEventResource.ORGANIZATION_MEMBERS, ChannelEventAction.UPDATED)
