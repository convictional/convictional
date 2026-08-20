from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.collaboration.workspace import Event
from app.models.workspaces.email.thread import EmailThread, EmailThreadComment
from app.routers.api.email_threads import MAX_BATCH_CONTENT_IDS
from config.enums import EmailMessageType, EventAction
from lib.html import sanitize_email_html_content
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_collaborator,
    create_content,
    create_email_draft,
    create_email_message,
    create_user,
)


async def _fresh_thread(client: AppClient):
    user = await client.get_default_user()
    message = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        subject="Show endpoint thread",
    )
    await message.fetch_related("thread")
    await Mailbox.sync(message.thread)
    mailbox = Mailbox(user=user)
    await mailbox.mark_as_unread(message.thread)
    return user, message


@pytest.mark.asyncio
async def test_show_returns_full_envelope(client: AppClient):
    user, message = await _fresh_thread(client)

    response = await client.get(f"/api/email_threads/{message.thread_id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    assert body["thread"]["id"] == str(message.thread_id)
    assert body["thread"]["title"]
    assert body["thread"]["creator"]["id"] == str(user.id)
    assert body["thread"]["is_shared"] is False
    assert body["thread"]["own_thread_id"] is None

    assert body["mailbox_entry"]["is_unread"] is True
    assert body["mailbox_entry"]["is_archived"] is False

    assert len(body["timeline"]) >= 1
    first = body["timeline"][0]
    assert first["type"] == "message"
    assert first["message"]["id"] == str(message.id)
    assert first["message"]["sender_email"] == "john@example.com"
    assert first["message"]["content_url"].endswith(f"/email_messages/{message.id}/content")
    # The timeline is a metadata-only summary: no body fields on the wire at all.
    assert "content_html" not in first["message"]
    assert "body_plain" not in first["message"]
    assert "attachments" not in first["message"]

    assert body["draft"] is None
    assert body["comments"] == []


@pytest.mark.asyncio
async def test_show_access_gating(client: AppClient):
    """A same-org non-collaborator gets 403 with a request_access_url (the client
    turns this into a request-access CTA — the server-side page redirect is gone
    now the SPA shell serves the page unconditionally). A cross-org viewer gets a
    plain 404 that doesn't leak the thread's existence."""
    user, message = await _fresh_thread(client)

    same_org = await create_user(organization_id=user.organization_id)
    with client.current_user_as(same_org):
        response = await client.get(f"/api/email_threads/{message.thread_id}")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["request_access_url"]

    other_org = await create_user()
    with client.current_user_as(other_org):
        response = await client.get(f"/api/email_threads/{message.thread_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_show_includes_structured_events(client: AppClient):
    user, message = await _fresh_thread(client)
    await message.thread.fetch_related("workspace")
    workspace = message.thread.workspace

    async with workspace.record(EventAction.ASSIGNED, creator_id=user.id) as recording:
        recording.event.details = {"assignee": {"name": "Ada Lovelace", "email": "ada@example.com"}}
    async with workspace.record(EventAction.ADDED_COLLABORATOR, creator_id=user.id) as recording:
        recording.event.details = {"collaborator": {"email": "grace@example.com"}, "reason": "to review."}
    # An action with no structured detail payload -> details is None.
    async with workspace.record(EventAction.REMOVED_COLLABORATOR, creator_id=user.id):
        pass

    response = await client.get(f"/api/email_threads/{message.thread_id}")
    body = response.json()

    events = [t["event"] for t in body["timeline"] if t["type"] == "event"]

    assigned = next(e for e in events if e["action"] == EventAction.ASSIGNED.value)
    assert assigned["details"] == {"type": "assigned", "subject_label": "Ada Lovelace"}

    collaborator = next(e for e in events if e["action"] == EventAction.ADDED_COLLABORATOR.value)
    assert collaborator["details"] == {
        "type": "added_collaborator",
        "subject_label": "grace@example.com",
        "reason": "to review.",
    }

    removed = next(e for e in events if e["action"] == EventAction.REMOVED_COLLABORATOR.value)
    assert removed["details"] is None

    assert body["last_event_id"] == events[-1]["id"]


@pytest.mark.asyncio
async def test_show_drops_commented_events_but_keeps_native_comment(client: AppClient):
    user, message = await _fresh_thread(client)
    await message.thread.fetch_related("workspace")
    comment = EmailThreadComment(email_thread_id=message.thread.id, user_id=user.id, content="hello there")
    async with message.thread.workspace.record(
        EventAction.COMMENTED, recordable=comment, creator_id=user.id
    ) as recording:
        await comment.save(recording.using_db)

    response = await client.get(f"/api/email_threads/{message.thread_id}")
    body = response.json()

    # The "commented" activity event is dropped from the timeline — the comment renders
    # natively from `comments` instead, so leaving it in would double-render.
    event_actions = [t["event"]["action"] for t in body["timeline"] if t["type"] == "event"]
    assert EventAction.COMMENTED.value not in event_actions
    assert [c["id"] for c in body["comments"]] == [str(comment.id)]

    # The Event row still exists, so notifications/feeds are unaffected.
    assert await Event.filter(workspace_id=message.thread.workspace_id, action=EventAction.COMMENTED).count() == 1


@pytest.mark.asyncio
async def test_message_content_endpoint(client: AppClient):
    _, message = await _fresh_thread(client)

    response = await client.get(f"/api/email_threads/{message.thread_id}/email_messages/{message.id}/content")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert "Hello world" in body["content_html"]
    assert body["attachments"] == []


@pytest.mark.asyncio
async def test_content_sanitizes_all_types_preserving_authored_whitespace(client: AppClient):
    # The display path ALWAYS sanitizes body_html — it never trusts stored HTML, because
    # authored-typed messages can enter via Gmail sync with raw, never-sanitized bytes.
    # Authored messages (SENT/SENDING/DRAFT) sanitize with the whitespace-preserving config,
    # so intentional whitespace survives and re-sanitizing already-clean HTML is byte-stable.
    # RECEIVED sanitizes with the default whitespace-stripping config — the security boundary.
    user, received = await _fresh_thread(client)

    # Body carrying whitespace the DEFAULT config would mangle: 4 consecutive newlines
    # (collapses to 2) and an indented line (leading run stripped). The stored authored body
    # is what compose produced — the output of the whitespace-preserving sanitizer.
    raw_authored = "<div>hi</div>\n\n\n\n<div>a   b</div>\n    <div>indented</div><div><br></div>"
    authored_html = sanitize_email_html_content(raw_authored, preserve_whitespace=True)
    stripped = sanitize_email_html_content(raw_authored, preserve_whitespace=False)
    # The preserving config actually keeps whitespace the default config strips — otherwise
    # this test would pass for the wrong reason.
    assert "\n\n\n\n" in authored_html
    assert "\n\n\n\n" not in stripped

    sent = await create_email_message(
        creator_id=user.id,
        user_id=user.id,
        organization_id=user.organization_id,
        thread_id=received.thread_id,
        message_type=EmailMessageType.SENT,
        body_html=authored_html,
    )

    sent_content = await client.get(f"/api/email_threads/{received.thread_id}/email_messages/{sent.id}/content")
    assert sent_content.status_code == status.HTTP_200_OK
    returned = sent_content.json()["content_html"]
    # Idempotent: re-sanitizing already-sanitized authored HTML is byte-stable (no
    # attachments, so the CID rewrite is a no-op), so whitespace fidelity is preserved.
    assert returned == authored_html
    assert "\n\n\n\n" in returned

    # A SENT message can arrive via Gmail sync carrying raw, hostile HTML (Gmail labels drive
    # message_type). The display path must scrub it despite the authored type — the hole the
    # old trust-on-display logic left open. The factory stores non-RECEIVED body_html verbatim.
    hostile = await create_email_message(
        creator_id=user.id,
        user_id=user.id,
        organization_id=user.organization_id,
        thread_id=received.thread_id,
        message_type=EmailMessageType.SENT,
        body_html="<div>ok</div><script>alert('xss')</script><img src=x onerror=alert(1)>",
    )
    hostile_content = await client.get(f"/api/email_threads/{received.thread_id}/email_messages/{hostile.id}/content")
    assert hostile_content.status_code == status.HTTP_200_OK
    hostile_returned = hostile_content.json()["content_html"]
    assert "<script" not in hostile_returned
    assert "alert" not in hostile_returned
    assert "onerror" not in hostile_returned
    assert "ok" in hostile_returned

    # RECEIVED body stored raw (bypass the factory's inbound processing) with hostile
    # markup + strippable whitespace; the display path must sanitize it.
    received.body_html = "<div>safe</div><script>alert('xss')</script>\n\n\n<div>tail</div>"
    await received.save()

    received_content = await client.get(
        f"/api/email_threads/{received.thread_id}/email_messages/{received.id}/content"
    )
    assert received_content.status_code == status.HTTP_200_OK
    received_returned = received_content.json()["content_html"]
    # Disallowed tag and its content are removed, and the whitespace run is normalized.
    assert "<script" not in received_returned
    assert "alert" not in received_returned
    assert "\n\n\n" not in received_returned
    assert "safe" in received_returned
    assert "tail" in received_returned


@pytest.mark.asyncio
async def test_show_defers_all_message_content(client: AppClient):
    # Sanitizing email HTML is CPU-bound; the timeline is a metadata-only summary
    # that embeds no bodies regardless of read state or position. The client fetches
    # each body on demand via the content endpoint. This keeps a long thread from
    # blocking the worker and leaves the server with no view on client rendering.
    user = await client.get_default_user()
    now = datetime.now(UTC)
    older = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="defer_collapsed",
        body_html="<p>Older body</p>",
        received_at=now - timedelta(hours=1),
    )
    newer = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="defer_collapsed",
        body_html="<p>Newer body</p>",
        received_at=now,
    )
    assert older.thread_id == newer.thread_id
    thread = await EmailThread.get(id=older.thread_id)
    await Mailbox.sync(thread)

    response = await client.get(f"/api/email_threads/{thread.id}")
    assert response.status_code == status.HTTP_200_OK
    messages = {
        item["message"]["id"]: item["message"] for item in response.json()["timeline"] if item["type"] == "message"
    }

    # The timeline summary carries no body fields at all — not even for the newest
    # message. body, plain text, and attachments live only on the content sub-resource.
    for message in (older, newer):
        summary = messages[str(message.id)]
        assert "content_html" not in summary
        assert "body_plain" not in summary
        assert "attachments" not in summary

    # Each body is served by the per-message content endpoint on demand.
    for message, expected in ((older, "Older body"), (newer, "Newer body")):
        content = await client.get(f"/api/email_threads/{thread.id}/email_messages/{message.id}/content")
        assert content.status_code == status.HTTP_200_OK
        assert expected in content.json()["content_html"]


@pytest.mark.asyncio
async def test_batch_message_contents_endpoint(client: AppClient):
    # The client batch-fetches the bodies of the messages it renders expanded on load in
    # one request, instead of one request per message. The endpoint returns each requested
    # body keyed by id; unknown/cross-thread ids and drafts are omitted, and the timeline
    # stays body-free.
    user = await client.get_default_user()
    now = datetime.now(UTC)
    older = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="batch_contents",
        body_html="<p>Older body</p>",
        received_at=now - timedelta(hours=1),
    )
    newer = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="batch_contents",
        body_html="<p>Newer body</p>",
        received_at=now,
    )
    assert older.thread_id == newer.thread_id
    thread = await EmailThread.get(id=older.thread_id)
    await thread.fetch_related("creator")
    await Mailbox.sync(thread)
    # A draft on the same thread must never appear in the batch response.
    draft = await create_email_draft(thread_id=thread.id, user_id=user.id, organization_id=user.organization_id)
    # A message on a different thread the user can access must also be omitted: the endpoint
    # returns only ids belonging to the thread in the path, so a caller can't read another
    # thread's bodies by naming their ids here.
    other = await create_email_message(
        creator_id=user.id,
        organization_id=user.organization_id,
        external_thread_id="batch_contents_other",
        body_html="<p>Other thread body</p>",
        received_at=now,
    )
    assert other.thread_id != thread.id

    unknown_id = uuid4()
    params = f"ids={older.id}&ids={newer.id}&ids={draft.message.id}&ids={other.id}&ids={unknown_id}"
    response = await client.get(f"/api/email_threads/{thread.id}/email_message_contents?{params}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    by_id = {c["id"]: c for c in body["contents"]}
    # Only the two real, non-draft messages on this thread come back — the draft, the
    # cross-thread message, and the unknown id all drop out.
    assert set(by_id) == {str(older.id), str(newer.id)}
    assert str(other.id) not in by_id
    assert "Older body" in by_id[str(older.id)]["content_html"]
    assert "Newer body" in by_id[str(newer.id)]["content_html"]
    assert by_id[str(older.id)]["attachments"] == []
    assert body["has_more"] is False

    # No ids requested -> empty envelope, not an error.
    empty = await client.get(f"/api/email_threads/{thread.id}/email_message_contents")
    assert empty.status_code == status.HTTP_200_OK
    assert empty.json()["contents"] == []

    # More ids than the per-request cap is rejected — the client chunks to stay under it.
    too_many = "&".join(f"ids={uuid4()}" for _ in range(MAX_BATCH_CONTENT_IDS + 1))
    over = await client.get(f"/api/email_threads/{thread.id}/email_message_contents?{too_many}")
    assert over.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_ai_inclusion_toggle_propagates_state(client: AppClient):
    user, message = await _fresh_thread(client)
    thread = message.thread
    content = await create_content(
        organization_id=user.organization_id,
        source_id=str(thread.global_id),
    )
    entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=user.id)
    assert content.is_ai_excluded is False
    assert entry.is_ai_excluded is False

    response = await client.post(f"/api/email_threads/{thread.id}/exclude_from_ai")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await content.refresh_from_db()
    await entry.refresh_from_db()
    assert content.is_ai_excluded is True
    assert entry.is_ai_excluded is True

    response = await client.post(f"/api/email_threads/{thread.id}/include_in_ai")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    await content.refresh_from_db()
    await entry.refresh_from_db()
    assert content.is_ai_excluded is False
    assert entry.is_ai_excluded is False


@pytest.mark.asyncio
async def test_ai_inclusion_toggle_creator_only(client: AppClient):
    user, message = await _fresh_thread(client)

    # Non-creator collaborator gets 403.
    other = await create_user(organization_id=user.organization_id)
    await create_collaborator(
        user_id=other.id,
        workspace_id=message.thread.workspace_id,
        organization_id=user.organization_id,
    )
    with client.current_user_as(other):
        response = await client.post(f"/api/email_threads/{message.thread_id}/exclude_from_ai")
    assert response.status_code == status.HTTP_403_FORBIDDEN
