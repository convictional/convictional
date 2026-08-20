from datetime import UTC, datetime

import pytest
from fastapi import status

from app.jobs.content import ContentIndexingJob
from app.jobs.notifications import SendEventEmailJob
from app.models.accounts import User
from app.models.collaboration.content import Content
from app.models.collaboration.mailbox import Mailbox
from app.models.collaboration.workspace import Collaborator, Notification
from config.enums import CollaboratorStatus, Sharing
from infra.email import FakeDelivery
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_collaborator,
    create_email_thread,
    create_meeting,
    create_user,
)


@pytest.mark.asyncio
async def test_workspace_collaborators(client: AppClient):
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Clams", organization_id=creator.organization_id)
    deleted = await create_user(
        name="Deleted User", organization_id=creator.organization_id, deleted_at=datetime.now(UTC)
    )

    # Test all available collaborators
    response = await client.get("/api/workspaces/collaborators/available")
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["users"]
    assert len(results) == 2
    assert results[0]["id"] == str(alice.id)
    assert results[0]["display_name"] == alice.display_name
    assert results[0]["is_collaborator"] is False  # Available endpoint marks all as non-collaborators
    assert results[1]["id"] == str(creator.id)
    assert results[1]["display_name"] == creator.display_name
    assert results[1]["is_collaborator"] is False

    # Test workspace collaborators
    meeting = await create_meeting(creator_id=creator.id, organization_id=creator.organization_id)
    response = await client.get(f"/api/workspaces/{meeting.workspace_id}/collaborators/typeahead")
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["users"]
    assert len(results) == 2
    assert any(u["is_collaborator"] for u in results)  # Creator is collaborator
    assert not all(u["is_collaborator"] for u in results)  # Alice is not

    await create_collaborator(workspace_id=meeting.workspace_id, user_id=alice.id)
    await create_collaborator(workspace_id=meeting.workspace_id, user_id=deleted.id)
    response = await client.get(f"/api/workspaces/{meeting.workspace_id}/collaborators/typeahead")
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["users"]
    assert len(results) == 2  # Deleted user filtered out
    assert all(u["is_collaborator"] for u in results)  # Both are collaborators


@pytest.mark.asyncio
async def test_workspace_collaborator_content_indexing(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    resource = await create_meeting(
        sharing=Sharing.PRIVATE, creator_id=creator.id, organization_id=creator.organization_id
    )
    await ContentIndexingJob.from_model(resource.organization_id, resource).perform()

    content = await Content.filter(source_id=str(resource.global_id)).first()
    assert content is not None
    assert content.sharing == Sharing.PRIVATE
    assert content.allowed_user_ids == [str(creator.id)]

    response = await client.post(
        f"/api/workspaces/{resource.workspace_id}/collaborators", json={"user_id": str(other_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    await content.refresh_from_db()
    assert content.sharing == Sharing.PRIVATE
    assert len(content.allowed_user_ids) == 2
    assert str(creator.id) in content.allowed_user_ids
    assert str(other_user.id) in content.allowed_user_ids

    response = await client.delete(f"/api/workspaces/{resource.workspace_id}/collaborators/{other_user.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    await content.refresh_from_db()
    assert content.sharing == Sharing.PRIVATE
    assert len(content.allowed_user_ids) == 1
    assert str(creator.id) in content.allowed_user_ids
    assert str(other_user.id) not in content.allowed_user_ids

    response = await client.patch(f"/api/meetings/{resource.id}", json={"sharing": Sharing.ORGANIZATION.value})
    assert response.status_code == status.HTTP_200_OK

    await content.refresh_from_db()
    assert content.sharing == Sharing.ORGANIZATION


@pytest.mark.asyncio
async def test_workspace_collaborators_email_notifications(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    other_user = await create_user(email="another@example.com", organization_id=creator.organization_id)
    subscriber_user = await create_user(email="subscriber@example.com", organization_id=creator.organization_id)
    meeting = await create_meeting(
        title="Test meeting", creator_id=creator.id, organization_id=creator.organization_id
    )

    # Creator is a collaborator by default
    collaborators = await Collaborator.by_workspace(meeting.workspace_id).all()
    assert len(collaborators) == 1
    assert collaborators[0].user_id == creator.id

    # Create a subscriber to the workspace
    await meeting.workspace.subscribe(subscriber_user.id)

    # Add a collaborator
    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(other_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Collaborator was added
    collaborators = await Collaborator.by_workspace(meeting.workspace_id).prefetch_related("user").all()
    assert len(collaborators) == 2
    assert other_user in [c.user for c in collaborators]

    content = await Content.filter(source_id=str(meeting.global_id)).first()
    assert content is not None
    assert len(content.allowed_user_ids) == 2
    assert str(creator.id) in content.allowed_user_ids
    assert str(other_user.id) in content.allowed_user_ids

    # Only one email was enqueued (for the added collaborator, not the subscriber)
    email_jobs = background_jobs.all_completed_jobs_by_type(SendEventEmailJob)
    assert len(email_jobs) == 1
    notification = await Notification.get(id=email_jobs[0].job_definition.notification_id)
    assert notification.user_id == other_user.id

    # Collaborator can access meeting
    with client.current_user_as(other_user):
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK

    # Remove collaborator
    response = await client.delete(f"/api/workspaces/{meeting.workspace_id}/collaborators/{other_user.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Collaborator was removed
    collaborators = await Collaborator.by_workspace(meeting.workspace_id).all()
    assert len(collaborators) == 1

    await content.refresh_from_db()
    assert content.allowed_user_ids == [str(creator.id)]

    # Can no longer access meeting
    with client.current_user_as(other_user):
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK
        assert meeting.title not in response.text
        assert "Request access" in response.text

        # Unless the meeting is shared with the organization
        meeting.sharing = Sharing.ORGANIZATION
        await meeting.save()
        response = await client.get(f"/meetings/{meeting.id}")
        assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_workspace_collaborators_in_app_notifications(client: AppClient):
    creator = await create_user()
    other_user = await create_user(organization_id=creator.organization_id)
    email_thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    await Mailbox.sync(email_thread)

    # Creator is a collaborator by default
    collaborators = await Collaborator.by_workspace(email_thread.workspace_id).all()
    assert len(collaborators) == 1
    assert collaborators[0].user_id == creator.id

    # Creator can access email thread
    with client.current_user_as(creator):
        response = await client.get(f"/api/email_threads/{email_thread.id}")
        assert response.status_code == status.HTTP_200_OK

        # Add a collaborator
        response = await client.post(
            f"/api/workspaces/{email_thread.workspace_id}/collaborators", json={"user_id": str(other_user.id)}
        )
        assert response.status_code == status.HTTP_201_CREATED

    # Collaborator was added
    collaborators = await Collaborator.by_workspace(email_thread.workspace_id).prefetch_related("user").all()
    assert len(collaborators) == 2
    assert other_user in [c.user for c in collaborators]

    # Collaborator's mailbox entry was created
    mailbox_entry = await Mailbox(other_user).entry(email_thread).get()
    assert mailbox_entry is not None
    assert mailbox_entry.is_unread

    # Collaborator can access email thread
    with client.current_user_as(other_user):
        response = await client.get(f"/api/email_threads/{email_thread.id}")
        assert response.status_code == status.HTTP_200_OK

    # Remove collaborator
    with client.current_user_as(creator):
        response = await client.delete(f"/api/workspaces/{email_thread.workspace_id}/collaborators/{other_user.id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    # Collaborator was removed
    collaborators = await Collaborator.by_workspace(email_thread.workspace_id).all()
    assert len(collaborators) == 1

    # Can no longer access email thread: the SPA shell always 200s, so access
    # gating lives on the API — a same-org non-collaborator gets a 403 carrying
    # the request-access URL the client turns into a CTA.
    with client.current_user_as(other_user):
        response = await client.get(f"/api/email_threads/{email_thread.id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.json()["request_access_url"]


@pytest.mark.asyncio
async def test_add_collaborator(client: AppClient):
    user = await client.get_default_user()
    another_user = await create_user(email="another@example.com", organization_id=user.organization_id)
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(another_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    collaborator = await Collaborator.by_user(another_user.id)
    assert len(collaborator) == 1
    assert collaborator[0].workspace_id == meeting.workspace_id


@pytest.mark.asyncio
async def test_invite_collaborator(client: AppClient):
    user = await client.get_default_user()
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators/invite",
        json={"email": "another@example.com"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    user = await User.get(email="another@example.com")
    assert user is not None

    collaborator = await Collaborator.by_user(user.id)
    assert len(collaborator) == 1
    assert collaborator[0].workspace_id == meeting.workspace_id


@pytest.mark.asyncio
async def test_request_access_page_renders_only_for_org_members(client: AppClient):
    # The HTML page is now a thin shell that hosts the React island — submission and state
    # live in the API (see tests/integration/routers/api/test_workspace_collaborators.py).
    # The HTML route still 404s for outsiders so the page doesn't render at all for them.
    user = await client.get_default_user()
    outsider = await create_user(email="bob@clams.com")
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    with client.current_user_as(outsider):
        response = await client.get(f"/workspaces/{meeting.workspace_id}/collaborators/access")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    same_org_member = await create_user(email="another@example.com", organization_id=user.organization_id)
    with client.current_user_as(same_org_member):
        response = await client.get(f"/workspaces/{meeting.workspace_id}/collaborators/access")
        assert response.status_code == status.HTTP_200_OK
        assert "react-workspace-access-request" in response.text


@pytest.mark.asyncio
async def test_grant_collaborator_access(client: AppClient, email_delivery: FakeDelivery):
    user = await client.get_default_user()
    another_user = await create_user(email="another@exampl.com", organization_id=user.organization_id)
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)

    collaborator = await Collaborator.create(
        workspace_id=meeting.workspace_id, user_id=another_user.id, status=CollaboratorStatus.PENDING
    )

    response = await client.get(f"/meetings/{meeting.id}")
    assert response.status_code == status.HTTP_200_OK
    assert user.display_name in response.text

    response = await client.post(f"/api/workspaces/{meeting.workspace_id}/collaborators/{collaborator.id}/approve")
    assert response.status_code == status.HTTP_201_CREATED

    await collaborator.refresh_from_db()
    assert collaborator.status.is_approved
    assert collaborator.added_by_id == user.id

    assert len(email_delivery.messages) == 1
    email = email_delivery.messages[0]
    assert email.to == another_user.email
    assert "added you as a collaborator" in email.html
    # Subject must include the meeting title so different resources don't
    # collapse to a single inbox thread.
    assert meeting.title in email.subject

    content = await Content.filter(source_id=str(meeting.global_id)).first()
    assert content is not None
    assert len(content.allowed_user_ids) == 2
    assert str(user.id) in content.allowed_user_ids
    assert str(another_user.id) in content.allowed_user_ids


@pytest.mark.asyncio
async def test_adding_collaborator_with_pending_access_request(client: AppClient):
    user = await client.get_default_user()
    another_user = await create_user(email="another@example.com", organization_id=user.organization_id)

    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)
    collaborator = await Collaborator.create(
        workspace_id=meeting.workspace_id, user_id=another_user.id, status=CollaboratorStatus.PENDING
    )

    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(another_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    collaborator = await Collaborator.by_user(another_user.id).first()
    assert collaborator
    assert collaborator.status.is_approved


@pytest.mark.asyncio
async def test_displaying_deleted_collaborators(client: AppClient):
    user = await client.get_default_user()
    another_user = await create_user(email="collaborator@user.com", organization_id=user.organization_id)
    meeting = await create_meeting(creator_id=user.id, organization_id=user.organization_id)
    collaborator = await Collaborator.create(
        workspace_id=meeting.workspace_id, user_id=another_user.id, status=CollaboratorStatus.PENDING
    )
    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(another_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Delete the collaborator
    await another_user.soft_delete()
    await another_user.refresh_from_db()
    assert another_user.is_deleted

    # Ensure the user model is still linked to the collaborator
    collaborator = await Collaborator.by_user(another_user.id).first()
    assert collaborator.user
    assert collaborator.user_id == another_user.id


@pytest.mark.asyncio
async def test_removing_collaborator_with_organization_sharing(client: AppClient):
    user = await client.get_default_user()
    another_user = await create_user(email="collaborator@example.com", organization_id=user.organization_id)

    # Create a meeting with organization sharing
    meeting = await create_meeting(
        creator_id=user.id, organization_id=user.organization_id, sharing=Sharing.ORGANIZATION
    )

    # Add collaborator
    response = await client.post(
        f"/api/workspaces/{meeting.workspace_id}/collaborators", json={"user_id": str(another_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    # Verify collaborator exists
    collaborator = await Collaborator.by_workspace(meeting.workspace_id).filter(user_id=another_user.id).first()
    assert collaborator is not None

    # Remove collaborator. Subscription rows are no longer written or modified
    # by collaborator add/remove; the row table represents only explicit user
    # actions. Removal just deletes the Collaborator row.
    response = await client.delete(f"/api/workspaces/{meeting.workspace_id}/collaborators/{another_user.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Verify collaborator was removed
    collaborator = await Collaborator.by_workspace(meeting.workspace_id).filter(user_id=another_user.id).first()
    assert collaborator is None
