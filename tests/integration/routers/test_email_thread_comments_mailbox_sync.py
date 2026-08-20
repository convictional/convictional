import pytest
from fastapi import status

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.collaboration.workspace import Subscription
from config.enums import MailboxLabel, SubscriptionLevel
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_collaborator,
    create_email_message,
    create_email_thread,
    create_email_thread_comment,
    create_user,
)


async def _create_thread_with_message(user):
    email_thread = await create_email_thread(
        creator_id=user.id, organization_id=user.organization_id, title="Test Thread"
    )
    await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_thread_id=email_thread.external_thread_id,
    )
    await email_thread.refresh_from_db()
    return email_thread


@pytest.mark.asyncio
async def test_create_comment_syncs_mailbox_entries(client: AppClient):
    user = await client.get_default_user()
    collaborator = await create_user(organization_id=user.organization_id)
    email_thread = await _create_thread_with_message(user)
    await create_collaborator(
        workspace_id=email_thread.workspace_id, user_id=collaborator.id, organization_id=user.organization_id
    )
    await Subscription.create(
        workspace_id=email_thread.workspace_id, subscriber_id=collaborator.id, level=SubscriptionLevel.ALL
    )

    response = await client.post(f"/api/email_threads/{email_thread.id}/comments", json={"content": "Team comment"})
    assert response.status_code == status.HTTP_201_CREATED

    author_entry = await MailboxEntry.get(owner_id=user.id, resource_gid=str(email_thread.global_id))
    assert author_entry.last_comment == "Team comment"
    assert author_entry.is_preview_comment is True

    collaborator_entry = await MailboxEntry.get(owner_id=collaborator.id, resource_gid=str(email_thread.global_id))
    assert collaborator_entry.last_comment == "Team comment"


@pytest.mark.asyncio
async def test_update_and_delete_comment_syncs_mailbox_entries(client: AppClient):
    user = await client.get_default_user()
    collaborator = await create_user(organization_id=user.organization_id)
    email_thread = await _create_thread_with_message(user)
    await create_collaborator(
        workspace_id=email_thread.workspace_id, user_id=collaborator.id, organization_id=user.organization_id
    )

    comment = await create_email_thread_comment(
        workspace_id=email_thread.workspace_id, user_id=user.id, content="Original"
    )
    await Mailbox.sync(email_thread)

    # Edit syncs all collaborators' entries
    response = await client.patch(
        f"/api/email_threads/{email_thread.id}/comments/{comment.id}", json={"content": "Edited"}
    )
    assert response.status_code == status.HTTP_200_OK

    author_entry = await MailboxEntry.get(owner_id=user.id, resource_gid=str(email_thread.global_id))
    assert author_entry.last_comment == "Edited"

    collaborator_entry = await MailboxEntry.get(owner_id=collaborator.id, resource_gid=str(email_thread.global_id))
    assert collaborator_entry.last_comment == "Edited"

    # Delete syncs all collaborators' entries — preview falls back to message, and the deleted
    # comment's text is cleared from the row rather than left stale.
    response = await client.delete(f"/api/email_threads/{email_thread.id}/comments/{comment.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    await author_entry.refresh_from_db()
    assert author_entry.is_preview_comment is False
    assert author_entry.last_comment is None
    assert author_entry.last_comment_author_id is None

    await collaborator_entry.refresh_from_db()
    assert collaborator_entry.is_preview_comment is False
    assert collaborator_entry.last_comment is None
    assert collaborator_entry.last_comment_author_id is None


@pytest.mark.asyncio
async def test_edit_and_delete_do_not_realert_caught_up_collaborators(client: AppClient):
    # The content-revision routing rule: a comment edit/delete refreshes a caught-up collaborator's
    # preview but must not re-mark their row unread.
    user = await client.get_default_user()
    collaborator = await create_user(organization_id=user.organization_id)
    email_thread = await _create_thread_with_message(user)
    await create_collaborator(
        workspace_id=email_thread.workspace_id, user_id=collaborator.id, organization_id=user.organization_id
    )
    await Subscription.create(
        workspace_id=email_thread.workspace_id, subscriber_id=collaborator.id, level=SubscriptionLevel.ALL
    )

    # Creator comments → collaborator's row goes unread.
    response = await client.post(f"/api/email_threads/{email_thread.id}/comments", json={"content": "Original"})
    comment_id = response.json()["id"]
    collaborator_entry = await MailboxEntry.get(owner_id=collaborator.id, resource_gid=str(email_thread.global_id))
    assert MailboxLabel.UNREAD in collaborator_entry.labels

    # Collaborator catches up.
    collaborator_entry.label_as_read()
    await collaborator_entry.save(update_fields=["labels"])
    activity_before_edit = collaborator_entry.last_activity_at

    # Edit refreshes the preview but doesn't re-alert — and doesn't float the thread to the
    # top: the edit event is not thread activity, so the activity cursor must not advance.
    response = await client.patch(
        f"/api/email_threads/{email_thread.id}/comments/{comment_id}", json={"content": "Edited"}
    )
    assert response.status_code == status.HTTP_200_OK
    await collaborator_entry.refresh_from_db()
    assert MailboxLabel.UNREAD not in collaborator_entry.labels
    assert collaborator_entry.last_comment == "Edited"
    assert collaborator_entry.last_activity_at == activity_before_edit

    # A later no-event resync (e.g. inbound mail, collaborator change) must not re-read the
    # edit event as new activity-from-others and resurrect the caught-up reader as unread.
    await email_thread.fetch_related("workspace")
    await Mailbox.sync(email_thread)
    await collaborator_entry.refresh_from_db()
    assert MailboxLabel.UNREAD not in collaborator_entry.labels

    # Delete likewise refreshes (preview falls back) without re-alerting.
    response = await client.delete(f"/api/email_threads/{email_thread.id}/comments/{comment_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await collaborator_entry.refresh_from_db()
    assert MailboxLabel.UNREAD not in collaborator_entry.labels
    assert collaborator_entry.is_preview_comment is False


@pytest.mark.asyncio
async def test_edit_added_mention_surfaces_thread_unread_for_new_user(client: AppClient):
    # The one case an edit surfaces a row unread: a newly-@mentioned user pulled into the
    # thread by the edit. They get a row in their inbox, unread.
    user = await client.get_default_user()
    quiet = await create_user(name="Quiet Mentioned", organization_id=user.organization_id)
    email_thread = await create_email_thread(
        creator_id=user.id, organization_id=user.organization_id, title="Mention Thread"
    )

    response = await client.post(f"/api/email_threads/{email_thread.id}/comments", json={"content": "Initial"})
    comment_id = response.json()["id"]
    assert not await MailboxEntry.filter(owner_id=quiet.id, resource_gid=str(email_thread.global_id)).exists()

    response = await client.patch(
        f"/api/email_threads/{email_thread.id}/comments/{comment_id}",
        json={"content": "Now @[Quiet Mentioned] take a look"},
    )
    assert response.status_code == status.HTTP_200_OK

    entry = await MailboxEntry.get(owner_id=quiet.id, resource_gid=str(email_thread.global_id))
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels
