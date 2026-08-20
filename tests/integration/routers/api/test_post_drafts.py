from datetime import UTC, datetime, timedelta
from uuid import uuid4 as generate_uuid

import pytest
from fastapi import status

from app.jobs.content import ContentIndexingJob
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import LinkPreview, url_hash
from config.enums import EventAction, LinkPreviewStatus, Sharing
from infra.jobs import InlineJobs
from tests.helpers.app import AppClient
from tests.helpers.factories import (
    create_attachment,
    create_collaborator,
    create_group,
    create_mailbox_entry,
    create_post,
    create_user,
)


@pytest.mark.asyncio
async def test_show_draft(client: AppClient):
    creator = await client.get_default_user()
    group = await create_group(organization_id=creator.organization_id, name="Engineering")
    other_group = await create_group(organization_id=creator.organization_id, name="Design")
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="My Draft",
        published_at=None,
        group_id=group.id,
    )

    response = await client.get(f"/api/posts/{post.id}/draft")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] == str(post.id)
    assert body["title"] == "My Draft"
    assert body["group"] == {"id": str(group.id), "name": "Engineering"}
    assert body["is_announcement"] is False
    assert body["is_creator"] is True
    assert body["can_announce"] is False  # not an admin
    assert body["can_delete"] is True  # creator can delete
    assert body["workspace_id"] == str(post.workspace_id)
    assert {g["name"] for g in body["org_groups"]} == {"Engineering", "Design"}
    assert str(other_group.id) in {g["id"] for g in body["org_groups"]}
    # The editor re-sources these client-side now that data-props is gone.
    assert body["upload_url"].endswith(f"/workspaces/{post.workspace_id}/attachments")
    # No mailbox_entry_id was passed, so there's no mailbox context.
    assert body["mailbox_entry"] is None


@pytest.mark.asyncio
async def test_show_draft_resolves_mailbox_entry(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="Draft with inbox context",
        published_at=None,
    )
    entry = await create_mailbox_entry(
        organization_id=creator.organization_id,
        owner_id=creator.id,
        resource_gid=str(post.global_id),
        title=post.title,
    )

    # Passing mailbox_entry_id resolves the owner-scoped entry so the editor header
    # renders its mailbox variant (mirrors GET /api/posts/{id}).
    response = await client.get(f"/api/posts/{post.id}/draft?mailbox_entry_id={entry.id}")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["mailbox_entry"]["id"] == str(entry.id)


@pytest.mark.asyncio
async def test_show_draft_access(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)
    post = await create_post(creator_id=creator.id, organization_id=creator.organization_id, published_at=None)

    # Non-collaborator gets 404 from get_draft_post
    with client.current_user_as(other_user):
        response = await client.get(f"/api/posts/{post.id}/draft")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # Collaborator (not creator) sees the draft with is_creator False
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=creator.id, user_id=other_user.id)
    with client.current_user_as(other_user):
        response = await client.get(f"/api/posts/{post.id}/draft")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["is_creator"] is False

    # Published post is not a draft -> 404
    published = await create_post(creator_id=creator.id, organization_id=creator.organization_id)
    response = await client.get(f"/api/posts/{published.id}/draft")
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_draft_title(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        published_at=None,
    )

    response = await client.patch(
        f"/api/posts/{post.id}/draft",
        json={"title": "Updated title"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["title"] == "Updated title"
    assert response.json()["id"] == str(post.id)
    assert any(isinstance(job.job_definition, ContentIndexingJob) for job in background_jobs.completed)


@pytest.mark.asyncio
async def test_update_draft_permissions(client: AppClient):
    creator = await client.get_default_user()
    other_user = await create_user(organization_id=creator.organization_id)

    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        published_at=None,
    )

    # Non-collaborator gets 404 from get_draft_post
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/posts/{post.id}/draft",
            json={"title": "Hijacked"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    # Collaborator who isn't the creator gets 403
    await create_collaborator(
        workspace_id=post.workspace_id,
        user_id=other_user.id,
        organization_id=creator.organization_id,
    )
    with client.current_user_as(other_user):
        response = await client.patch(
            f"/api/posts/{post.id}/draft",
            json={"title": "Hijacked"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_update_published_post_returns_404(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
    )

    response = await client.patch(
        f"/api/posts/{post.id}/draft",
        json={"title": "Should fail"},
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_draft_group_and_announcement(client: AppClient):
    creator = await client.get_default_user()
    group = await create_group(organization_id=creator.organization_id, name="Engineering")
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="Keep this title",
        published_at=None,
    )

    # Group-only change does not touch the title
    response = await client.patch(f"/api/posts/{post.id}/draft", json={"group_id": str(group.id)})
    assert response.status_code == status.HTTP_200_OK
    await post.refresh_from_db()
    assert post.group_id == group.id
    assert post.title == "Keep this title"

    # Announcement (admin only) clears the group
    await creator.make_admin()
    response = await client.patch(
        f"/api/posts/{post.id}/draft",
        json={"group_id": str(group.id), "is_announcement": True},
    )
    assert response.status_code == status.HTTP_200_OK
    await post.refresh_from_db()
    assert post.is_announcement is True
    assert post.group_id is None

    # Empty body is rejected
    response = await client.patch(f"/api/posts/{post.id}/draft", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_update_draft_rejects_cross_org_group(client: AppClient):
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="Draft",
        published_at=None,
    )
    # A group from a different organization must not be assignable.
    foreign_user = await create_user()
    foreign_group = await create_group(organization_id=foreign_user.organization_id, name="Foreign")

    response = await client.patch(f"/api/posts/{post.id}/draft", json={"group_id": str(foreign_group.id)})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
    await post.refresh_from_db()
    assert post.group_id is None


@pytest.mark.asyncio
async def test_update_draft_announcement_requires_admin(client: AppClient):
    creator = await client.get_default_user()  # not an admin
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="Draft",
        published_at=None,
    )

    # A non-admin's announcement request is silently downgraded, not honored
    response = await client.patch(
        f"/api/posts/{post.id}/draft",
        json={"group_id": None, "is_announcement": True},
    )
    assert response.status_code == status.HTTP_200_OK
    await post.refresh_from_db()
    assert post.is_announcement is False


@pytest.mark.asyncio
async def test_publish_draft(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="Ready to ship",
        published_at=None,
        sharing=Sharing.PRIVATE,
    )

    # Inline image uploaded during drafting: an attachment with a non-null claim_id
    # referenced from the document body. Publishing should claim it (clear claim_id).
    attachment_id = generate_uuid()
    content = f"Here is the body\n![logo](/workspaces/abc/attachments/{attachment_id}/download)"
    await LiveDocument.set_initial_content(post.live_document_topic, content)
    inline_attachment = await create_attachment(
        id=attachment_id,
        user_id=creator.id,
        workspace_id=post.workspace_id,
        claim_id=generate_uuid(),
        comment_gid=None,
    )

    response = await client.post(f"/api/posts/{post.id}/publish")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["id"] == str(post.id)

    await post.refresh_from_db()
    await post.fetch_related("comments", "workspace__events")
    assert post.is_published
    assert post.sharing == Sharing.ORGANIZATION
    assert post.original_comment.content == content
    assert EventAction.POST_CREATED in [event.action for event in post.workspace.events]

    # Publish clears claim_id on attachments referenced in the published content
    await inline_attachment.refresh_from_db()
    assert inline_attachment.claim_id is None

    # Re-publishing is idempotent
    response = await client.post(f"/api/posts/{post.id}/publish")
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_publish_draft_associates_link_preview(client: AppClient, background_jobs: InlineJobs):
    creator = await client.get_default_user()

    # Pre-seed the URL cache so prepare_link_preview_for_comment takes the find_valid
    # cache-hit branch and makes no network call.
    preview = await LinkPreview.create(
        url="https://example.com/article",
        url_hash=url_hash("https://example.com/article"),
        status=LinkPreviewStatus.READY,
        title="Article Title",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )

    post_a = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="Ready to ship",
        published_at=None,
        sharing=Sharing.PRIVATE,
    )
    await LiveDocument.set_initial_content(post_a.live_document_topic, "Read this: https://example.com/article")

    post_b = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="No links here",
        published_at=None,
        sharing=Sharing.PRIVATE,
    )
    await LiveDocument.set_initial_content(post_b.live_document_topic, "Just plain text, no link at all.")

    # Draft A: publishing a draft whose body has a link associates the cached preview.
    response = await client.post(f"/api/posts/{post_a.id}/publish")
    assert response.status_code == status.HTTP_200_OK

    await post_a.refresh_from_db()
    await post_a.fetch_related("comments")
    assert post_a.original_comment.link_preview_id == preview.id

    # Draft A: the associated preview surfaces on the show API.
    response = await client.get(f"/api/posts/{post_a.id}")
    assert response.status_code == status.HTTP_200_OK
    show_preview = response.json()["original_comment"]["link_preview"]
    assert show_preview is not None
    assert show_preview["title"] == "Article Title"

    # Draft B: publishing a draft with no link associates no preview.
    response = await client.post(f"/api/posts/{post_b.id}/publish")
    assert response.status_code == status.HTTP_200_OK
    await post_b.refresh_from_db()
    await post_b.fetch_related("comments")
    assert post_b.original_comment.link_preview_id is None


@pytest.mark.asyncio
async def test_publish_draft_claims_org_wide_composer_attachment(client: AppClient, background_jobs: InlineJobs):
    # Inline-composer uploads are org-wide (workspace_id=None) and publishing has no claim_id
    # path, so publish must promote the publisher's referenced uploads into the workspace.
    creator = await client.get_default_user()
    post = await create_post(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        title="Ready to ship",
        published_at=None,
        sharing=Sharing.PRIVATE,
    )

    owned_id = generate_uuid()
    other_id = generate_uuid()
    content = (
        "Here is the body\n"
        f"[report.pdf](/workspaces/attachments/{owned_id}/download)\n"
        f"[stranger.pdf](/workspaces/attachments/{other_id}/download)"
    )
    await LiveDocument.set_initial_content(post.live_document_topic, content)

    owned_attachment = await create_attachment(
        id=owned_id, user_id=creator.id, workspace_id=None, claim_id=generate_uuid(), comment_gid=None
    )
    # A different user's org-wide upload referenced in the same content must NOT be claimed —
    # promotion is scoped to the publisher.
    stranger = await create_user(organization_id=creator.organization_id)
    other_attachment = await create_attachment(
        id=other_id, user_id=stranger.id, workspace_id=None, claim_id=generate_uuid(), comment_gid=None
    )

    response = await client.post(f"/api/posts/{post.id}/publish")
    assert response.status_code == status.HTTP_200_OK

    await owned_attachment.refresh_from_db()
    assert owned_attachment.claim_id is None
    assert owned_attachment.workspace_id == post.workspace_id

    await other_attachment.refresh_from_db()
    assert other_attachment.claim_id is not None
    assert other_attachment.workspace_id is None


@pytest.mark.asyncio
async def test_publish_draft_validation(client: AppClient):
    creator = await client.get_default_user()

    # Untitled draft cannot publish
    untitled = await create_post(
        creator_id=creator.id, organization_id=creator.organization_id, title="Untitled draft", published_at=None
    )
    await LiveDocument.set_initial_content(untitled.live_document_topic, "Has content")
    response = await client.post(f"/api/posts/{untitled.id}/publish")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    # Empty content cannot publish
    titled = await create_post(
        creator_id=creator.id, organization_id=creator.organization_id, title="Has a title", published_at=None
    )
    response = await client.post(f"/api/posts/{titled.id}/publish")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@pytest.mark.asyncio
async def test_publish_announcement_draft_by_collaborator(client: AppClient, background_jobs: InlineJobs):
    admin = await client.get_default_user()
    await admin.make_admin()
    collaborator = await create_user(organization_id=admin.organization_id)
    member = await create_user(organization_id=admin.organization_id, last_logged_in_at=datetime.now(UTC))
    post = await create_post(
        creator_id=admin.id,
        organization_id=admin.organization_id,
        title="Company update",
        published_at=None,
        sharing=Sharing.PRIVATE,
        is_announcement=True,
    )
    await create_collaborator(workspace_id=post.workspace_id, added_by_id=admin.id, user_id=collaborator.id)
    await LiveDocument.set_initial_content(post.live_document_topic, "Big announcement body")

    # A collaborator (not just the creator) can publish
    with client.current_user_as(collaborator):
        response = await client.post(f"/api/posts/{post.id}/publish")
    assert response.status_code == status.HTTP_200_OK

    await post.refresh_from_db()
    await post.fetch_related("workspace__events")
    assert post.is_published
    assert EventAction.POST_ANNOUNCED in [event.action for event in post.workspace.events]

    # Announcements reach every org member's inbox, even non-collaborators
    entry = await MailboxEntry.filter(owner_id=member.id, resource_gid=str(post.global_id)).first()
    assert entry is not None
    assert entry.is_inbox
