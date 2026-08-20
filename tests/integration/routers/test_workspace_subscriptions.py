import pytest
from fastapi import status

from app.jobs.notifications import SendEventEmailJob
from app.models.collaboration.workspace import Notification, SubscriberResolver, Subscription, SubscriptionPreference
from app.models.workspaces.documents import Document
from app.models.workspaces.meetings import Meeting
from config.enums import JobStatus, Sharing, SubscriptionLevel
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import create_collaborator, create_document, create_meeting, create_user


@pytest.mark.asyncio
async def test_no_subscription_rows_written_for_creator_or_collaborator(client: AppClient):
    creator = await client.get_default_user()
    await SubscriptionPreference.update_for(creator.id, {Meeting.record_type: SubscriptionLevel.ALL})

    # Creating a meeting no longer writes a Subscription row for the creator.
    # They are still effectively subscribed via their global preference (ALL).
    meeting = await create_meeting(
        title="Test meeting", creator_id=creator.id, organization_id=creator.organization_id
    )
    await meeting.fetch_related("workspace")

    creator_row = await Subscription.get_or_none(workspace_id=meeting.workspace_id, subscriber_id=creator.id)
    assert creator_row is None

    subscribers = await SubscriberResolver(workspace=meeting.workspace).resolve()
    assert creator in subscribers

    # Adding a collaborator does not write a Subscription row either.
    other_user = await create_user(email="other@example.com", organization_id=creator.organization_id)
    await SubscriptionPreference.update_for(other_user.id, {Meeting.record_type: SubscriptionLevel.ALL})
    response = await client.post(
        f"/api/workspaces/{meeting.workspace.id}/collaborators", json={"user_id": str(other_user.id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    other_row = await Subscription.get_or_none(workspace_id=meeting.workspace_id, subscriber_id=other_user.id)
    assert other_row is None

    subscribers = await SubscriberResolver(workspace=meeting.workspace).resolve()
    assert other_user in subscribers

    # Removing a collaborator does not touch subscription rows. Access-control
    # gates delivery if the user loses access; the row (if any) is preserved.
    response = await client.delete(f"/api/workspaces/{meeting.workspace.id}/collaborators/{other_user.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    other_row = await Subscription.get_or_none(workspace_id=meeting.workspace_id, subscriber_id=other_user.id)
    assert other_row is None


@pytest.mark.asyncio
async def test_subscription_notifications(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    other_user = await create_user(email="other@example.com", organization_id=creator.organization_id)

    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    await document.fetch_related("workspace")
    await create_collaborator(workspace_id=document.workspace_id, user_id=other_user.id)
    await SubscriptionPreference.update_for(other_user.id, {Document.record_type: SubscriptionLevel.ALL})

    # Creator comments on the document
    response = await client.post(f"/api/documents/{document.id}/comments", json={"content": "Test comment"})
    assert response.status_code == status.HTTP_201_CREATED

    # The subscribed collaborator receives a notification
    notification_job = next(
        job for job in background_jobs.completed if isinstance(job.job_definition, SendEventEmailJob)
    )
    assert notification_job.status == JobStatus.SUCCESSFUL
    assert isinstance(notification_job.job_definition, SendEventEmailJob)
    notification = await Notification.get(id=notification_job.job_definition.notification_id)
    assert notification.event_id is not None
    assert notification.user_id == other_user.id
    background_jobs.completed.clear()

    # Unsubscribe the collaborator
    await document.workspace.unsubscribe(other_user.id)

    # Creator comments again
    response = await client.post(f"/api/documents/{document.id}/comments", json={"content": "Second comment"})
    assert response.status_code == status.HTTP_201_CREATED

    # No further notification is delivered to the now-unsubscribed collaborator
    assert sum(1 for job in background_jobs.completed if isinstance(job.job_definition, SendEventEmailJob)) == 0
