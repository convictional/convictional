from fastapi import APIRouter, Depends

from app.helpers.users import user_avatar_url
from app.models.accounts import User
from app.routers.api.schemas import (
    ClientConfigResponse,
    CurrentUserResponse,
    FlashResponse,
)
from app.routers.dependencies import Helpers, get_current_user, get_helpers
from config.enums import FlashLevel
from config.settings import settings

router = APIRouter(tags=["current user"])


@router.get("/users/me", response_model=CurrentUserResponse, name="api_users_me_show")
async def show(
    current_user: User = Depends(get_current_user),
    helpers: Helpers = Depends(get_helpers),
) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=str(current_user.id),
        display_name=current_user.display_name,
        email=current_user.email,
        is_superuser=current_user.is_superuser,
        is_admin=current_user.is_admin,
        picture=user_avatar_url(current_user),
        client_config=ClientConfigResponse(
            klipy_api_key=settings.klipy_api_key or None,
        ),
        organization_id=str(current_user.organization_id),
        organization_name=current_user.organization.name,
        time_zone=current_user.time_zone,
        feedback_upload_url=str(helpers.url_for("attachments_upload_global")),
        # Drains (and clears) any server flashes pending in the session so the
        # SPA shell can show them once via the toaster.
        flashes=[
            FlashResponse(content=flash.content, level=FlashLevel(flash.level))
            for flash in helpers.get_flashed_messages()
        ],
    )
