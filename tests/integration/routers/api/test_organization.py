import pytest
from fastapi import status

from app.jobs.mailers import SendNewUserEmailJob, UserInvitedEmailJob
from app.models.accounts import User
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import create_group, create_group_member, create_superuser, create_user


@pytest.mark.asyncio
async def test_organization_members(client: AppClient):
    user = await client.get_default_user()
    other_user = await create_user(organization_id=user.organization_id)
    group = await create_group(organization_id=user.organization_id, name="Engineering")

    response = await client.get("/api/organization/members")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    user_ids = {u["id"] for u in data["users"]}
    assert str(user.id) in user_ids
    assert str(other_user.id) in user_ids

    groups_by_id = {g["id"]: g for g in data["groups"]}
    assert str(group.id) in groups_by_id
    assert groups_by_id[str(group.id)]["name"] == "Engineering"

    # Verify shape
    sample_user = next(u for u in data["users"] if u["id"] == str(user.id))
    assert "display_name" in sample_user
    assert "picture" in sample_user


@pytest.mark.asyncio
async def test_organization_show_and_update_as_superuser(client: AppClient):
    superuser = await create_superuser(is_admin=True)
    client.current_user = superuser

    response = await client.get("/api/organization")
    assert response.status_code == status.HTTP_200_OK
    assert {"id", "name", "system_prompt"} <= set(response.json())

    response = await client.patch("/api/organization", json={"name": "Acme", "system_prompt": "Be concise."})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["name"] == "Acme"
    assert data["system_prompt"] == "Be concise."

    # PATCH bodies that can't produce a change are rejected (not silent 200 no-ops):
    # an empty body, or name=null (the handler never clears name).
    assert (await client.patch("/api/organization", json={})).status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    response = await client.patch("/api/organization", json={"name": None})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_organization_system_prompt_is_superuser_only(client: AppClient):
    # No address is listed in settings.superuser_emails, so this admin is not a superuser.
    admin = await create_user(is_admin=True)
    client.current_user = admin

    # Non-superusers never see the system prompt — the key is omitted entirely (not null).
    response = await client.get("/api/organization")
    assert response.status_code == status.HTTP_200_OK
    assert "system_prompt" not in response.json()

    # ...and cannot edit it — only superusers may set system_prompt.
    response = await client.patch("/api/organization", json={"system_prompt": "sneaky"})
    assert response.status_code == status.HTTP_403_FORBIDDEN

    # But editing the name still works.
    response = await client.patch("/api/organization", json={"name": "Renamed"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["name"] == "Renamed"


@pytest.mark.asyncio
async def test_organization_endpoints_require_admin(client: AppClient):
    member = await create_user(is_admin=False)
    client.current_user = member

    assert (await client.get("/api/organization")).status_code == status.HTTP_403_FORBIDDEN
    response = await client.patch("/api/organization", json={"name": "Nope"})
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_organization_users_index(client: AppClient):
    admin = await create_user(is_admin=True)
    client.current_user = admin
    org_id = admin.organization_id

    member = await create_user(name="Member", organization_id=org_id, email="member@example.com")
    deactivated = await create_user(name="Gone", organization_id=org_id, email="gone@example.com")
    await deactivated.deactivate()

    group = await create_group(name="Engineering", organization_id=org_id)
    await create_group_member(group_id=group.id, user_id=member.id)

    response = await client.get("/api/organization/users")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Envelope present.
    assert data["has_more"] is False and data["next_cursor"] is None

    users_by_id = {u["id"]: u for u in data["users"]}
    assert {str(admin.id), str(member.id), str(deactivated.id)} <= set(users_by_id)

    member_payload = users_by_id[str(member.id)]
    assert member_payload["active"] is True
    assert member_payload["email"] == "member@example.com"
    assert {"display_name", "picture", "is_admin", "bio", "groups"} <= set(member_payload)
    # The top goal is its own resource (/api/users/{id}/top_goal), not embedded here.
    assert "top_goal" not in member_payload
    assert [g["name"] for g in member_payload["groups"]] == ["Engineering"]

    # Deactivated members are present but flagged so the client can tab them separately.
    assert users_by_id[str(deactivated.id)]["active"] is False


@pytest.mark.asyncio
async def test_organization_users_invite(client: AppClient, email_delivery, background_jobs: InlineJobs):
    admin = await create_user(is_admin=True)
    client.current_user = admin

    response = await client.post("/api/organization/users", json={"email": "newbie@example.com", "note": "welcome"})
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["email"] == "newbie@example.com"
    assert body["active"] is True
    assert await User.filter(email="newbie@example.com", organization_id=admin.organization_id).exists()

    # Inviting a new user enqueues the invite email job and delivers an invite email.
    assert background_jobs.has_completed_job(UserInvitedEmailJob, count=1)
    emails = email_delivery.by_recipient("newbie@example.com")
    assert any("invited" in email.subject for email in emails)

    # The internal "new user" notification must NOT fire at invite time — only once the invitee logs in.
    assert background_jobs.has_completed_job(SendNewUserEmailJob, count=0)

    # Re-inviting an existing member refreshes rather than creates → 200, not 201.
    response = await client.post("/api/organization/users", json={"email": "newbie@example.com"})
    assert response.status_code == status.HTTP_200_OK

    # Inviting someone who already belongs to another org is a semantic rejection, not malformed input.
    await create_user(email="elsewhere@example.com")  # different org (no organization_id)
    response = await client.post("/api/organization/users", json={"email": "elsewhere@example.com"})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # An over-long note is rejected (bounded before it reaches the email job).
    response = await client.post("/api/organization/users", json={"email": "long@example.com", "note": "x" * 1001})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_organization_users_update(client: AppClient):
    admin = await create_user(is_admin=True)
    client.current_user = admin
    member = await create_user(organization_id=admin.organization_id, email="m@example.com")

    # Promote to admin.
    response = await client.patch(f"/api/organization/users/{member.id}", json={"is_admin": True})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["is_admin"] is True

    # Deactivate soft-deletes the member and logs them out.
    response = await client.patch(f"/api/organization/users/{member.id}", json={"active": False})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["active"] is False
    await member.refresh_from_db()
    assert member.is_deleted and member.last_logout_at is not None
    deactivated_at = member.deleted_at

    # A no-op toggle (already deactivated) is idempotent: still 200, and deleted_at isn't re-stamped.
    response = await client.patch(f"/api/organization/users/{member.id}", json={"active": False})
    assert response.status_code == status.HTTP_200_OK
    await member.refresh_from_db()
    assert member.deleted_at == deactivated_at

    # Restore.
    response = await client.patch(f"/api/organization/users/{member.id}", json={"active": True})
    assert response.json()["active"] is True
    await member.refresh_from_db()
    assert not member.is_deleted

    # Empty body has no actionable field.
    response = await client.patch(f"/api/organization/users/{member.id}", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Admins can't modify their own membership.
    response = await client.patch(f"/api/organization/users/{admin.id}", json={"is_admin": False})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_organization_users_require_admin(client: AppClient):
    member = await create_user(is_admin=False)
    client.current_user = member
    other = await create_user(organization_id=member.organization_id, email="other@example.com")

    assert (await client.get("/api/organization/users")).status_code == status.HTTP_403_FORBIDDEN
    assert (
        await client.post("/api/organization/users", json={"email": "x@example.com"})
    ).status_code == status.HTTP_403_FORBIDDEN
    assert (
        await client.patch(f"/api/organization/users/{other.id}", json={"is_admin": True})
    ).status_code == status.HTTP_403_FORBIDDEN
