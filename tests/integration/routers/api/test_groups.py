from unittest.mock import patch

import pytest
from fastapi import status

from app.jobs.content import UpdateChatContentAccessJob
from app.models.accounts import Group, GroupMember
from app.models.collaboration.workspace import Collaborator
from app.models.workspaces.chat import Chat
from config.enums import AccessAction
from infra.jobs import InlineJobs
from infra.messaging import Topic
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_group,
    create_group_member,
    create_user,
)


@pytest.mark.asyncio
async def test_groups_index(client: AppClient):
    user = await create_user(email="groups-index@convictional.com")
    other = await create_user(organization_id=user.organization_id)

    joined = await create_group(name="Engineering", organization_id=user.organization_id)
    await create_group_member(group_id=joined.id, user_id=user.id)
    await create_group_member(group_id=joined.id, user_id=other.id)

    # A soft-deleted member must not be counted or listed.
    deactivated = await create_user(organization_id=user.organization_id)
    await create_group_member(group_id=joined.id, user_id=deactivated.id)
    await deactivated.soft_delete()

    await create_group(name="Design", organization_id=user.organization_id)

    # A group in a different org must not appear.
    stranger = await create_user()
    await create_group(name="Other Org", organization_id=stranger.organization_id)

    with client.current_user_as(user):
        response = await client.get("/api/groups")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["has_more"] is False
    assert data["next_cursor"] is None

    rows = {row["name"]: row for row in data["groups"]}
    assert set(rows) == {"Engineering", "Design"}

    eng = rows["Engineering"]
    # member_count / members reflect only the 2 active members, though a deactivated member also exists in the DB.
    assert eng["member_count"] == 2
    assert len(eng["members"]) == 2
    assert eng["is_member"] is True
    assert str(deactivated.id) not in [m["user"]["id"] for m in eng["members"]]

    design = rows["Design"]
    assert design["is_member"] is False
    assert design["member_count"] == 0


@pytest.mark.asyncio
async def test_groups_index_pagination(client: AppClient):
    user = await create_user(email="groups-paginate@convictional.com")
    for i in range(60):
        await create_group(name=f"Group {i:02d}", organization_id=user.organization_id)

    with client.current_user_as(user):
        first = await client.get("/api/groups")
        first_data = first.json()
        assert first_data["has_more"] is True
        assert first_data["next_cursor"] is not None

        second = await client.get("/api/groups", params={"cursor": first_data["next_cursor"]})
        second_data = second.json()

    first_ids = {card["id"] for card in first_data["groups"]}
    second_ids = {card["id"] for card in second_data["groups"]}
    assert not (first_ids & second_ids)


@pytest.mark.asyncio
async def test_create_group(client: AppClient):
    admin = await create_user(email="group-creator@convictional.com", is_admin=True)
    member = await create_user(organization_id=admin.organization_id)

    with client.current_user_as(admin):
        response = await client.post("/api/groups", json={"name": "Platform"})
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == "Platform"
        assert data["member_count"] == 0
        assert data["is_member"] is False

    assert await Group.filter(name="Platform", organization_id=admin.organization_id).exists()

    # Non-admins cannot create.
    with client.current_user_as(member):
        forbidden = await client.post("/api/groups", json={"name": "Sneaky"})
        assert forbidden.status_code == status.HTTP_403_FORBIDDEN

    # Blank and whitespace-only names are rejected; valid names are stored trimmed.
    with client.current_user_as(admin):
        for blank in ("", "   "):
            invalid = await client.post("/api/groups", json={"name": blank})
            assert invalid.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        trimmed = await client.post("/api/groups", json={"name": "  Spacey  "})
        assert trimmed.status_code == status.HTTP_201_CREATED
        assert trimmed.json()["name"] == "Spacey"


@pytest.mark.asyncio
async def test_update_group_renames_linked_chat(client: AppClient):
    admin = await create_user(email="group-renamer@convictional.com", is_admin=True)
    member = await create_user(organization_id=admin.organization_id)
    group = await create_group(name="Old Name", organization_id=admin.organization_id)
    chat = await Chat.create(organization_id=admin.organization_id, creator_id=admin.id, group_id=group.id)

    await create_group_member(group_id=group.id, user_id=member.id)

    # A soft-deleted member must not be counted or listed on the rename response.
    deactivated = await create_user(organization_id=admin.organization_id)
    await create_group_member(group_id=group.id, user_id=deactivated.id)
    await deactivated.soft_delete()

    with client.current_user_as(admin):
        response = await client.patch(f"/api/groups/{group.id}", json={"name": "New Name"})
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["name"] == "New Name"
        assert response.json()["member_count"] == 1
        assert str(deactivated.id) not in [m["user"]["id"] for m in response.json()["members"]]

    assert (await Group.get(id=group.id)).name == "New Name"
    assert (await Chat.get(id=chat.id)).title == "New Name"

    # Non-admins cannot rename; empty body is rejected.
    with client.current_user_as(member):
        forbidden = await client.patch(f"/api/groups/{group.id}", json={"name": "Nope"})
        assert forbidden.status_code == status.HTTP_403_FORBIDDEN

    with client.current_user_as(admin):
        empty = await client.patch(f"/api/groups/{group.id}", json={})
        assert empty.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        whitespace = await client.patch(f"/api/groups/{group.id}", json={"name": "   "})
        assert whitespace.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

        trimmed = await client.patch(f"/api/groups/{group.id}", json={"name": "  Trimmed  "})
        assert trimmed.status_code == status.HTTP_200_OK
        assert trimmed.json()["name"] == "Trimmed"


@pytest.mark.asyncio
async def test_delete_group(client: AppClient):
    admin = await create_user(email="group-deleter@convictional.com", is_admin=True)
    member = await create_user(organization_id=admin.organization_id)
    group = await create_group(organization_id=admin.organization_id)

    with client.current_user_as(member):
        forbidden = await client.delete(f"/api/groups/{group.id}")
        assert forbidden.status_code == status.HTTP_403_FORBIDDEN

    with client.current_user_as(admin):
        response = await client.delete(f"/api/groups/{group.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert response.content == b""

    assert not await Group.filter(id=group.id).exists()  # soft-deleted, filtered from default manager


@pytest.mark.asyncio
async def test_group_not_in_org_returns_404(client: AppClient):
    admin = await create_user(email="group-404@convictional.com", is_admin=True)
    stranger = await create_user()
    other_group = await create_group(organization_id=stranger.organization_id)

    with client.current_user_as(admin):
        response = await client.patch(f"/api/groups/{other_group.id}", json={"name": "x"})
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_add_group_member(client: AppClient, background_jobs: InlineJobs):
    user = await create_user(email="add-member@convictional.com", is_admin=True)
    new_member = await create_user(name="New Member", organization_id=user.organization_id)
    group = await create_group(name="Engineering", organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)
    chat = await Chat.create(organization_id=user.organization_id, creator_id=user.id, group_id=group.id)

    with patch.object(Topic, "broadcast", autospec=True) as broadcast:
        with client.current_user_as(user):
            response = await client.post(f"/api/groups/{group.id}/members", json={"user_id": str(new_member.id)})
            assert response.status_code == status.HTTP_201_CREATED
            assert response.json()["user"]["display_name"] == "New Member"

    assert await GroupMember.filter(group_id=group.id, user_id=new_member.id).exists()
    assert await Collaborator.filter(workspace_id=chat.workspace_id, user_id=new_member.id).exists()

    add_jobs = background_jobs.all_completed_jobs_by_type(UpdateChatContentAccessJob)
    assert any(
        j.job_definition.action == AccessAction.ADD and j.job_definition.user_id == new_member.id for j in add_jobs
    )

    streams = {call.args[0].stream for call in broadcast.call_args_list}
    assert {"chat", "chats_index"} <= streams


@pytest.mark.asyncio
async def test_add_group_member_already_member(client: AppClient):
    user = await create_user(email="dupe-member@convictional.com")
    group = await create_group(organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)

    with client.current_user_as(user):
        response = await client.post(f"/api/groups/{group.id}/members", json={"user_id": str(user.id)})
        assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_add_group_member_authorization(client: AppClient):
    admin = await create_user(email="member-adder-admin@convictional.com", is_admin=True)
    regular = await create_user(organization_id=admin.organization_id)
    target = await create_user(organization_id=admin.organization_id)
    group = await create_group(organization_id=admin.organization_id)

    # A non-admin can add themselves (self-join).
    with client.current_user_as(regular):
        allowed = await client.post(f"/api/groups/{group.id}/members", json={"user_id": str(regular.id)})
        assert allowed.status_code == status.HTTP_201_CREATED

    # A non-admin cannot add another user.
    with client.current_user_as(regular):
        forbidden = await client.post(f"/api/groups/{group.id}/members", json={"user_id": str(target.id)})
        assert forbidden.status_code == status.HTTP_403_FORBIDDEN
    assert not await GroupMember.filter(group_id=group.id, user_id=target.id).exists()

    # An admin can add another user.
    with client.current_user_as(admin):
        allowed = await client.post(f"/api/groups/{group.id}/members", json={"user_id": str(target.id)})
        assert allowed.status_code == status.HTTP_201_CREATED
    assert await GroupMember.filter(group_id=group.id, user_id=target.id).exists()


@pytest.mark.asyncio
async def test_remove_group_member_self(client: AppClient, background_jobs: InlineJobs):
    user = await create_user(email="leave-group@convictional.com")
    other = await create_user(organization_id=user.organization_id)
    group = await create_group(organization_id=user.organization_id)
    await create_group_member(group_id=group.id, user_id=user.id)
    await create_group_member(group_id=group.id, user_id=other.id)
    chat = await Chat.create(organization_id=user.organization_id, creator_id=user.id, group_id=group.id)

    with patch.object(Topic, "broadcast", autospec=True) as broadcast:
        with client.current_user_as(user):
            response = await client.delete(f"/api/groups/{group.id}/members/{user.id}")
            assert response.status_code == status.HTTP_204_NO_CONTENT

    assert not await GroupMember.filter(group_id=group.id, user_id=user.id).exists()
    assert not await Collaborator.filter(workspace_id=chat.workspace_id, user_id=user.id).exists()

    remove_jobs = background_jobs.all_completed_jobs_by_type(UpdateChatContentAccessJob)
    assert any(
        j.job_definition.action == AccessAction.REMOVE and j.job_definition.user_id == user.id for j in remove_jobs
    )

    streams = {call.args[0].stream for call in broadcast.call_args_list}
    assert {"chat", "chats_index"} <= streams


@pytest.mark.asyncio
async def test_remove_group_member_not_member(client: AppClient):
    user = await create_user(email="leave-non-member@convictional.com")
    group = await create_group(organization_id=user.organization_id)

    with client.current_user_as(user):
        response = await client.delete(f"/api/groups/{group.id}/members/{user.id}")
        assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_remove_group_member_authorization(client: AppClient):
    admin = await create_user(email="member-remover-admin@convictional.com", is_admin=True)
    regular = await create_user(organization_id=admin.organization_id)
    target = await create_user(organization_id=admin.organization_id)
    group = await create_group(organization_id=admin.organization_id)
    await create_group_member(group_id=group.id, user_id=regular.id)
    await create_group_member(group_id=group.id, user_id=target.id)

    # A non-admin cannot remove another user.
    with client.current_user_as(regular):
        forbidden = await client.delete(f"/api/groups/{group.id}/members/{target.id}")
        assert forbidden.status_code == status.HTTP_403_FORBIDDEN
    assert await GroupMember.filter(group_id=group.id, user_id=target.id).exists()

    # An admin can remove another user.
    with client.current_user_as(admin):
        allowed = await client.delete(f"/api/groups/{group.id}/members/{target.id}")
        assert allowed.status_code == status.HTTP_204_NO_CONTENT
    assert not await GroupMember.filter(group_id=group.id, user_id=target.id).exists()
