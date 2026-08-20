from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import status
from pycrdt import Text

from app.jobs.email import ScheduledDraftSendJob, SweepOverdueScheduledDraftsJob
from app.jobs.notifications import SendEventEmailJob
from app.jobs.push import SendEventPushJob
from app.models.collaboration.live import LiveDocument, LiveDocumentUpdate
from app.models.collaboration.mailbox import Mailbox, MailboxEntry, MailboxSync
from app.models.workspaces.email.client import FakeEmailClient
from app.models.workspaces.email.thread import EmailMessage, EmailThread
from config import settings
from config.enums import EmailLabel, EmailMailboxLabel, EmailMessageType, EventAction
from config.settings import EmailClient
from infra.jobs import enqueue_job
from tests.helpers.app import AppClient
from tests.helpers.factories import create_email_message, create_push_subscription, create_user


async def setup_live_document_content(thread: EmailThread, content: str) -> None:
    """Helper to set up live document content for tests that need a non-empty body."""
    draft = await thread.get_draft()
    assert draft is not None
    topic = draft.live_document_topic
    live_doc = await LiveDocument.for_topic(topic)
    markdown_text = live_doc.get("markdown", type=Text)
    markdown_text.insert(0, content)
    await LiveDocumentUpdate.create(topic_name=topic.name, update_data=live_doc.get_update())


async def _seed_draft(user, **kwargs) -> EmailMessage:
    """Create an in-thread draft message owned by `user`."""
    return await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject=kwargs.pop("subject", "Hello"),
        to=kwargs.pop("to", ["recipient@example.com"]),
        cc=kwargs.pop("cc", []),
        bcc=kwargs.pop("bcc", []),
        body_plain=kwargs.pop("body_plain", "draft body"),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_get_returns_envelope(client: AppClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user, subject="Subject A", to=["a@example.com"], cc=["c@example.com"])

    response = await client.get(f"/api/email_threads/{draft.thread_id}/draft")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    assert body["subject"] == "Subject A"
    assert body["to"] == ["a@example.com"]
    assert body["cc"] == ["c@example.com"]
    assert body["bcc"] == []
    assert body["attachments"] == []
    assert body["sendable_by"]
    assert body["can_reply"] is True


@pytest.mark.asyncio
async def test_composer_returns_full_response(client: AppClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user, subject="Hello", to=["a@example.com"])

    response = await client.get(f"/api/email_threads/{draft.thread_id}/composer")
    assert response.status_code == status.HTTP_200_OK

    body = response.json()
    # The React loader fetches this on mount with only {threadId, focusBody}
    # as bootstrap. Everything else must come from this endpoint.
    assert body["thread_id"] == str(draft.thread_id)
    assert body["draft_message_id"] == str(draft.id)
    assert body["current_user"]["id"] == str(user.id)
    assert body["patch_url"].endswith("/draft")
    assert body["send_url"].endswith("/draft/send")
    assert body["schedule_url"].endswith("/draft/schedule")
    assert body["unschedule_url"].endswith("/draft/unschedule")
    assert body["default_snooze_times"]
    assert body["initial_envelope"]["subject"] == "Hello"
    assert body["initial_envelope"]["to"] == ["a@example.com"]
    # The full DraftEnvelopeResponse is embedded under initial_envelope, so
    # attachments and assignment state live there too.
    assert body["initial_envelope"]["attachments"] == []
    assert body["initial_envelope"]["can_reply"] is True
    # focus_body is supplied by the React loader from data-props, not the server.
    assert "focus_body" not in body


@pytest.mark.asyncio
async def test_patch_updates_only_provided_fields(client: AppClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user, subject="Original", to=["existing@example.com"])

    response = await client.patch(
        f"/api/email_threads/{draft.thread_id}/draft",
        json={"subject": "Updated"},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    await draft.refresh_from_db()
    assert draft.subject == "Updated"
    assert draft.to == ["existing@example.com"]


@pytest.mark.asyncio
async def test_patch_clears_recipients_when_explicit_empty_list(client: AppClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["x@y.com"], cc=["c@y.com"])

    response = await client.patch(
        f"/api/email_threads/{draft.thread_id}/draft",
        json={"to": [], "cc": []},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    await draft.refresh_from_db()
    assert draft.to == []
    assert draft.cc == []


@pytest.mark.asyncio
async def test_patch_with_no_fields_rejects_empty_body(client: AppClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user, subject="Untouched", to=["x@y.com"])

    response = await client.patch(f"/api/email_threads/{draft.thread_id}/draft", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    await draft.refresh_from_db()
    assert draft.subject == "Untouched"
    assert draft.to == ["x@y.com"]


@pytest.mark.asyncio
async def test_patch_send_happy_path(client: AppClient, email_client: FakeEmailClient):
    user = await client.get_default_user()
    draft = await _seed_draft(
        user,
        subject="Send subject",
        to=["recipient@example.com"],
        body_plain="Body text",
    )
    thread = await EmailThread.get(id=draft.thread_id)
    await Mailbox.sync(thread)
    draft_obj = await thread.get_draft()
    assert draft_obj is not None
    await LiveDocument.set_initial_content(draft_obj.live_document_topic, "Body text")

    response = await client.post(
        f"/api/email_threads/{draft.thread_id}/draft/send",
        json={
            "subject": "Send subject",
            "to": ["recipient@example.com"],
            "message_body": "Body text",
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_send_allows_empty_subject_and_body(client: AppClient, email_client: FakeEmailClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user, subject="", to=["recipient@example.com"], body_plain="")
    thread = await EmailThread.get(id=draft.thread_id)
    await Mailbox.sync(thread)
    draft_obj = await thread.get_draft()
    assert draft_obj is not None
    await LiveDocument.set_initial_content(draft_obj.live_document_topic, "")

    response = await client.post(
        f"/api/email_threads/{draft.thread_id}/draft/send",
        json={"subject": "", "to": ["recipient@example.com"], "message_body": ""},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_send_allows_empty_subject_or_body(client: AppClient, email_client: FakeEmailClient):
    # The subject and body required checks were removed independently, so cover
    # each half-case: empty subject with a body, and a subject with empty body.
    user = await client.get_default_user()

    for subject, body in [("", "Body text"), ("Send subject", "")]:
        draft = await _seed_draft(user, subject=subject, to=["recipient@example.com"], body_plain=body)
        thread = await EmailThread.get(id=draft.thread_id)
        await Mailbox.sync(thread)
        draft_obj = await thread.get_draft()
        assert draft_obj is not None
        await LiveDocument.set_initial_content(draft_obj.live_document_topic, body)

        response = await client.post(
            f"/api/email_threads/{draft.thread_id}/draft/send",
            json={"subject": subject, "to": ["recipient@example.com"], "message_body": body},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_send_rejects_snooze_in_past(client: AppClient, email_client: FakeEmailClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user)

    response = await client.post(
        f"/api/email_threads/{draft.thread_id}/draft/send",
        json={
            "subject": "S",
            "to": ["recipient@example.com"],
            "message_body": "Body",
            "should_snooze": True,
            "snoozed_until": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_delete_keeps_thread_when_other_messages_exist(client: AppClient):
    user = await client.get_default_user()
    # An existing received message keeps the thread alive after draft deletion.
    received = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="thread_with_history",
        subject="Original",
        sender="sender@example.com",
    )
    thread = await EmailThread.get(id=received.thread_id)
    await thread.start_draft(user=user, subject="Re: Original", body_plain="reply")

    response = await client.delete(f"/api/email_threads/{thread.id}/draft")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await EmailThread.get_or_none(id=thread.id) is not None


@pytest.mark.asyncio
async def test_delete_drops_thread_when_only_draft(client: AppClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user)

    response = await client.delete(f"/api/email_threads/{draft.thread_id}/draft")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await EmailThread.get_or_none(id=draft.thread_id) is None


@pytest.mark.asyncio
async def test_sequential_patch_disjoint_keys_both_persist(client: AppClient):
    """Disjoint-key PATCHes commute: the update_fields protocol must preserve untouched columns.

    A truly concurrent test (asyncio.gather across two AppClient instances) hits a pre-existing
    Mailbox.sync race that's unrelated to PATCH semantics — see lessons learned. Sequential is
    sufficient to verify the dirty-flag protocol: only keys in the JSON body are written.
    """
    user = await client.get_default_user()
    draft = await _seed_draft(user, subject="Initial", to=["initial@x.com"])

    subject_response = await client.patch(f"/api/email_threads/{draft.thread_id}/draft", json={"subject": "Subject A"})
    assert subject_response.status_code == status.HTTP_204_NO_CONTENT

    to_response = await client.patch(f"/api/email_threads/{draft.thread_id}/draft", json={"to": ["new@x.com"]})
    assert to_response.status_code == status.HTTP_204_NO_CONTENT

    await draft.refresh_from_db()
    assert draft.subject == "Subject A"
    assert draft.to == ["new@x.com"]


# ----------------------------------------------------------------------
# Assignee / shared-draft send tests
#
# These tests cover the cross-cutting business logic that an assignee on a shared
# thread can send on behalf of the creator, with the expected mailbox-state
# side effects (sent labels, inbox/unread propagation, archive on demand).
# They live here because the API send route is the single integration point.
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assignee_can_send_new_thread_draft(client: AppClient, email_client: FakeEmailClient):
    """Assignee should be able to send a draft on a new thread (no external_thread_id)."""
    creator = await create_user(email="creator@convictional.com")
    assignee = await create_user(email="assignee@convictional.com", organization_id=creator.organization_id)

    email_message = await create_email_message(
        user_id=creator.id,
        creator_id=creator.id,
        organization_id=creator.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Assignee Send Test",
        body_plain="Test body",
        to=["recipient@example.com"],
        external_thread_id=None,
        labels=[EmailLabel.DRAFT],
    )

    thread = await email_message.thread.get()
    await thread.fetch_related("workspace")
    await thread.collaboration.add(assignee, creator)
    await thread.collaboration.assign_to(assignee, creator)
    await Mailbox.sync(thread)
    await setup_live_document_content(thread, "Test body")

    with settings.override():
        settings.email_client = EmailClient.FAKE

        client.current_user = assignee
        response = await client.post(
            f"/api/email_threads/{thread.id}/draft/send",
            json={
                "subject": "Assignee Send Test",
                "to": ["recipient@example.com"],
                "message_body": "Test body",
            },
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

    await email_message.refresh_from_db()
    assert email_message.was_sent
    assert email_message.sender and assignee.email in email_message.sender


@pytest.mark.asyncio
async def test_assignee_send_authorization_existing_thread(client: AppClient, email_client: FakeEmailClient):
    """Assignee cannot send on an existing thread (has external_thread_id)."""
    creator = await create_user(email="creator@convictional.com")
    assignee = await create_user(email="assignee@convictional.com", organization_id=creator.organization_id)

    message = await create_email_message(
        user_id=creator.id,
        creator_id=creator.id,
        organization_id=creator.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Existing Thread Draft",
        body_plain="Test body",
        to=["recipient@example.com"],
        external_thread_id="existing-gmail-thread-123",
        labels=[EmailLabel.DRAFT],
    )
    thread = await message.thread.get()
    await thread.fetch_related("workspace")
    await thread.collaboration.add(assignee, creator)
    await thread.collaboration.assign_to(assignee, creator)
    await setup_live_document_content(thread, "Test body")

    client.current_user = assignee
    response = await client.post(
        f"/api/email_threads/{thread.id}/draft/send",
        json={
            "subject": "Existing Thread Draft",
            "to": ["recipient@example.com"],
            "message_body": "Test body",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_non_assignee_collaborator_cannot_send(client: AppClient, email_client: FakeEmailClient):
    """A non-assignee collaborator on a thread cannot send the draft."""
    creator = await create_user(email="creator@convictional.com")
    collaborator = await create_user(email="collab@convictional.com", organization_id=creator.organization_id)

    message = await create_email_message(
        user_id=creator.id,
        creator_id=creator.id,
        organization_id=creator.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Collab Send Test",
        body_plain="Test body",
        to=["recipient@example.com"],
        external_thread_id=None,
        labels=[EmailLabel.DRAFT],
    )
    thread = await message.thread.get()
    await thread.fetch_related("workspace")
    await thread.collaboration.add(collaborator, creator)
    await setup_live_document_content(thread, "Test body")

    client.current_user = collaborator
    response = await client.post(
        f"/api/email_threads/{thread.id}/draft/send",
        json={
            "subject": "Collab Send Test",
            "to": ["recipient@example.com"],
            "message_body": "Test body",
        },
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_send_without_archive_keeps_thread_in_inbox(client: AppClient, email_client: FakeEmailClient):
    """Sending a draft (no archive, no snooze) on a shared thread must leave the
    sender's MailboxEntry with INBOX. Mailbox.sync alone won't pin INBOX here:
    own-send doesn't qualify as "activity from others", and a draft-only thread
    has thread.is_inbox=False. The send handler explicitly re-labels the sender's
    entry as INBOX, symmetric to the archive branch."""
    creator = await create_user(email="creator@convictional.com")
    assignee = await create_user(email="assignee@convictional.com", organization_id=creator.organization_id)

    draft_message = await create_email_message(
        user_id=creator.id,
        creator_id=creator.id,
        organization_id=creator.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Shared Thread",
        body_plain="My reply",
        to=["recipient@example.com"],
        external_thread_id=None,
        labels=[EmailLabel.DRAFT],
    )
    thread = await draft_message.thread.get()
    await thread.fetch_related("workspace")
    await thread.collaboration.add(assignee, creator)
    await thread.collaboration.assign_to(assignee, creator)
    await Mailbox.sync(thread)
    await setup_live_document_content(thread, "My reply")

    client.current_user = creator
    response = await client.post(
        f"/api/email_threads/{thread.id}/draft/send",
        json={
            "subject": "Shared Thread",
            "to": ["recipient@example.com"],
            "message_body": "My reply",
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    creator_entry = await MailboxEntry.filter(
        MailboxEntry.filters.by_resource(thread.global_id),
        MailboxEntry.filters.by_owner(creator.id),
    ).first()
    assert creator_entry is not None
    assert creator_entry.is_inbox


@pytest.mark.asyncio
async def test_assignee_send_marks_creator_inbox_unread(client: AppClient, email_client: FakeEmailClient):
    """When an assignee sends on a new shared thread, the creator's mailbox entry
    must surface as INBOX + UNREAD so the sent activity is visible as new."""
    creator = await create_user(email="creator@convictional.com")
    assignee = await create_user(email="assignee@convictional.com", organization_id=creator.organization_id)

    draft_message = await create_email_message(
        user_id=creator.id,
        creator_id=creator.id,
        organization_id=creator.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Shared Send Activity",
        body_plain="Reply body",
        to=["recipient@example.com"],
        external_thread_id=None,
        labels=[EmailLabel.DRAFT],
    )
    thread = await draft_message.thread.get()
    await thread.fetch_related("workspace")
    await thread.collaboration.add(assignee, creator)
    await thread.collaboration.assign_to(assignee, creator)
    await Mailbox.sync(thread)
    await setup_live_document_content(thread, "Reply body")

    client.current_user = assignee
    response = await client.post(
        f"/api/email_threads/{thread.id}/draft/send",
        json={
            "subject": "Shared Send Activity",
            "to": ["recipient@example.com"],
            "message_body": "Reply body",
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    creator_entry = await Mailbox(creator).entry(thread).get_or_none()
    assert creator_entry is not None
    assert creator_entry.is_inbox
    assert creator_entry.is_unread


@pytest.mark.asyncio
async def test_send_marks_non_assignee_collaborator_inbox_unread(client: AppClient, email_client: FakeEmailClient):
    """A non-assignee collaborator on a shared thread must see the send as new
    activity: their mailbox entry should be INBOX + UNREAD after anyone sends."""
    creator = await create_user(email="creator@convictional.com")
    assignee = await create_user(email="assignee@convictional.com", organization_id=creator.organization_id)
    collaborator = await create_user(email="collab@convictional.com", organization_id=creator.organization_id)

    draft_message = await create_email_message(
        user_id=creator.id,
        creator_id=creator.id,
        organization_id=creator.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Three-Party Shared Send",
        body_plain="Reply body",
        to=["recipient@example.com"],
        external_thread_id=None,
        labels=[EmailLabel.DRAFT],
    )
    thread = await draft_message.thread.get()
    await thread.fetch_related("workspace")
    await thread.collaboration.add(assignee, creator)
    await thread.collaboration.add(collaborator, creator)
    await thread.collaboration.assign_to(assignee, creator)
    await Mailbox.sync(thread)
    await setup_live_document_content(thread, "Reply body")

    client.current_user = assignee
    response = await client.post(
        f"/api/email_threads/{thread.id}/draft/send",
        json={
            "subject": "Three-Party Shared Send",
            "to": ["recipient@example.com"],
            "message_body": "Reply body",
        },
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    collaborator_entry = await Mailbox(collaborator).entry(thread).get_or_none()
    assert collaborator_entry is not None
    assert collaborator_entry.is_inbox
    assert collaborator_entry.is_unread


@pytest.mark.asyncio
async def test_delete_cleans_up_mailbox_entries(client: AppClient, email_client: FakeEmailClient):
    """When a single-draft thread is deleted, all MailboxEntries for it are soft-deleted."""
    user = await client.get_default_user()

    single_draft = await create_email_message(
        user_id=user.id,
        organization_id=user.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Single Draft",
        body_plain="This draft will be deleted",
        to=["recipient@example.com"],
    )
    thread_id = single_draft.thread_id
    thread = await EmailThread.get(id=thread_id).prefetch_related("messages")
    assert len(thread.messages) == 1
    await Mailbox.sync(thread)

    entries_before = await MailboxEntry.filter(MailboxEntry.filters.by_resource(thread.global_id)).all()
    assert len(entries_before) > 0
    assert all(not entry.is_deleted for entry in entries_before)

    response = await client.delete(f"/api/email_threads/{thread_id}/draft")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert await EmailThread.get_or_none(id=thread_id) is None

    entries_after = await MailboxEntry.unscoped.filter(MailboxEntry.filters.by_resource(thread.global_id)).all()
    assert len(entries_after) > 0
    assert all(entry.is_deleted for entry in entries_after)


#
# Scheduled send
#


def _future() -> datetime:
    return datetime.now(UTC) + timedelta(days=1)


async def _schedule(client: AppClient, thread_id, scheduled_for: datetime, **overrides):
    payload = {
        "subject": "Scheduled subject",
        "to": ["recipient@example.com"],
        "message_body": "Body text",
        "scheduled_for": scheduled_for.isoformat(),
        **overrides,
    }
    return await client.post(f"/api/email_threads/{thread_id}/draft/schedule", json=payload)


@pytest.mark.asyncio
async def test_schedule_sets_scheduled_for_and_enqueues_deferred_job(
    client: AppClient, email_client: FakeEmailClient, background_jobs
):
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    scheduled_for = _future()

    response = await _schedule(client, draft.thread_id, scheduled_for)
    assert response.status_code == status.HTTP_202_ACCEPTED
    assert response.json()["scheduled_for"]

    # A scheduled draft is still a DRAFT (stays in Drafts) with scheduled_for set.
    message = await EmailMessage.get(id=draft.id)
    assert message.message_type == EmailMessageType.DRAFT
    assert message.scheduled_for is not None
    assert message.scheduled_send_job_id is not None

    # The fire job is deferred (perform_at), not run immediately.
    scheduled = background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)
    assert len(scheduled) == 1
    assert abs((scheduled[0].perform_at - scheduled_for).total_seconds()) < 1
    assert not background_jobs.has_completed_job(ScheduledDraftSendJob)
    assert scheduled[0].id == message.scheduled_send_job_id

    # The persisted body HTML is exposed so the read-only scheduled preview can render it
    # through the same path as sent mail.
    assert "Body text" in response.json()["body_html"]
    envelope = (await client.get(f"/api/email_threads/{draft.thread_id}/draft")).json()
    assert envelope["scheduled_for"]
    assert "Body text" in envelope["body_html"]


@pytest.mark.asyncio
async def test_schedule_rejects_naive_datetime(client: AppClient, email_client: FakeEmailClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user)

    response = await client.post(
        f"/api/email_threads/{draft.thread_id}/draft/schedule",
        json={
            "to": ["recipient@example.com"],
            "message_body": "Body",
            "scheduled_for": datetime.now().replace(tzinfo=None).isoformat(),  # naive
        },
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_schedule_rejects_past_and_beyond_horizon(client: AppClient, email_client: FakeEmailClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user)

    past = await _schedule(client, draft.thread_id, datetime.now(UTC) - timedelta(minutes=1))
    assert past.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    too_far = await _schedule(client, draft.thread_id, datetime.now(UTC) + timedelta(days=31))
    assert too_far.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_scheduled_draft_cannot_be_edited_or_sent_now(client: AppClient, email_client: FakeEmailClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    assert (await _schedule(client, draft.thread_id, _future())).status_code == status.HTTP_202_ACCEPTED

    edit = await client.patch(f"/api/email_threads/{draft.thread_id}/draft", json={"subject": "New"})
    assert edit.status_code == status.HTTP_409_CONFLICT

    send_now = await client.post(
        f"/api/email_threads/{draft.thread_id}/draft/send",
        json={"to": ["recipient@example.com"], "message_body": "Body text"},
    )
    assert send_now.status_code == status.HTTP_409_CONFLICT

    # Scheduling again while already scheduled is a conflict.
    again = await _schedule(client, draft.thread_id, _future())
    assert again.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_unschedule_returns_to_editable_and_cancels_job(
    client: AppClient, email_client: FakeEmailClient, background_jobs
):
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    assert (await _schedule(client, draft.thread_id, _future())).status_code == status.HTTP_202_ACCEPTED
    assert background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)

    response = await client.post(f"/api/email_threads/{draft.thread_id}/draft/unschedule")
    assert response.status_code == status.HTTP_200_OK

    message = await EmailMessage.get(id=draft.id)
    assert message.message_type == EmailMessageType.DRAFT
    assert message.scheduled_for is None
    assert message.scheduled_send_job_id is None
    # cancel_job removed the pending Cloud Task from the runner.
    assert not background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)

    # Editable again.
    edit = await client.patch(f"/api/email_threads/{draft.thread_id}/draft", json={"subject": "Edited"})
    assert edit.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_schedule_and_unschedule_update_mailbox_row_via_event(
    client: AppClient, email_client: FakeEmailClient, background_jobs, monkeypatch
):
    # scheduled_for lives on the message, not the mailbox row, so a plain change-gated sync stays
    # silent. Scheduling records a DRAFT_SCHEDULED workspace event via Notifier.record_and_notify
    # instead; the event-driven SyncMailboxJob pins it on the row's last_event (a real column
    # change), so the row broadcasts and the list re-renders — a mailbox update that's a product of
    # an event, no forced row push. record_and_notify must stay silent for these actions: an email
    # thread is EmailDelivery.SKIP and DRAFT_SCHEDULED/UNSCHEDULED are outside its push policy, so a
    # collaborator gets the inbox refresh but no push or email. Guard that with a subscribed
    # collaborator and push enabled — a policy regression would surface a push/email job here.
    user = await client.get_default_user()
    collaborator = await create_user(email="collaborator@convictional.com", organization_id=user.organization_id)
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    thread = await EmailThread.get(id=draft.thread_id)
    await thread.fetch_related("workspace")
    await thread.collaboration.add(collaborator, user)
    await create_push_subscription(user_id=collaborator.id)
    monkeypatch.setattr(settings, "push_enabled", True)
    # Materialize the Drafts row first so it already exists and is unchanged when we schedule.
    await Mailbox.sync(thread)
    entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=user.id)

    broadcast_entry_ids: list[UUID] = []

    async def fake_broadcast(self: MailboxSync) -> None:
        broadcast_entry_ids.append(self.entry_id)

    monkeypatch.setattr(MailboxSync, "broadcast", fake_broadcast)

    broadcast_entry_ids.clear()
    # Only jobs from the schedule/unschedule calls should be judged for silence, not the
    # collaborator-add above.
    background_jobs.reset()
    assert (await _schedule(client, draft.thread_id, _future())).status_code == status.HTTP_202_ACCEPTED
    assert entry.id in broadcast_entry_ids
    scheduled = await MailboxEntry.get(id=entry.id).prefetch_related("last_event")
    assert scheduled.last_event is not None
    assert scheduled.last_event.action == EventAction.DRAFT_SCHEDULED

    broadcast_entry_ids.clear()
    unschedule = await client.post(f"/api/email_threads/{draft.thread_id}/draft/unschedule")
    assert unschedule.status_code == status.HTTP_200_OK
    assert entry.id in broadcast_entry_ids
    unscheduled = await MailboxEntry.get(id=entry.id).prefetch_related("last_event")
    assert unscheduled.last_event is not None
    assert unscheduled.last_event.action == EventAction.DRAFT_UNSCHEDULED

    # Silent throughout: neither schedule nor unschedule notified the collaborator.
    assert not background_jobs.has_completed_job(SendEventPushJob)
    assert not background_jobs.has_completed_job(SendEventEmailJob)


@pytest.mark.asyncio
async def test_unschedule_requires_scheduled_draft(client: AppClient, email_client: FakeEmailClient):
    user = await client.get_default_user()
    draft = await _seed_draft(user)

    response = await client.post(f"/api/email_threads/{draft.thread_id}/draft/unschedule")
    assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_scheduled_job_fires_and_delivers(client: AppClient, email_client: FakeEmailClient, background_jobs):
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    assert (await _schedule(client, draft.thread_id, _future())).status_code == status.HTTP_202_ACCEPTED

    [job] = background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)
    await job.run()

    message = await EmailMessage.get(id=draft.id)
    assert message.message_type == EmailMessageType.SENT
    assert message.scheduled_for is None


@pytest.mark.asyncio
async def test_scheduled_send_with_archive_archives_sender_entry(
    client: AppClient, email_client: FakeEmailClient, background_jobs
):
    """Scheduling with should_archive=True archives the sender's mailbox entry when the job fires.
    apply_send_side_effects runs inside the fire job's transaction, so this guards that using_db path."""
    creator = await create_user(email="creator@convictional.com")
    assignee = await create_user(email="assignee@convictional.com", organization_id=creator.organization_id)
    draft_message = await create_email_message(
        user_id=creator.id,
        creator_id=creator.id,
        organization_id=creator.organization_id,
        message_type=EmailMessageType.DRAFT,
        subject="Shared Thread",
        body_plain="My reply",
        to=["recipient@example.com"],
        external_thread_id=None,
        labels=[EmailLabel.DRAFT],
    )
    thread = await draft_message.thread.get()
    await thread.fetch_related("workspace")
    await thread.collaboration.add(assignee, creator)
    await thread.collaboration.assign_to(assignee, creator)
    await Mailbox.sync(thread)

    client.current_user = creator
    response = await _schedule(client, thread.id, _future(), should_archive=True)
    assert response.status_code == status.HTTP_202_ACCEPTED

    [job] = background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)
    await job.run()

    message = await EmailMessage.get(id=draft_message.id)
    assert message.message_type == EmailMessageType.SENT

    creator_entry = await MailboxEntry.filter(
        MailboxEntry.filters.by_resource(thread.global_id),
        MailboxEntry.filters.by_owner(creator.id),
    ).first()
    assert creator_entry is not None
    assert creator_entry.is_archived


@pytest.mark.asyncio
async def test_scheduled_send_keeps_archived_entry_out_of_inbox(
    client: AppClient, email_client: FakeEmailClient, background_jobs
):
    """Archiving a thread between scheduling and the fire must stand: the sent draft surfaces in
    Sent (SENT label) without resurrecting the entry into the inbox. Immediate sends still pin to
    inbox (test_send_without_archive_keeps_thread_in_inbox); this guards the deferred opt-out."""
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    thread = await EmailThread.get(id=draft.thread_id)

    assert (await _schedule(client, draft.thread_id, _future())).status_code == status.HTTP_202_ACCEPTED

    # Archive the sender's entry after scheduling but before the fire.
    await Mailbox.sync(thread)
    entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=user.id)
    await entry.archive()
    assert entry.is_archived

    [job] = background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)
    await job.run()

    message = await EmailMessage.get(id=draft.id)
    assert message.message_type == EmailMessageType.SENT

    # The entry stays archived — the send did not pin it back to the inbox — and now carries the
    # SENT label, so it surfaces in Sent (the only view it should appear in once sent).
    await entry.refresh_from_db()
    assert entry.is_archived
    assert not entry.is_inbox
    assert EmailMailboxLabel.SENT in entry.labels


@pytest.mark.asyncio
async def test_unschedule_then_fire_is_noop(client: AppClient, email_client: FakeEmailClient, background_jobs):
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    assert (await _schedule(client, draft.thread_id, _future())).status_code == status.HTTP_202_ACCEPTED

    # Capture the job before unscheduling cancels it, then simulate it firing anyway.
    [job] = background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)
    assert (await client.post(f"/api/email_threads/{draft.thread_id}/draft/unschedule")).status_code == 200

    await job.run()

    message = await EmailMessage.get(id=draft.id)
    assert message.message_type == EmailMessageType.DRAFT
    assert message.scheduled_for is None


@pytest.mark.asyncio
async def test_unschedule_after_fire_is_rejected(client: AppClient, email_client: FakeEmailClient, background_jobs):
    user = await client.get_default_user()
    draft = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    assert (await _schedule(client, draft.thread_id, _future())).status_code == status.HTTP_202_ACCEPTED

    [job] = background_jobs.all_scheduled_jobs_by_type(ScheduledDraftSendJob)
    await job.run()  # delivers → SENT

    # Once fired there is no longer a DRAFT to unschedule, so the draft lookup 404s before the
    # endpoint's own guard — either way, unschedule can't undo a completed send.
    response = await client.post(f"/api/email_threads/{draft.thread_id}/draft/unschedule")
    assert response.status_code == status.HTTP_404_NOT_FOUND


async def _make_scheduled_draft(client: AppClient, scheduled_for: datetime) -> EmailMessage:
    """Directly put a draft into the scheduled state (bypassing the endpoint's future-time guard so
    a test can create an already-overdue one)."""
    user = await client.get_default_user()
    draft_message = await _seed_draft(user, to=["recipient@example.com"], body_plain="Body text")
    thread = await EmailThread.get(id=draft_message.thread_id).prefetch_related("messages", "workspace")
    await Mailbox.sync(thread)
    draft = await thread.get_draft()
    assert draft is not None
    await thread.mark_draft_scheduled(draft, scheduled_for, uuid4(), user)
    return draft_message


@pytest.mark.asyncio
async def test_sweep_refires_overdue_scheduled_draft(
    client: AppClient, email_client: FakeEmailClient, background_jobs
):
    # A scheduled draft whose fire time passed long ago (its Cloud Task was lost) is re-fired.
    draft_message = await _make_scheduled_draft(client, datetime.now(UTC) - timedelta(hours=1))

    sweep = await enqueue_job(SweepOverdueScheduledDraftsJob())
    await sweep.run()

    message = await EmailMessage.get(id=draft_message.id)
    assert message.message_type == EmailMessageType.SENT
    assert message.scheduled_for is None


@pytest.mark.asyncio
async def test_sweep_ignores_not_yet_due_scheduled_draft(
    client: AppClient, email_client: FakeEmailClient, background_jobs
):
    # A draft still within its window (or before the grace) must not be touched.
    draft_message = await _make_scheduled_draft(client, datetime.now(UTC) + timedelta(days=1))

    sweep = await enqueue_job(SweepOverdueScheduledDraftsJob())
    await sweep.run()

    message = await EmailMessage.get(id=draft_message.id)
    assert message.message_type == EmailMessageType.DRAFT
    assert message.scheduled_for is not None
