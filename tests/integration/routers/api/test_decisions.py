from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import status

from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Attachment, Decision, Event, Mention, SubscriptionPreference
from app.models.workspaces.chat import ChatMailboxEntry
from app.models.workspaces.documents import Document, DocumentComment
from app.models.workspaces.email.mailbox import EmailMailboxEntry
from app.models.workspaces.email.thread import EmailThreadComment
from app.models.workspaces.posts import PostComment, PostDraftComment
from config.enums import EventAction, Sharing, SubscriptionLevel
from infra.db import GlobalID
from infra.email import FakeDelivery
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_chat,
    create_chat_message,
    create_collaborator,
    create_decision,
    create_document,
    create_email_thread,
    create_email_thread_comment,
    create_post,
    create_post_comment,
    create_user,
)


@pytest.mark.asyncio
async def test_decision_crud_and_duplicate(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="Ship it on Tuesday")

    # Create
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
    )
    assert response.status_code == status.HTTP_201_CREATED
    body = response.json()
    assert body["comment_gid"] == str(comment.global_id)
    assert body["comment_preview"] == "Ship it on Tuesday"
    assert body["decided_by"]["id"] == str(creator.id)
    assert body["decided_at"] is not None
    decision_id = body["id"]

    # Duplicate on the same comment → 409, exactly one row
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert await Decision.filter(comment_gid=comment.global_id).count() == 1

    # Multiple decisions per workspace, on different comments
    second_comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="Also hire Bob")
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(second_comment.global_id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    # List envelope
    response = await client.get(f"/api/workspaces/{post.workspace_id}/decisions")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["next_cursor"] is None
    assert body["has_more"] is False
    assert {d["comment_preview"] for d in body["decisions"]} == {"Ship it on Tuesday", "Also hire Bob"}

    # Delete
    response = await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await Decision.get_or_none(id=decision_id) is None

    response = await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision_id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_decision_on_soft_deleted_email_thread_comment_renders_tombstone(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_email_thread_comment(
        email_thread_id=thread.id, user_id=creator.id, content="Ship on Friday"
    )
    await create_decision(workspace_id=thread.workspace_id, comment=comment, decided_by_id=creator.id)

    # Before deletion the decision renders its anchor's content.
    response = await client.get(f"/api/workspaces/{thread.workspace_id}/decisions")
    assert response.json()["decisions"][0]["comment_preview"] == "Ship on Friday"

    # Soft-deleting the anchor comment must not drop the decision: the list resolves soft-deleted
    # anchors (unscoped) and renders them as tombstones (comment_preview None) rather than dropping
    # the row. Email comments only reach this path now that they're soft-deletable, not hard-deleted.
    await comment.soft_delete()

    response = await client.get(f"/api/workspaces/{thread.workspace_id}/decisions")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert [d["comment_gid"] for d in body["decisions"]] == [str(comment.global_id)]
    assert body["decisions"][0]["comment_preview"] is None


@pytest.mark.asyncio
async def test_create_rejects_invalid_comment_gids(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    # Comment belonging to another workspace
    other_post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    foreign_comment = await create_post_comment(post_id=other_post.id, user_id=creator.id)
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(foreign_comment.global_id)}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # A real record that isn't a comment
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(post.global_id)}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # A CommentMixin type outside the allowlist: draft-review comments are
    # visible to a narrower audience than workspace access.
    draft_comment = await PostDraftComment.create(
        content="Reviewer-only note",
        quoted_text="quoted",
        comment_mark_id="mark-1",
        post_id=post.id,
        user_id=creator.id,
    )
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(draft_comment.global_id)}
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # A real comment but with a foreign app name — GlobalID equality includes
    # app_name, so storing it would permanently orphan the decision.
    own_comment = await create_post_comment(post_id=post.id, user_id=creator.id)
    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions",
        json={"comment_gid": f"gid://other-app/PostComment/{own_comment.id}"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND

    # Garbage gids: unparseable, unknown type, nonexistent comment
    for gid in ["not-a-gid", "gid://convictional/Banana/123", f"gid://convictional/PostComment/{uuid4()}"]:
        response = await client.post(f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": gid})
        assert response.status_code == status.HTTP_404_NOT_FOUND, gid

    assert await Decision.filter(workspace_id=post.workspace_id).count() == 0


@pytest.mark.asyncio
async def test_authz_recording_open_clearing_restricted(client: AppClient):
    creator = await client.get_default_user()
    decider = await create_user(organization_id=creator.organization_id)
    admin = await create_user(organization_id=creator.organization_id, is_admin=True)
    bystander = await create_user(organization_id=creator.organization_id)

    # Org-shared post: recording is reaction-grade — any org member can mark a
    # decision, even on someone else's comment.
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id)
    with client.current_user_as(decider):
        response = await client.post(
            f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["decided_by"]["id"] == str(decider.id)
        decision_id = response.json()["id"]

    # Clearing is restricted: a member who isn't the decider can't undecide it,
    # even with workspace access — 403, not 404, since they can already see it.
    with client.current_user_as(bystander):
        response = await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision_id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN
    assert await Decision.get_or_none(id=decision_id) is not None

    # An org admin can clear anyone's decision.
    with client.current_user_as(admin):
        response = await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision_id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await Decision.get_or_none(id=decision_id) is None

    # The decider can clear their own decision.
    with client.current_user_as(decider):
        response = await client.post(
            f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
        )
        own_decision_id = response.json()["id"]
        response = await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{own_decision_id}")
        assert response.status_code == status.HTTP_204_NO_CONTENT

    # Private document: a non-collaborator is blocked by the get_workspace gate
    # on every verb (404, never 403 — they shouldn't learn the workspace exists).
    document = await create_document(
        creator_id=creator.id, organization_id=creator.organization_id, sharing=Sharing.PRIVATE
    )
    document_comment = await DocumentComment.create(
        content="Pick option B",
        quoted_text="quoted",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=creator.id,
    )
    with client.current_user_as(bystander):
        response = await client.post(
            f"/api/workspaces/{document.workspace_id}/decisions",
            json={"comment_gid": str(document_comment.global_id)},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND
        response = await client.get(f"/api/workspaces/{document.workspace_id}/decisions")
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_create_records_event_and_notifies_like_a_comment(client: AppClient, email_delivery: FakeDelivery):
    creator = await client.get_default_user()
    subscriber = await create_user(organization_id=creator.organization_id)
    document = await create_document(
        creator_id=creator.id, organization_id=creator.organization_id, sharing=Sharing.ORGANIZATION
    )
    await create_collaborator(workspace_id=document.workspace_id, user_id=subscriber.id)
    await SubscriptionPreference.update_for(subscriber.id, {Document.record_type: SubscriptionLevel.ALL})
    comment = await DocumentComment.create(
        content="Go with option B",
        quoted_text="quoted",
        comment_mark_id="mark-1",
        document_id=document.id,
        user_id=creator.id,
    )

    response = await client.post(
        f"/api/workspaces/{document.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    events = await Event.filter(workspace_id=document.workspace_id, action=EventAction.DECIDED)
    assert len(events) == 1
    assert events[0].creator_id == creator.id
    # The event stashes the decided comment's GID param so the email CTA can deep-link to it.
    assert events[0].details["comment_gid"] == comment.global_id.to_param

    # Subscriber is notified along the comment contours; the actor is excluded.
    # The email carries the decided comment's body via event details.
    assert len(email_delivery.by_recipient(subscriber.email)) == 1
    email_html = email_delivery.by_recipient(subscriber.email)[0].html
    assert "marked a decision on the document" in email_html
    assert "Go with option B" in email_html
    assert len(email_delivery.by_recipient(creator.email)) == 0
    # The CTA is the only /gid/ link in the body, so these assertions pin its
    # target: it deep-links through the decided comment GID, not the bare document.
    assert f"/gid/{comment.global_id.to_param}" in email_html
    assert f"/gid/{document.global_id.to_param}" not in email_html


@pytest.mark.asyncio
async def test_delete_is_silent(client: AppClient, email_delivery: FakeDelivery):
    # Clearing records no event and sends no notification; the channel signal
    # it does fire is covered in tests/integration/channels/test_decisions.py.
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id)
    decision = await create_decision(post.workspace_id, comment, decided_by_id=creator.id)
    email_delivery.reset()

    response = await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision.id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    assert await Event.filter(workspace_id=post.workspace_id, action=EventAction.DECIDED).count() == 0
    assert len(email_delivery.messages) == 0


@pytest.mark.asyncio
async def test_chat_decision_surfaces_in_recipient_inbox(client: AppClient):
    # Marking a decision on a chat message routes "like a new comment": the
    # recipient's chat re-surfaces as unread even though the decision creates no
    # new message. The decider's own row is untouched, and clearing a decision is
    # silent — a row read before the clear stays read.
    arjun = await client.get_default_user()
    jordan = await create_user(organization_id=arjun.organization_id)
    chat = await create_chat(organization_id=arjun.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=arjun.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=jordan.id)
    await chat.workspace.subscribe(jordan.id)

    message = await create_chat_message(chat_id=chat.id, user_id=arjun.id, content="Ship it Friday")

    # Both have already seen the chat — existing, read inbox rows.
    await chat.refresh_from_db()
    await ChatMailboxEntry.from_resource(chat).mark_as_read(jordan)
    await ChatMailboxEntry.from_resource(chat).mark_as_read(arjun)
    jordan_entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=jordan.id)
    arjun_entry = await MailboxEntry.get(resource_gid=str(chat.global_id), owner_id=arjun.id)
    assert not jordan_entry.is_unread
    assert not arjun_entry.is_unread

    response = await client.post(
        f"/api/workspaces/{chat.workspace_id}/decisions", json={"comment_gid": str(message.global_id)}
    )
    assert response.status_code == status.HTTP_201_CREATED
    decision_id = response.json()["id"]

    # The recipient re-surfaces as unread; the decider's own row stays read.
    await jordan_entry.refresh_from_db()
    await arjun_entry.refresh_from_db()
    assert jordan_entry.is_inbox
    assert jordan_entry.is_unread
    assert not arjun_entry.is_unread

    # Clearing the decision creates no event, so it never resurfaces a read row.
    await ChatMailboxEntry.from_resource(chat).mark_as_read(jordan)
    delete_response = await client.delete(f"/api/workspaces/{chat.workspace_id}/decisions/{decision_id}")
    assert delete_response.status_code == status.HTTP_204_NO_CONTENT

    await jordan_entry.refresh_from_db()
    assert not jordan_entry.is_unread


@pytest.mark.asyncio
async def test_email_thread_anchors_to_internal_comment(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, organization_id=thread.organization_id
    )

    response = await client.post(
        f"/api/workspaces/{thread.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    response = await client.get(f"/api/workspaces/{thread.workspace_id}/decisions")
    assert [d["comment_preview"] for d in response.json()["decisions"]] == [comment.content]


@pytest.mark.asyncio
async def test_email_thread_comment_global_id_round_trips_after_rename(client: AppClient):
    # record_type is the class name and GIDs persist as strings, so a comment's own GID and
    # every stored reference to it (decision anchor, attachment, mention) must resolve back to
    # the model — renaming the model class otherwise dangles all of them.
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, user_id=creator.id, organization_id=thread.organization_id
    )

    assert comment.record_type == "EmailThreadComment"
    assert str(comment.global_id) == f"gid://convictional/EmailThreadComment/{comment.id}"

    resolved = await GlobalID.parse(str(comment.global_id)).get_or_none()
    assert isinstance(resolved, EmailThreadComment)
    assert resolved.id == comment.id

    decision = await create_decision(thread.workspace_id, comment)
    assert (await Decision.get(comment_gid=comment.global_id)).id == decision.id

    attachment = await create_attachment(
        workspace_id=thread.workspace_id, user_id=creator.id, comment_gid=comment.global_id
    )
    assert (await Attachment.get(comment_gid=comment.global_id)).id == attachment.id

    mention = await Mention.create(
        recordable_gid=comment.global_id,
        content="hi @[someone]",
        mentioned_id=creator.id,
        creator_id=creator.id,
        workspace_id=thread.workspace_id,
    )
    assert (await Mention.get(recordable_gid=comment.global_id)).id == mention.id


@pytest.mark.asyncio
async def test_email_thread_decision_surfaces_in_recipient_inbox(client: AppClient):
    # Email-thread inbox surfacing is event-driven (`_sync_activity_tracking` reads
    # `last_event_by_others`), so a DECIDED mark re-surfaces a collaborator's
    # already-read thread as unread — like posts — with no email-specific code.
    # The decider's own row is untouched (actor excluded from "by others").
    arjun = await client.get_default_user()
    jordan = await create_user(organization_id=arjun.organization_id)
    thread = await create_email_thread(creator_id=arjun.id, organization_id=arjun.organization_id)
    # The creator is already a collaborator; add the recipient.
    await create_collaborator(workspace_id=thread.workspace_id, user_id=jordan.id)
    comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, organization_id=thread.organization_id
    )

    # Establish read inbox rows for both collaborators (non-new, so the next
    # event's newer timestamp registers as fresh activity). The initial sync
    # leaves the creator's own row read; only the recipient needs marking read.
    await EmailMailboxEntry.from_resource(thread).sync()
    await EmailMailboxEntry.from_resource(thread).mark_as_read(jordan)
    jordan_entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=jordan.id)
    arjun_entry = await MailboxEntry.get(resource_gid=str(thread.global_id), owner_id=arjun.id)
    assert not jordan_entry.is_unread
    assert not arjun_entry.is_unread

    response = await client.post(
        f"/api/workspaces/{thread.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
    )
    assert response.status_code == status.HTTP_201_CREATED

    # The recipient re-surfaces as unread; the decider's own row stays read.
    await jordan_entry.refresh_from_db()
    await arjun_entry.refresh_from_db()
    assert jordan_entry.is_inbox
    assert jordan_entry.is_unread
    assert not arjun_entry.is_unread


@pytest.mark.asyncio
async def test_list_tombstones_soft_deleted_and_skips_orphaned_anchors(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    live_comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="Keep me")
    deleted_comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="Unsend me")
    await create_decision(post.workspace_id, live_comment, decided_by_id=creator.id)
    await create_decision(post.workspace_id, deleted_comment, decided_by_id=creator.id)

    # Soft-deleted anchor → decision retained, preview tombstoned (null)
    await deleted_comment.soft_delete()

    # Orphaned anchor (cleanup hasn't swept it) → row skipped, never a 500
    await Decision.create(
        workspace_id=post.workspace_id,
        comment_gid=GlobalID.create(PostComment.record_type, uuid4()),
        decided_by_id=creator.id,
        decided_at=datetime.now(UTC),
    )

    response = await client.get(f"/api/workspaces/{post.workspace_id}/decisions")
    assert response.status_code == status.HTTP_200_OK
    previews = {d["comment_gid"]: d["comment_preview"] for d in response.json()["decisions"]}
    assert previews == {
        str(live_comment.global_id): "Keep me",
        str(deleted_comment.global_id): None,
    }


@pytest.mark.asyncio
async def test_post_index_decision_badge_reflects_decisions(client: AppClient):
    # The posts-index card's decision badge is sourced from the PostListResponse
    # `decisions` envelope (no legacy Post columns): recording a decision surfaces
    # the post there with the decided comment's preview; clearing removes it.
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_post_comment(post_id=post.id, user_id=creator.id, content="The decision")
    second = await create_post_comment(post_id=post.id, user_id=creator.id, content="Another decision")

    response = await client.post(
        f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(comment.global_id)}
    )
    decision_id = response.json()["id"]

    # One decision: count 1 + the preview.
    body = (await client.get("/api/posts")).json()
    decisions = {d["post_id"]: d for d in body["decisions"]}
    assert decisions[str(post.id)]["count"] == 1
    assert decisions[str(post.id)]["comment_preview"] == "The decision"
    # The decided post is included by the ?decided=true filter.
    decided_body = (await client.get("/api/posts?decided=true")).json()
    assert str(post.id) in {p["id"] for p in decided_body["posts"]}

    # A second decision bumps the count (the card renders "N decisions" then).
    await client.post(f"/api/workspaces/{post.workspace_id}/decisions", json={"comment_gid": str(second.global_id)})
    body = (await client.get("/api/posts")).json()
    assert {d["post_id"]: d["count"] for d in body["decisions"]}[str(post.id)] == 2

    # Deleting the first decision leaves the second as the latest 1-of-N projection.
    await client.delete(f"/api/workspaces/{post.workspace_id}/decisions/{decision_id}")
    body = (await client.get("/api/posts")).json()
    remaining = {d["post_id"]: d for d in body["decisions"]}[str(post.id)]
    assert remaining["count"] == 1
    assert remaining["comment_preview"] == "Another decision"
