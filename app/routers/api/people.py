from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.helpers.users import user_avatar_url
from app.models.accounts import User
from app.routers.api.schemas import GroupResponse, UserResponse
from app.routers.dependencies import get_current_user

router = APIRouter(tags=["people"])


class PeopleUserResponse(UserResponse):
    email: str
    bio: str | None
    is_admin: bool


class PeopleResponse(BaseModel):
    user: PeopleUserResponse
    groups: list[GroupResponse]


@router.get("/people/{user_id}", response_model=PeopleResponse)
async def api_people_show(user_id: UUID, current_user: User = Depends(get_current_user)) -> PeopleResponse:
    user = (
        current_user
        if current_user.id == user_id
        else await User.get(id=user_id, organization_id=current_user.organization_id).select_related("avatar_file")
    )
    await user.fetch_related("group_memberships__group")

    return PeopleResponse(
        user=PeopleUserResponse(
            id=str(user.id),
            display_name=user.display_name,
            picture=user_avatar_url(user),
            email=user.email,
            bio=user.bio,
            is_admin=user.is_admin,
        ),
        groups=[GroupResponse(id=str(m.group.id), name=m.group.name) for m in user.group_memberships],
    )
