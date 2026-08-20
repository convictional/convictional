import pytest
from fastapi import status

from app.models.collaboration.workspace import Event
from config.enums import EventAction
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_thread, create_user


@pytest.mark.asyncio
async def test_assignment_lifecycle(client: AppClient):
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Clams", organization_id=creator.organization_id)
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    await thread.fetch_related("workspace__collaborators")
    workspace = thread.workspace

    # GET on an unassigned workspace returns `assignee: null`.
    response = await client.get(f"/api/workspaces/{workspace.id}/assignment")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"assignee": None}

    # PATCH assigns Alice.
    response = await client.patch(
        f"/api/workspaces/{workspace.id}/assignment",
        json={"user_id": str(alice.id)},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["assignee"]["id"] == str(alice.id)
    assert response.json()["assignee"]["display_name"] == "Alice Clams"

    await workspace.refresh_from_db()
    assert workspace.assignee_id == alice.id

    # Assigning also adds the user as a collaborator (matches existing HTMX behavior).
    collaborator_ids = [c.user_id for c in await workspace.collaborators.all()]
    assert alice.id in collaborator_ids

    events = await Event.filter(Event.filters.by_workspace(workspace.id)).all()
    assert [e.action for e in events] == [EventAction.ASSIGNED]

    # PATCH again with creator reassigns.
    response = await client.patch(
        f"/api/workspaces/{workspace.id}/assignment",
        json={"user_id": str(creator.id)},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["assignee"]["id"] == str(creator.id)

    await workspace.refresh_from_db()
    assert workspace.assignee_id == creator.id

    # DELETE clears the assignment with 204 No Content.
    response = await client.delete(f"/api/workspaces/{workspace.id}/assignment")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert response.content == b""

    await workspace.refresh_from_db()
    assert workspace.assignee_id is None

    events = await Event.filter(Event.filters.by_workspace(workspace.id)).all()
    assert [e.action for e in events] == [EventAction.ASSIGNED, EventAction.ASSIGNED, EventAction.UNASSIGNED]


@pytest.mark.asyncio
async def test_delete_when_already_unassigned_is_noop(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.delete(f"/api/workspaces/{thread.workspace_id}/assignment")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    events = await Event.filter(Event.filters.by_workspace(thread.workspace_id)).all()
    assert events == []


@pytest.mark.asyncio
async def test_patch_requires_user_id(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.patch(f"/api/workspaces/{thread.workspace_id}/assignment", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_cannot_assign_user_from_another_org(client: AppClient):
    creator = await client.get_default_user()
    outsider = await create_user(name="Other Org")
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.patch(
        f"/api/workspaces/{thread.workspace_id}/assignment",
        json={"user_id": str(outsider.id)},
    )
    # User.get raises DoesNotExist when the user is in a different org, surfacing as 404.
    assert response.status_code == status.HTTP_404_NOT_FOUND
