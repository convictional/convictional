from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from tortoise import BaseDBAsyncClient

from app.jobs.content import UpdateChatContentAccessJob
from app.models.accounts import Group, User
from app.models.workspaces.chat import Chat
from app.routers.api.schemas import PaginatedResponse, UserResponse
from app.routers.api.serializers import user_response
from app.routers.dependencies import get_admin_user, get_current_user
from config.enums import AccessAction
from infra.db import Pagination, after_commit, transaction
from infra.jobs import enqueue_job
from infra.messaging import Topic

router = APIRouter(tags=["groups"])


#
# Dependencies
#


async def get_group(group_id: UUID, current_user: User = Depends(get_current_user)) -> Group:
    return await Group.get(
        id=group_id,
        organization_id=current_user.organization_id,
    ).prefetch_related(Group.active_members_prefetch())


async def get_group_for_admin(group_id: UUID, admin_user: User = Depends(get_admin_user)) -> Group:
    return await Group.get(id=group_id, organization_id=admin_user.organization_id).prefetch_related(
        Group.active_members_prefetch()
    )


#
# Response models
#


class GroupMemberResponse(BaseModel):
    id: str
    user: UserResponse


class GroupRowResponse(BaseModel):
    id: str
    name: str
    member_count: int
    members: list[GroupMemberResponse]  # active members; excludes soft-deleted users
    is_member: bool  # for current_user — drives Join/Leave


class GroupListResponse(PaginatedResponse):
    groups: list[GroupRowResponse]


#
# Request models
#


class AddGroupMemberRequest(BaseModel):
    user_id: UUID


class GroupNameRequest(BaseModel):
    name: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("name must not be blank")
        return stripped


#
# Serialization
#


def _group_row_response(group: Group, current_user: User) -> GroupRowResponse:
    members = [GroupMemberResponse(id=str(member.id), user=user_response(member.user)) for member in group.members]
    return GroupRowResponse(
        id=str(group.id),
        name=group.name,
        member_count=len(members),
        members=members,
        is_member=group.is_member(current_user.id),
    )


async def _broadcast_membership_change(group: Group, user_id: UUID, action: AccessAction) -> None:
    chat = await Chat.filter(group_id=group.id).first()
    if not chat:
        return

    await enqueue_job(UpdateChatContentAccessJob(chat_id=chat.id, user_id=user_id, action=action, unique=True))

    collaborator_field = "collaborator_added" if action == AccessAction.ADD else "collaborator_removed"
    await Topic("chat", chat_id=chat.id, workspace_id=chat.workspace_id).broadcast(
        **{collaborator_field: str(user_id)}
    )
    await Topic("chats_index", organization_id=group.organization_id).broadcast()


#
# Endpoints
#


@router.get("/groups", response_model=GroupListResponse)
async def api_groups_index(current_user: User = Depends(get_current_user), cursor: str | None = Query(None)):
    queryset = Group.filter(Group.filters.by_organization(current_user.organization_id)).prefetch_related(
        Group.active_members_prefetch()
    )
    pagination = await Pagination.create(Group, cursor=cursor, queryset=queryset)

    return GroupListResponse(
        groups=[_group_row_response(group, current_user) for group in pagination.results],
        next_cursor=pagination.next_cursor,
        has_more=pagination.has_next,
    )


@router.post("/groups", response_model=GroupRowResponse, status_code=status.HTTP_201_CREATED)
async def api_create_group(body: GroupNameRequest, admin_user: User = Depends(get_admin_user)):
    # A freshly created group has no members, and the creator is not auto-joined,
    # so build the row directly rather than re-fetching to load empty relations.
    group = await Group.create(name=body.name, organization_id=admin_user.organization_id)

    # Broadcast after the awaited mutation (no surrounding transaction here) so other
    # sessions see the new group in the shared org-members store without a reload.
    await Topic("organization_members", organization_id=admin_user.organization_id).broadcast(
        group_added_id=str(group.id)
    )

    return GroupRowResponse(
        id=str(group.id),
        name=group.name,
        member_count=0,
        members=[],
        is_member=False,
    )


@router.patch("/groups/{group_id}", response_model=GroupRowResponse)
async def api_update_group(
    body: GroupNameRequest, group: Group = Depends(get_group_for_admin), admin_user: User = Depends(get_admin_user)
):
    async with transaction() as connection:
        group.name = body.name
        await group.save(using_db=connection)
        await Chat.filter(group_id=group.id).using_db(connection).update(title=body.name)

        async def broadcast(using_db: BaseDBAsyncClient | None):
            await Topic("organization_members", organization_id=group.organization_id).broadcast(
                group_updated_id=str(group.id)
            )

        await after_commit(broadcast)

    return _group_row_response(group, admin_user)


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_delete_group(
    group: Group = Depends(get_group_for_admin),
):
    await group.soft_delete()
    await Topic("organization_members", organization_id=group.organization_id).broadcast(
        group_removed_id=str(group.id)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/groups/{group_id}/members", response_model=GroupMemberResponse, status_code=status.HTTP_201_CREATED)
async def api_add_group_member(
    body: AddGroupMemberRequest, group: Group = Depends(get_group), current_user: User = Depends(get_current_user)
):
    if body.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    user_to_add = await User.active.get(id=body.user_id, organization_id=current_user.organization_id)

    try:
        member = await group.add_member(user_to_add)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None

    await _broadcast_membership_change(group, user_to_add.id, AccessAction.ADD)

    return GroupMemberResponse(id=str(member.id), user=user_response(user_to_add))


@router.delete("/groups/{group_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def api_remove_group_member(
    user_id: UUID, group: Group = Depends(get_group), current_user: User = Depends(get_current_user)
):
    if user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    user_to_remove = await User.active.get(id=user_id, organization_id=current_user.organization_id)

    try:
        await group.remove_member(user_to_remove)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from None

    await _broadcast_membership_change(group, user_to_remove.id, AccessAction.REMOVE)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
