from urllib.parse import urljoin

import pytest
from fastapi import status

from app.models.collaboration.workspace import LinkPreview, Visit
from config.enums import EmailLabel, LinkPreviewStatus, LinkPreviewType, MailboxLabel
from config.settings import settings
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_collaborator,
    create_group,
    create_mailbox_entry,
    create_post,
    create_post_comment,
    create_user,
)


@pytest.mark.asyncio
async def test_show_enriches_attachment_file_card(client: AppClient):
    # top_level_comments is the initial payload the post island renders, so its attachment-link
    # previews must arrive with file metadata enriched (content type/size), not just the filename.
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    content = b"a,b\n1,2\n"
    attachment = await create_attachment(
        user_id=creator.id,
        workspace_id=post.workspace_id,
        filename="report.csv",
        content_type="text/csv",
        content=content,
    )
    url = urljoin(str(settings.base_url), f"/workspaces/attachments/{attachment.id}/download")
    preview = await LinkPreview.upsert(
        url,
        {
            "status": LinkPreviewStatus.READY,
            "type": LinkPreviewType.LINK,
            "title": "report.csv",
            "description": None,
            "image_url": None,
            "site_name": None,
            "oembed_html": None,
        },
    )
    await create_post_comment(
        post_id=post.id, user_id=creator.id, content=f"[report.csv]({url})", link_preview_id=preview.id
    )

    response = await client.get(f"/api/posts/{post.id}")
    assert response.status_code == status.HTTP_200_OK
    link_preview = response.json()["top_level_comments"][0]["link_preview"]
    assert link_preview["resource_kind"] == "file"
    assert link_preview["file"] == {"file_name": "report.csv", "content_type": "text/csv", "byte_size": len(content)}


@pytest.mark.asyncio
async def test_show_returns_full_envelope(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=creator.id, user_id=other_user.id)

    top_level = await create_post_comment(post_id=post.id, user_id=other_user.id, content="Top-level comment")
    await create_post_comment(post_id=post.id, user_id=creator.id, parent_id=top_level.id, content="A reply")

    response = await client.get(f"/api/posts/{post.id}")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()

    # Envelope keys
    expected_keys = {
        "post",
        "original_comment",
        "top_level_comments",
        "last_visit_at",
        "mailbox_entry",
        "subscription",
    }
    assert expected_keys.issubset(body.keys())

    # Post fields
    assert body["post"]["id"] == str(post.id)
    assert body["post"]["workspace_id"] == str(post.workspace_id)
    assert body["post"]["permissions"] == {"edit": True, "pin": False, "delete": True}
    assert body["post"]["pinned_at"] is None

    # Original comment is separate from top_level_comments — the React island
    # renders the original via <PostBody>, not the comment list.
    assert body["original_comment"] is not None
    assert body["original_comment"]["parent_id"] is None
    assert body["original_comment"]["id"] != str(top_level.id)

    assert len(body["top_level_comments"]) == 1
    assert body["top_level_comments"][0]["id"] == str(top_level.id)
    assert len(body["top_level_comments"][0]["replies"]) == 1
    assert body["top_level_comments"][0]["replies"][0]["content"] == "A reply"

    # Original is not duplicated inside top_level_comments
    top_level_ids = {c["id"] for c in body["top_level_comments"]}
    assert body["original_comment"]["id"] not in top_level_ids

    # Read analytics populated for creator
    # Subscription state present
    assert "wants_all" in body["subscription"]
    assert "is_explicit" in body["subscription"]

    # No mailbox entry on this fixture
    assert body["mailbox_entry"] is None


@pytest.mark.asyncio
async def test_last_visit_at_present_after_visit(client: AppClient):
    # Server returns the raw last_visit_at; the client derives "what's new"
    # by diffing comment.created_at and decision.decided_at against this.
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    await Visit.record(creator.id, post.workspace_id)
    response = await client.get(f"/api/posts/{post.id}")
    assert response.json()["last_visit_at"] is not None


@pytest.mark.asyncio
async def test_last_visit_at_null_without_visit(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id)

    response = await client.get(f"/api/posts/{post.id}")
    assert response.json()["last_visit_at"] is None


@pytest.mark.asyncio
async def test_mailbox_entry_when_present(client: AppClient):
    user = await client.get_default_user()
    post = await create_post(creator_id=user.id, organization_id=user.organization_id)
    entry = await create_mailbox_entry(
        owner_id=user.id,
        organization_id=user.organization_id,
        resource_gid=str(post.global_id),
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD, MailboxLabel.INBOX],
    )

    response = await client.get(f"/api/posts/{post.id}?mailbox_entry_id={entry.id}")
    body = response.json()
    assert body["mailbox_entry"] is not None
    # The entry id lets the island drive the generic /api/mailbox_entries/{id} actions.
    assert body["mailbox_entry"]["id"] == str(entry.id)
    assert "is_unread" in body["mailbox_entry"]
    assert "is_archived" in body["mailbox_entry"]
    assert "is_snoozed" in body["mailbox_entry"]


@pytest.mark.asyncio
async def test_grouped_post_group_returned(client: AppClient):
    user = await client.get_default_user()
    group = await create_group(name="Engineering", organization_id=user.organization_id)
    post = await create_post(creator_id=user.id, organization_id=user.organization_id, group_id=group.id)

    response = await client.get(f"/api/posts/{post.id}")
    assert response.json()["post"]["group"] == {"id": str(group.id), "name": "Engineering"}


@pytest.mark.asyncio
async def test_draft_post_returns_404(client: AppClient):
    user = await client.get_default_user()
    draft = await create_post(creator_id=user.id, organization_id=user.organization_id, published_at=None)

    response = await client.get(f"/api/posts/{draft.id}")
    assert response.status_code == status.HTTP_404_NOT_FOUND
