from urllib.parse import urljoin
from uuid import uuid4

import pytest
from fastapi import status

from app.jobs.content import IndexEmailThreadJob
from app.jobs.notifications import SendMentionJob
from app.jobs.push import SendMentionPushJob
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import Attachment, Collaborator, Event
from app.models.workspaces.email.thread import EmailThreadComment
from config import settings
from config.enums import EventAction, MailboxLabel
from infra.db import allow_soft_deleted
from infra.email import FakeDelivery
from infra.jobs import InlineJobs
from infra.push import FakePushDelivery
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_collaborator,
    create_email_thread,
    create_email_thread_comment,
    create_push_subscription,
    create_user,
)


@pytest.mark.asyncio
async def test_email_thread_comment_crud(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    # GET empty list — envelope shape
    response = await client.get(f"/api/email_threads/{thread.id}/comments")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"comments": [], "next_cursor": None, "has_more": False}

    # POST create — 201 with full body
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "First comment"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["content"] == "First comment"
    assert data["user"]["id"] == str(creator.id)
    assert data["user"]["display_name"] == creator.display_name
    assert data["reactions"] == {}
    assert data["created_at"] is not None
    assert data["updated_at"] is not None
    assert data["link_preview"] is None
    assert data["attachments"] == []
    comment_id = data["id"]

    # Create records a COMMENTED event and reindexes the thread.
    assert await Event.filter(workspace_id=thread.workspace_id, action=EventAction.COMMENTED).count() == 1
    assert background_jobs.has_completed_job(IndexEmailThreadJob)

    # GET returns the created comment, ordered by created_at
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "Second comment"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    second_id = response.json()["id"]

    response = await client.get(f"/api/email_threads/{thread.id}/comments")
    body = response.json()
    assert [c["id"] for c in body["comments"]] == [comment_id, second_id]

    # PATCH edit — 200, records an EMAIL_THREAD_COMMENT_EDITED event so the mailbox engine can
    # sync it (the edit-rule keeps it from re-alerting caught-up collaborators).
    response = await client.patch(
        f"/api/email_threads/{thread.id}/comments/{comment_id}",
        json={"content": "Edited comment"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["content"] == "Edited comment"
    assert (
        await Event.filter(workspace_id=thread.workspace_id, action=EventAction.EMAIL_THREAD_COMMENT_EDITED).count()
        == 1
    )

    # Blank content → 422
    response = await client.patch(
        f"/api/email_threads/{thread.id}/comments/{comment_id}",
        json={"content": "   "},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # DELETE — 204 (not 200 like legacy); soft-deleted, so the default manager hides it,
    # and records an EMAIL_THREAD_COMMENT_DELETED event
    response = await client.delete(f"/api/email_threads/{thread.id}/comments/{comment_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await EmailThreadComment.get_or_none(id=comment_id) is None
    assert (
        await Event.filter(workspace_id=thread.workspace_id, action=EventAction.EMAIL_THREAD_COMMENT_DELETED).count()
        == 1
    )


@pytest.mark.asyncio
async def test_email_thread_comment_soft_delete(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    kept = await client.post(f"/api/email_threads/{thread.id}/comments", json={"content": "Keep me"})
    removed = await client.post(f"/api/email_threads/{thread.id}/comments", json={"content": "Remove me"})
    kept_id = kept.json()["id"]
    removed_id = removed.json()["id"]

    response = await client.delete(f"/api/email_threads/{thread.id}/comments/{removed_id}")
    assert response.status_code == status.HTTP_204_NO_CONTENT

    # Soft delete: the row survives (deleted_at stamped) but the default NonDeletedManager hides it.
    assert await EmailThreadComment.get_or_none(id=removed_id) is None
    async with allow_soft_deleted():
        persisted = await EmailThreadComment.get_or_none(id=removed_id)
    assert persisted is not None
    assert persisted.deleted_at is not None

    # Excluded from the comments index endpoint...
    response = await client.get(f"/api/email_threads/{thread.id}/comments")
    assert [c["id"] for c in response.json()["comments"]] == [kept_id]

    # ...and from the thread show payload the React island bootstraps from.
    response = await client.get(f"/api/email_threads/{thread.id}")
    assert [c["id"] for c in response.json()["comments"]] == [kept_id]

    # The delete is recorded as an event (drives mailbox sync) and reindexes the thread.
    assert (
        await Event.filter(workspace_id=thread.workspace_id, action=EventAction.EMAIL_THREAD_COMMENT_DELETED).count()
        == 1
    )
    assert background_jobs.has_completed_job(IndexEmailThreadJob)


@pytest.mark.asyncio
async def test_email_thread_comment_permissions(client: AppClient):
    creator = await client.get_default_user()
    collaborator = await create_user(organization_id=creator.organization_id)
    outsider = await create_user(organization_id=creator.organization_id)

    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=thread.workspace_id, added_by_id=creator.id, user_id=collaborator.id)

    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "Creator's comment"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]

    # Non-author collaborator cannot edit or delete the author's comment (403).
    with client.current_user_as(collaborator):
        response = await client.patch(
            f"/api/email_threads/{thread.id}/comments/{comment_id}",
            json={"content": "Hijacked"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        response = await client.delete(f"/api/email_threads/{thread.id}/comments/{comment_id}")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    # A user who can't access the thread gets 404 (not 403 — don't leak existence).
    with client.current_user_as(outsider):
        response = await client.get(f"/api/email_threads/{thread.id}/comments")
        assert response.status_code == status.HTTP_404_NOT_FOUND

        response = await client.post(
            f"/api/email_threads/{thread.id}/comments",
            json={"content": "Sneaky"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_email_thread_comment_mention_pushes_not_emails(
    client: AppClient,
    email_delivery: FakeDelivery,
    background_jobs: InlineJobs,
    push_enabled,
    push_delivery: FakePushDelivery,
):
    # A @mention on a thread comment pushes (like chat) and reaches the inbox, not email.
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Threadland", organization_id=creator.organization_id)
    await create_push_subscription(user_id=alice.id, platform="Chrome on macOS")
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "Hey @[Alice Threadland] take a look"},
    )
    assert response.status_code == status.HTTP_201_CREATED

    assert background_jobs.has_completed_job(SendMentionPushJob)
    assert not background_jobs.has_completed_job(SendMentionJob)
    assert email_delivery.by_recipient(alice.email) == []


@pytest.mark.asyncio
async def test_email_thread_comment_edit_mention_does_not_email(
    client: AppClient, email_delivery: FakeDelivery, background_jobs: InlineJobs
):
    # Editing a comment to add an @mention grants that user access (collaborator → inbox)
    # but sends no email — email-thread comment @mentions don't email.
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Editland", organization_id=creator.organization_id)
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "Initial comment"},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]

    response = await client.patch(
        f"/api/email_threads/{thread.id}/comments/{comment_id}",
        json={"content": "Now @[Alice Editland] take a look"},
    )
    assert response.status_code == status.HTTP_200_OK

    assert not background_jobs.has_completed_job(SendMentionJob)
    assert email_delivery.by_recipient(alice.email) == []
    assert await Collaborator.filter(workspace_id=thread.workspace_id, user_id=alice.id).exists()


@pytest.mark.asyncio
async def test_email_thread_comment_edit_added_mention_pushes_and_reaches_inbox(
    client: AppClient,
    email_delivery: FakeDelivery,
    background_jobs: InlineJobs,
    push_enabled,
    push_delivery: FakePushDelivery,
):
    # Editing a comment to add an @mention pushes the newly-mentioned user and surfaces the
    # thread in their inbox unread — but never emails (email-thread comment @mentions don't email).
    creator = await client.get_default_user()
    alice = await create_user(name="Alice Pushland", organization_id=creator.organization_id)
    await create_push_subscription(user_id=alice.id, platform="Chrome on macOS")
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.post(f"/api/email_threads/{thread.id}/comments", json={"content": "Initial comment"})
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]

    response = await client.patch(
        f"/api/email_threads/{thread.id}/comments/{comment_id}",
        json={"content": "Now @[Alice Pushland] take a look"},
    )
    assert response.status_code == status.HTTP_200_OK

    assert background_jobs.has_completed_job(SendMentionPushJob)
    assert not background_jobs.has_completed_job(SendMentionJob)
    assert email_delivery.by_recipient(alice.email) == []

    entry = await MailboxEntry.get(owner_id=alice.id, resource_gid=str(thread.global_id))
    assert MailboxLabel.INBOX in entry.labels
    assert MailboxLabel.UNREAD in entry.labels


@pytest.mark.asyncio
async def test_email_thread_comment_reactions(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    comment = await create_email_thread_comment(
        workspace_id=thread.workspace_id, user_id=creator.id, content="React to me"
    )
    original_updated_at = comment.updated_at

    # Invalid reaction_type → 422
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments/{comment.id}/reactions?reaction_type=not_a_reaction"
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Toggle on — 200, reactions dict updated.
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments/{comment.id}/reactions?reaction_type=thumbs_up"
    )
    assert response.status_code == status.HTTP_200_OK
    reaction_ids = [u["id"] for u in response.json()["reactions"]["thumbs_up"]]
    assert str(creator.id) in reaction_ids

    # Reactions don't bump updated_at (key invariant) and don't re-index.
    await comment.refresh_from_db()
    assert comment.updated_at == original_updated_at
    assert not background_jobs.has_completed_job(IndexEmailThreadJob)

    # Toggle off — reaction removed.
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments/{comment.id}/reactions?reaction_type=thumbs_up"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["reactions"].get("thumbs_up", []) == []


@pytest.mark.asyncio
async def test_email_thread_comment_link_preview(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    # unfurl_links=False → no preview association.
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "See https://github.com/anthropics/claude-code", "unfurl_links": False},
    )
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["link_preview"] is None

    # unfurl_links=True → preview FK set on the response.
    # TODO: add VCR cassette once the endpoint exists (record-mode=rewrite).
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "See https://github.com/anthropics/claude-code", "unfurl_links": True},
    )
    assert response.status_code == status.HTTP_201_CREATED
    preview = response.json()["link_preview"]
    assert preview is not None
    comment_id = response.json()["id"]

    # Editing with a new URL updates the preview.
    response = await client.patch(
        f"/api/email_threads/{thread.id}/comments/{comment_id}",
        json={"content": "Now see https://github.com/anthropics/anthropic-sdk-python", "unfurl_links": True},
    )
    assert response.status_code == status.HTTP_200_OK
    updated_preview = response.json()["link_preview"]
    assert updated_preview is not None
    assert updated_preview["url"] != preview["url"]


@pytest.mark.asyncio
async def test_email_thread_comment_edit_keeps_non_image_attachment(client: AppClient):
    # A non-image attachment on an email comment renders from a separate attachments list, not
    # from the content, so a text-only edit must not delete it. cleanup_unreferenced_attachments
    # is images-only on this path — only chat file cards (claim_for_comment) drop unreferenced files.
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    claim_id = uuid4()
    attachment = await create_attachment(
        user_id=creator.id,
        workspace_id=None,
        claim_id=claim_id,
        comment_gid=None,
        filename="report.pdf",
        content_type="application/pdf",
    )

    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "See attached", "attachment_claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_201_CREATED
    comment_id = response.json()["id"]
    # The PDF's URL is never in the content, yet it survives create (images-only cleanup)...
    assert await Attachment.filter(id=attachment.id).exists()

    response = await client.patch(
        f"/api/email_threads/{thread.id}/comments/{comment_id}",
        json={"content": "Updated text, still no inline link"},
    )
    assert response.status_code == status.HTTP_200_OK
    # ...and survives a subsequent text-only edit.
    assert await Attachment.filter(id=attachment.id).exists()


@pytest.mark.asyncio
async def test_email_thread_comment_attachment_link_serializes_file_card(client: AppClient):
    # A pasted attachment link on an email comment carries resource_kind="file" AND re-resolved
    # file metadata (content type/size) so the shared LinkPreviewCard renders a full file card,
    # matching chat (both were omitted on this surface before).
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    content = b"%PDF-1.4 spec body"
    attachment = await create_attachment(
        user_id=creator.id, workspace_id=None, filename="spec.pdf", content_type="application/pdf", content=content
    )
    url = urljoin(str(settings.base_url), f"/workspaces/attachments/{attachment.id}/download")

    response = await client.post(f"/api/email_threads/{thread.id}/comments", json={"content": f"See {url}"})
    assert response.status_code == status.HTTP_201_CREATED

    listing = await client.get(f"/api/email_threads/{thread.id}/comments")
    preview = listing.json()["comments"][0]["link_preview"]
    assert preview is not None
    assert preview["resource_kind"] == "file"
    assert preview["title"] == "spec.pdf"
    assert preview["file"] == {
        "file_name": "spec.pdf",
        "content_type": "application/pdf",
        "byte_size": len(content),
    }


@pytest.mark.asyncio
async def test_email_thread_comment_inline_attachment_renders_only_as_card(client: AppClient):
    # An uploaded non-image attachment referenced inline unfurls into the file-card preview.
    # The claimed Attachment must NOT also appear in the attachments list (show_in_list=False),
    # so the same file renders once — as the card — not once as the card and again as a list row.
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    claim_id = uuid4()
    attachment = await create_attachment(
        user_id=creator.id,
        workspace_id=None,
        claim_id=claim_id,
        comment_gid=None,
        filename="report.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.4 spec body",
    )
    url = urljoin(str(settings.base_url), f"/workspaces/attachments/{attachment.id}/download")

    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": f"[report.pdf]({url})", "attachment_claim_id": str(claim_id)},
    )
    assert response.status_code == status.HTTP_201_CREATED

    comment = (await client.get(f"/api/email_threads/{thread.id}/comments")).json()["comments"][0]
    # The card is present (its single representation)...
    assert comment["link_preview"]["resource_kind"] == "file"
    # ...and the claimed attachment is suppressed from the list rather than duplicating it.
    attachments = {a["id"]: a for a in comment["attachments"]}
    assert attachments[str(attachment.id)]["show_in_list"] is False


@pytest.mark.asyncio
async def test_email_thread_comment_reply_persists_and_serializes(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    parent = await client.post(f"/api/email_threads/{thread.id}/comments", json={"content": "Original comment"})
    parent_id = parent.json()["id"]

    # Create response carries the reply preview.
    reply = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "A reply", "reply_to_id": parent_id},
    )
    assert reply.status_code == status.HTTP_201_CREATED
    reply_id = reply.json()["id"]
    assert reply.json()["reply_to"] == {
        "id": parent_id,
        "user_name": creator.display_name,
        "content_preview": "Original comment",
        "is_deleted": False,
    }

    # Persisted on the row.
    assert str((await EmailThreadComment.get(id=reply_id)).reply_to_id) == parent_id

    # Index endpoint carries reply_to; the parent (no reply) has null reply_to.
    listing = (await client.get(f"/api/email_threads/{thread.id}/comments")).json()["comments"]
    by_id = {c["id"]: c for c in listing}
    assert by_id[reply_id]["reply_to"]["id"] == parent_id
    assert by_id[parent_id]["reply_to"] is None

    # Thread show payload (the React island bootstrap) also carries reply_to.
    show = (await client.get(f"/api/email_threads/{thread.id}")).json()["comments"]
    assert next(c for c in show if c["id"] == reply_id)["reply_to"]["id"] == parent_id


@pytest.mark.asyncio
async def test_email_thread_comment_reply_preview_strips_markdown_and_truncates(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    parent = await create_email_thread_comment(
        email_thread_id=thread.id,
        user_id=creator.id,
        content="**bold** _italic_ [link](http://x) " + "x" * 500,
    )
    await create_email_thread_comment(email_thread_id=thread.id, user_id=creator.id, reply_to_id=parent.id)

    listing = (await client.get(f"/api/email_threads/{thread.id}/comments")).json()["comments"]
    preview = next(c for c in listing if c["reply_to"])["reply_to"]["content_preview"]
    assert preview.startswith("bold italic link")
    assert preview.endswith("…")
    assert len(preview) == 200


@pytest.mark.asyncio
async def test_email_thread_comment_reply_target_validation(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)
    other_thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    # A comment in a *different* thread can't be quoted.
    cross = await create_email_thread_comment(email_thread_id=other_thread.id, user_id=creator.id)
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "Cross-thread", "reply_to_id": str(cross.id)},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    assert response.json()["detail"] == "reply_to_id not found in this thread"

    # A nonexistent id is rejected.
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "Ghost", "reply_to_id": str(uuid4())},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # A soft-deleted target is rejected (the default manager hides it).
    deleted = await create_email_thread_comment(email_thread_id=thread.id, user_id=creator.id)
    await deleted.soft_delete()
    response = await client.post(
        f"/api/email_threads/{thread.id}/comments",
        json={"content": "To a ghost", "reply_to_id": str(deleted.id)},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_email_thread_comment_reply_to_soft_deleted_target_shows_tombstone(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    parent = await create_email_thread_comment(
        email_thread_id=thread.id, user_id=creator.id, content="Will be deleted"
    )
    reply = await create_email_thread_comment(email_thread_id=thread.id, user_id=creator.id, reply_to_id=parent.id)

    # Soft-delete the quoted comment — the pointer survives so the quote renders a tombstone.
    await parent.soft_delete()

    listing = (await client.get(f"/api/email_threads/{thread.id}/comments")).json()["comments"]
    reply_data = next(c for c in listing if c["id"] == str(reply.id))
    assert reply_data["reply_to"]["is_deleted"] is True
    assert reply_data["reply_to"]["content_preview"] == "This message was deleted"


@pytest.mark.asyncio
async def test_email_thread_comment_edit_of_reply_keeps_reply_to(client: AppClient):
    # The edit path serializes through _build_response, which reads reply_to, so editing a
    # reply must still load the target.
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    parent = await create_email_thread_comment(
        email_thread_id=thread.id, user_id=creator.id, content="Original comment"
    )
    other = await create_email_thread_comment(email_thread_id=thread.id, user_id=creator.id, content="Other")
    reply = await create_email_thread_comment(email_thread_id=thread.id, user_id=creator.id, reply_to_id=parent.id)

    # Reply target is create-only: a reply_to_id in the edit body is ignored, not re-pointed.
    response = await client.patch(
        f"/api/email_threads/{thread.id}/comments/{reply.id}",
        json={"content": "Edited reply", "reply_to_id": str(other.id)},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["content"] == "Edited reply"
    assert response.json()["reply_to"]["id"] == str(parent.id)
    assert (await EmailThreadComment.get(id=reply.id)).reply_to_id == parent.id


@pytest.mark.asyncio
async def test_email_thread_comment_reply_to_hard_deleted_target_nulls(client: AppClient):
    creator = await client.get_default_user()
    thread = await create_email_thread(creator_id=creator.id, organization_id=creator.organization_id)

    parent = await create_email_thread_comment(email_thread_id=thread.id, user_id=creator.id)
    reply = await create_email_thread_comment(email_thread_id=thread.id, user_id=creator.id, reply_to_id=parent.id)

    # A hard delete (purge/cascade) fires ON DELETE SET NULL, so the quote gracefully vanishes.
    await parent.delete()

    assert (await EmailThreadComment.get(id=reply.id)).reply_to_id is None
    listing = (await client.get(f"/api/email_threads/{thread.id}/comments")).json()["comments"]
    assert next(c for c in listing if c["id"] == str(reply.id))["reply_to"] is None
