import pytest
from fastapi import status

from app.models.accounts import User
from app.models.collaboration.workspace import Collaborator, Visit, Workspace
from config.enums import CollaboratorStatus, EventAction, Sharing
from infra.email import FakeDelivery
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_collaborator,
    create_email_thread,
    create_event,
    create_goal,
    create_meeting,
    create_user,
)


@pytest.mark.asyncio
async def test_get_collaborators_returns_full_state(client: AppClient):
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Clams", organization_id=creator.organization_id)
    bob = await create_user(name="Bob Whales", organization_id=creator.organization_id)
    meeting = await create_meeting(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=meeting.workspace_id, user_id=alice.id)
    await Collaborator.create(workspace_id=meeting.workspace_id, user_id=bob.id, status=CollaboratorStatus.PENDING)

    response = await client.get(f"/api/workspaces/{meeting.workspace_id}/collaborators")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    approved_user_ids = {c["user"]["id"] for c in data["collaborators"]}
    assert approved_user_ids == {str(creator.id), str(alice.id)}
    for c in data["collaborators"]:
        assert "display_name" in c["user"]
        assert "picture" in c["user"]
        assert "is_removable" in c

    assert [c["user"]["id"] for c in data["pending"]] == [str(bob.id)]
    assert data["pending"][0]["status"] == "pending"

    # "Everyone else" (org members not yet collaborators) is now derived
    # client-side from the organizationMembers store, so the response no longer
    # carries an available_users list.
    assert "available_users" not in data

    assert data["present_user_ids"] == []


@pytest.mark.asyncio
async def test_collaborators_expose_visit_derived_view_state(client: AppClient):
    creator = await client.get_default_user()
    unviewed_user = await create_user(name="Never Seen", organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=goal.workspace_id, user_id=unviewed_user.id)

    workspace = await Workspace.get(id=goal.workspace_id)
    event = await create_event(workspace, creator_id=creator.id, action=EventAction.GOAL_COMMENTED)
    await Visit.record(user_id=creator.id, workspace_id=workspace.id, last_event_id=event.id)

    response = await client.get(f"/api/workspaces/{goal.workspace_id}/collaborators")
    assert response.status_code == status.HTTP_200_OK
    by_user = {c["user"]["id"]: c["view_state"] for c in response.json()["collaborators"]}

    viewed = by_user[str(creator.id)]
    assert viewed["viewed"] is True
    assert viewed["last_viewed_at"] is not None
    assert viewed["last_viewed_event_id"] == str(event.id)

    # A collaborator who never visited is supported-but-unviewed, not null.
    assert by_user[str(unviewed_user.id)] == {
        "viewed": False,
        "last_viewed_at": None,
        "last_viewed_event_id": None,
    }


@pytest.mark.asyncio
async def test_current_user_view_state_returned_for_non_collaborator_viewer(client: AppClient):
    """An org member viewing an org-shared goal gets their own view state even when not a collaborator.

    This is what lets the goal "New activity" divider anchor for casual viewers, who aren't in the
    collaborators list (only the owner + group members are).
    """
    creator = await client.get_default_user()
    viewer = await create_user(organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, owner_id=creator.id, organization_id=creator.organization_id)

    workspace = await Workspace.get(id=goal.workspace_id)
    event = await create_event(workspace, creator_id=creator.id, action=EventAction.GOAL_COMMENTED)
    await Visit.record(user_id=viewer.id, workspace_id=workspace.id, last_event_id=event.id)

    with client.current_user_as(viewer):
        response = await client.get(f"/api/workspaces/{goal.workspace_id}/collaborators")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert str(viewer.id) not in {c["user"]["id"] for c in data["collaborators"]}
    view_state = data["current_user_view_state"]
    assert view_state["viewed"] is True
    assert view_state["last_viewed_event_id"] == str(event.id)
    assert view_state["last_viewed_at"] is not None


@pytest.mark.asyncio
async def test_non_collaborator_viewer_appears_in_viewers(client: AppClient):
    """A non-collaborator org member who viewed a shared goal shows up in `viewers`, not `collaborators`.

    Seen-by is derived from collaborators + viewers, so casual viewers still appear in others' "Seen
    by" avatars — the old goal timeline included all visitors, and dropping non-collaborators was a
    regression.
    """
    creator = await client.get_default_user()
    viewer = await create_user(name="Casual Viewer", organization_id=creator.organization_id)
    goal = await create_goal(creator_id=creator.id, owner_id=creator.id, organization_id=creator.organization_id)

    workspace = await Workspace.get(id=goal.workspace_id)
    event = await create_event(workspace, creator_id=creator.id, action=EventAction.GOAL_COMMENTED)
    await Visit.record(user_id=viewer.id, workspace_id=workspace.id, last_event_id=event.id)

    # Requested by the creator (a collaborator): the viewer is a non-collaborator, so they surface in
    # `viewers` with their cursor, and never in `collaborators`.
    response = await client.get(f"/api/workspaces/{goal.workspace_id}/collaborators")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert str(viewer.id) not in {c["user"]["id"] for c in data["collaborators"]}
    viewers_by_id = {v["user"]["id"]: v["view_state"] for v in data["viewers"]}
    assert viewers_by_id[str(viewer.id)]["last_viewed_event_id"] == str(event.id)
    assert viewers_by_id[str(viewer.id)]["viewed"] is True

    # A viewer never appears in their own `viewers` — their state rides current_user_view_state.
    with client.current_user_as(viewer):
        own = await client.get(f"/api/workspaces/{goal.workspace_id}/collaborators")
    assert str(viewer.id) not in {v["user"]["id"] for v in own.json()["viewers"]}
    assert own.json()["current_user_view_state"]["last_viewed_event_id"] == str(event.id)


@pytest.mark.asyncio
async def test_email_thread_collaborators_use_visit_view_state(client: AppClient):
    # Email threads record visits through the shared /visits endpoint like every other
    # resource, so their view state is Visit-derived too — no special-casing.
    creator = await client.get_default_user()
    viewer = await create_user(name="Opened It", organization_id=creator.organization_id)
    never_opened = await create_user(name="Never Opened", organization_id=creator.organization_id)
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=thread.workspace_id, user_id=viewer.id)
    await create_collaborator(workspace_id=thread.workspace_id, user_id=never_opened.id)

    workspace = await Workspace.get(id=thread.workspace_id)
    event = await create_event(workspace, creator_id=creator.id, action=EventAction.COMMENTED)
    await Visit.record(user_id=viewer.id, workspace_id=workspace.id, last_event_id=event.id)

    response = await client.get(f"/api/workspaces/{thread.workspace_id}/collaborators")
    assert response.status_code == status.HTTP_200_OK
    by_user = {c["user"]["id"]: c["view_state"] for c in response.json()["collaborators"]}

    viewed = by_user[str(viewer.id)]
    assert viewed["viewed"] is True
    assert viewed["last_viewed_at"] is not None
    # Unlike the old mailbox override, email carries a real event cursor.
    assert viewed["last_viewed_event_id"] == str(event.id)

    # A collaborator who never opened the thread in Convictional is unviewed.
    assert by_user[str(never_opened.id)] == {
        "viewed": False,
        "last_viewed_at": None,
        "last_viewed_event_id": None,
    }


@pytest.mark.asyncio
async def test_add_collaborator_via_api(client: AppClient):
    user = await client.get_default_user()
    another_user = await create_user(email="another@example.com", organization_id=user.organization_id)
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators",
        json={"user_id": str(another_user.id), "reason": "joining the project"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    user_ids = {c["user"]["id"] for c in data["collaborators"]}
    assert str(another_user.id) in user_ids

    collaborators = await Collaborator.by_user(another_user.id)
    assert len(collaborators) == 1
    assert collaborators[0].workspace_id == meeting.workspace_id


@pytest.mark.asyncio
async def test_invite_collaborator_via_api(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators/invite",
        json={"email": "newcomer@example.com", "reason": "to plan Q4"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    invited = await User.get(email="newcomer@example.com")
    assert invited is not None
    invited_ids = {c["user"]["id"] for c in response.json()["collaborators"]}
    assert str(invited.id) in invited_ids


@pytest.mark.asyncio
async def test_invite_collaborator_rejects_invalid_email(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators/invite",
        json={"email": "not-an-email"},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_remove_collaborator_via_api(client: AppClient):
    user = await client.get_default_user()
    another_user = await create_user(email="leaver@example.com", organization_id=user.organization_id)
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)
    await create_collaborator(workspace_id=meeting.workspace_id, user_id=another_user.id)

    response = await client.delete(f"/api/workspaces/{meeting.workspace_id}/collaborators/{another_user.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    collaborators = await Collaborator.by_workspace(meeting.workspace_id).all()
    assert all(c.user_id != another_user.id for c in collaborators)


@pytest.mark.asyncio
async def test_approve_pending_collaborator_via_api(client: AppClient):
    user = await client.get_default_user()
    requester = await create_user(email="requester@example.com", organization_id=user.organization_id)
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)
    pending = await Collaborator.create(
        workspace_id=meeting.workspace_id, user_id=requester.id, status=CollaboratorStatus.PENDING
    )

    response = await client.post(f"/api/workspaces/{meeting.workspace_id}/collaborators/{pending.id}/approve")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["pending"] == []
    approved_user_ids = {c["user"]["id"] for c in data["collaborators"]}
    assert str(requester.id) in approved_user_ids

    await pending.refresh_from_db()
    assert pending.status.is_approved


@pytest.mark.asyncio
async def test_access_request_show_and_create(client: AppClient, email_delivery: FakeDelivery):
    creator = await client.get_default_user()
    requestor = await create_user(email="requestor@example.com", organization_id=creator.organization_id)
    meeting = await create_meeting(
        creator_id=creator.id, organization_id=creator.organization_id, sharing=Sharing.PRIVATE
    )

    with client.current_user_as(requestor):
        # Initial state: no pending request, redirect stays null since the requestor can't read the resource.
        response = await client.get(f"/api/workspaces/{meeting.workspace_id}/collaborators/access")
        assert response.status_code == status.HTTP_200_OK
        state = response.json()
        assert state["workspace_id"] == str(meeting.workspace_id)
        assert state["resource_label"] == "meeting"
        assert state["request"] is None

        # Submit creates the pending Collaborator and notifies the creator.
        response = await client.post(
            f"/api/workspaces/{meeting.workspace_id}/collaborators/access",
            json={"note": "Please add me"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["request"]["id"]
        assert data["redirect_url"] is None  # requestor can't read the private meeting

        collaborator = await Collaborator.unscoped.get(workspace_id=meeting.workspace_id, user_id=requestor.id)
        assert collaborator.status.is_pending
        assert len(email_delivery.messages) == 1
        assert "Please add me" in email_delivery.messages[0].html

        # Re-submitting returns the existing request without creating a new one or re-notifying — 200, not 201.
        response = await client.post(
            f"/api/workspaces/{meeting.workspace_id}/collaborators/access",
            json={"note": "again"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["request"]["id"] == str(collaborator.id)
        assert len(email_delivery.messages) == 1

        # Subsequent GET surfaces the existing request so the island can render the confirmation state.
        response = await client.get(f"/api/workspaces/{meeting.workspace_id}/collaborators/access")
        assert response.json()["request"]["id"] == str(collaborator.id)


@pytest.mark.asyncio
async def test_access_request_returns_redirect_when_resource_is_readable(client: AppClient):
    creator = await client.get_default_user()
    requestor = await create_user(email="org-user@example.com", organization_id=creator.organization_id)
    meeting = await create_meeting(
        creator_id=creator.id, organization_id=creator.organization_id, sharing=Sharing.ORGANIZATION
    )

    with client.current_user_as(requestor):
        response = await client.post(
            f"/api/workspaces/{meeting.workspace_id}/collaborators/access",
            json={"note": "please"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["redirect_url"] and data["redirect_url"].endswith(f"/gid/{meeting.global_id.to_param}")


@pytest.mark.asyncio
async def test_access_request_404s_for_other_org(client: AppClient):
    creator = await client.get_default_user()
    outsider = await create_user(email="outsider@otherco.com")
    meeting = await create_meeting(creator_id=creator.id, organization_id=creator.organization_id)

    with client.current_user_as(outsider):
        response = await client.get(f"/api/workspaces/{meeting.workspace_id}/collaborators/access")
        assert response.status_code == status.HTTP_404_NOT_FOUND
