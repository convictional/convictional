import pytest
from fastapi import status

from app.jobs.content import ContentIndexingJob
from app.models.accounts import User
from infra.jobs import InlineJobs
from infra.storage import FileReference
from tests.helpers.app import AppClient
from tests.helpers.images import png_bytes


@pytest.mark.asyncio
async def test_profile_show(client: AppClient):
    user = await client.get_default_user()
    user.name = "Alex Doe"
    user.bio = "Engineer"
    user.time_zone = "America/New_York"
    await user.save()

    response = await client.get("/api/users/me/profile")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body["name"] == "Alex Doe"
    assert body["bio"] == "Engineer"
    assert body["time_zone"] == "America/New_York"
    assert body["has_custom_avatar"] is False


@pytest.mark.asyncio
async def test_profile_update_fields(client: AppClient, background_jobs: InlineJobs):
    user = await client.get_default_user()

    response = await client.patch("/api/users/me/profile", json={"name": "  Alex Doe  ", "bio": "Updated bio"})
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["name"] == "Alex Doe"  # trimmed
    assert body["bio"] == "Updated bio"

    user = await User.get(id=user.id)
    assert user.name == "Alex Doe"
    assert user.bio == "Updated bio"

    # A profile edit reindexes the user's searchable content.
    assert any(isinstance(job.job_definition, ContentIndexingJob) for job in background_jobs.completed)

    response = await client.patch("/api/users/me/profile", json={"time_zone": "Europe/London"})
    assert response.status_code == status.HTTP_200_OK
    user = await User.get(id=user.id)
    assert user.time_zone == "Europe/London"
    # Updating only the timezone leaves the name untouched.
    assert user.name == "Alex Doe"


@pytest.mark.asyncio
async def test_profile_update_rejects_invalid_input(client: AppClient):
    user = await client.get_default_user()
    user.name = "Alex Doe"
    user.time_zone = "Europe/London"
    await user.save()

    # Empty body — no recognised fields.
    assert (await client.patch("/api/users/me/profile", json={})).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    invalid_names = [
        "   ",  # blank after trim
        "x" * 51,  # too long
        "Alex\r\nBcc: evil@example.com",  # control chars (header injection)
        "​‌",  # zero-width only
        "🎉 Party",  # emoji
        "Владимир",  # non-Latin script
        "𝓯𝓪𝓷𝓬𝔂",  # decorative unicode
    ]
    for name in invalid_names:
        response = await client.patch("/api/users/me/profile", json={"name": name})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, f"expected 422 for {name!r}"

    invalid_zones = ["Not/A_Real_Zone", "../../etc/passwd", "/absolute/path", "x/../y"]
    for zone in invalid_zones:
        response = await client.patch("/api/users/me/profile", json={"time_zone": zone})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, f"expected 422 for {zone!r}"

    # Nothing persisted from the rejected requests.
    user = await User.get(id=user.id)
    assert user.name == "Alex Doe"
    assert user.time_zone == "Europe/London"


@pytest.mark.asyncio
async def test_avatar_upload_replace_and_delete(client: AppClient):
    user = await client.get_default_user()
    user.oauth_picture = "https://oauth.example/avatar.jpg"
    await user.save()

    response = await client.post(
        "/api/users/me/profile/avatar", files={"avatar": ("me.png", png_bytes(), "image/png")}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["has_custom_avatar"] is True
    first_picture = response.json()["picture"]

    user = await User.get(id=user.id)
    first_file_id = user.avatar_file_id
    assert first_file_id is not None
    first_file = await FileReference.get(id=first_file_id)
    assert first_file.content_type == "image/webp"

    # Replacing swaps in a new file, and the picture URL changes with it so a
    # cached avatar at the otherwise-stable path can't linger after a replace.
    response = await client.post(
        "/api/users/me/profile/avatar", files={"avatar": ("me2.png", png_bytes(300, 400), "image/png")}
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["picture"] != first_picture
    user = await User.get(id=user.id)
    assert user.avatar_file_id is not None
    assert user.avatar_file_id != first_file_id

    # Delete clears it back to the oauth fallback.
    response = await client.delete("/api/users/me/profile/avatar")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""
    user = await User.get(id=user.id)
    assert user.avatar_file_id is None
    assert user.oauth_picture == "https://oauth.example/avatar.jpg"

    # Delete is idempotent when nothing is set.
    assert (await client.delete("/api/users/me/profile/avatar")).status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_avatar_upload_rejects_invalid_inputs(client: AppClient):
    user = await client.get_default_user()

    invalid_files = [
        ("animated.gif", b"GIF89a", "image/gif"),
        ("notes.txt", b"plain text", "text/plain"),
        ("broken.png", b"not really png bytes", "image/png"),
    ]
    for upload in invalid_files:
        response = await client.post("/api/users/me/profile/avatar", files={"avatar": upload})
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT, f"expected 422 for {upload[0]}"

    user = await User.get(id=user.id)
    assert user.avatar_file_id is None
