import asyncio
import io

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.jobs.content import ContentIndexingJob
from app.models.accounts import (
    AVATAR_MAX_UPLOAD_BYTES,
    AVATAR_OUTPUT_FILENAME,
    AVATAR_OUTPUT_MIME,
    User,
    process_avatar_image,
)
from app.routers.api.schemas import ProfileResponse, ProfileUpdateRequest
from app.routers.api.serializers import profile_response
from app.routers.dependencies import get_current_user
from infra.db import transaction
from infra.jobs import enqueue_job
from infra.storage import store_file
from lib.images import ImageProcessingError

# /api/users/me/profile is the current user's *editable* profile sub-resource:
# public identity (name, bio, avatar) plus timezone. It sits under /api/users/me/
# alongside the other current-user sub-resources (.../calendar).
# The parent /api/users/me is a lean read-only session/identity projection for
# island bootstrap and surfaces a couple of the same fields (picture, time_zone)
# for the hot path — this sub-resource is the editable source of truth. The
# cross-user read of someone's public profile is /api/people/{id}, which omits
# timezone, keeping it private. Guardrails: no write path on /api/users/me; no
# private per-user settings here (own domain resource, or a /api/users/me/preferences
# namespace once a second non-domain preference exists); don't add timezone to /api/people.
router = APIRouter(tags=["profile"])


@router.get("/users/me/profile", response_model=ProfileResponse)
async def api_profile_show(current_user: User = Depends(get_current_user)) -> ProfileResponse:
    return profile_response(current_user)


@router.patch("/users/me/profile", response_model=ProfileResponse)
async def api_profile_update(
    body: ProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    # name/time_zone are already normalized and validated by ProfileUpdateRequest's
    # field validators (invalid input → 422). An explicit null is treated as "no
    # change" — these fields aren't clearable via this API.
    async with transaction() as connection:
        if body.name is not None:
            current_user.name = body.name
        if body.bio is not None:
            current_user.bio = body.bio
        if body.time_zone is not None:
            current_user.time_zone = body.time_zone

        await current_user.save(using_db=connection)
        await enqueue_job(ContentIndexingJob.from_model(current_user.organization_id, current_user), connection)

    return profile_response(current_user)


@router.post("/users/me/profile/avatar", response_model=ProfileResponse)
async def api_profile_avatar_upload(
    avatar: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
) -> ProfileResponse:
    # Read one byte past the cap so process_avatar_image can reject oversized
    # uploads without pulling the whole file into memory.
    raw = await avatar.read(AVATAR_MAX_UPLOAD_BYTES + 1)
    try:
        processed = await asyncio.to_thread(process_avatar_image, raw, avatar.content_type)
    except ImageProcessingError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    file_reference = await store_file(io.BytesIO(processed), AVATAR_OUTPUT_FILENAME, AVATAR_OUTPUT_MIME)
    async with transaction() as connection:
        current_user.avatar_file_id = file_reference.id
        await current_user.save(using_db=connection)

    return profile_response(current_user)


@router.delete("/users/me/profile/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def api_profile_avatar_delete(current_user: User = Depends(get_current_user)) -> Response:
    if current_user.avatar_file_id is not None:
        async with transaction() as connection:
            current_user.avatar_file_id = None
            await current_user.save(using_db=connection)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
