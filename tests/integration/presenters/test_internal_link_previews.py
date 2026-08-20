from urllib.parse import urljoin
from uuid import uuid4

import pytest

from app.presenters.internal_link_previews import (
    internal_resource_kind,
    previewed_attachment_id,
    resolve_attachment_files,
    resolve_internal_preview,
)
from config.settings import settings
from tests.helpers.factories import (
    create_attachment,
    create_chat,
    create_collaborator,
    create_document,
    create_goal,
    create_goal_comment,
    create_post,
    create_user,
)


def _url(path: str) -> str:
    return urljoin(str(settings.base_url), path)


@pytest.mark.asyncio
async def test_resolve_internal_preview_url_parsing(client):
    user = await create_user()
    org_id = user.organization_id

    goal = await create_goal(
        creator_id=user.id, organization_id=org_id, title="Roadmap", description="Hit quarterly targets"
    )
    document = await create_document(creator_id=user.id, organization_id=org_id, title="Spec")
    post = await create_post(creator_id=user.id, organization_id=org_id, title="Lunch")
    goal_comment = await create_goal_comment(goal_id=goal.id, user_id=user.id)

    async def title_of(path: str) -> str | None:
        preview = await resolve_internal_preview(_url(path), user)
        return preview["title"] if preview else None

    # Collection URLs tolerate trailing slashes and trailing path segments (e.g. /edit).
    assert await title_of(f"/documents/{document.id}") == "Spec"
    assert await title_of(f"/documents/{document.id}/") == "Spec"
    assert await title_of(f"/documents/{document.id}/edit") == "Spec"

    # Goals resolve from the detail page /goals/{id} and the index page fragment /goals#goal-{id};
    # a query string before the fragment must not break the fragment form. The preview title is the
    # goal's long-form description, not its short title ("Roadmap").
    assert await title_of(f"/goals/{goal.id}") == "Hit quarterly targets"
    assert await title_of(f"/goals/{goal.id}/") == "Hit quarterly targets"
    assert await title_of(f"/goals#goal-{goal.id}") == "Hit quarterly targets"
    assert await title_of(f"/goals?planning_list_name=Now#goal-{goal.id}") == "Hit quarterly targets"

    # Comment fragments resolve to the parent resource's preview.
    assert await title_of(f"/goals#comment-{goal_comment.id}") == "Hit quarterly targets"
    assert await title_of(f"/posts/{post.id}#comment-{uuid4()}") == "Lunch"

    # A comment in another org is org-scoped at the query level -> no preview.
    foreign_comment = await create_goal_comment()
    assert await title_of(f"/goals#comment-{foreign_comment.id}") is None

    # Unparseable / unknown shapes resolve to nothing rather than raising.
    assert await title_of("/") is None
    assert await title_of("/widgets/123") is None
    assert await title_of(f"/posts/{post.id}-not-a-uuid") is None
    assert await title_of("/goals#goal-not-a-uuid") is None
    assert await title_of("/gid/!!!not-base64!!!") is None


def test_internal_resource_kind():
    rid = uuid4()

    # Each page URL maps to its resource kind (purely from the URL, no DB lookup).
    assert internal_resource_kind(_url(f"/posts/{rid}")) == "post"
    assert internal_resource_kind(_url(f"/documents/{rid}/edit")) == "document"
    assert internal_resource_kind(_url(f"/meetings/{rid}")) == "meeting"
    assert internal_resource_kind(_url(f"/email_threads/{rid}")) == "email_thread"
    assert internal_resource_kind(_url(f"/chats/{rid}")) == "chat"
    assert internal_resource_kind(_url(f"/goals/{rid}")) == "goal"
    assert internal_resource_kind(_url(f"/goals#goal-{rid}")) == "goal"

    # Comment fragments display as their parent resource.
    assert internal_resource_kind(_url(f"/goals#comment-{rid}")) == "goal"

    # Attachment download URLs are file cards across every scope; a chat attachment URL must
    # not be mistaken for the chat itself.
    assert internal_resource_kind(_url(f"/workspaces/attachments/{rid}/download")) == "file"
    assert internal_resource_kind(_url(f"/workspaces/{uuid4()}/attachments/{rid}/download")) == "file"
    assert internal_resource_kind(_url(f"/chats/{uuid4()}/attachments/{rid}/download")) == "file"

    # External URLs are never treated as native, even when the path mimics a resource.
    assert internal_resource_kind(f"https://evil.example.com/posts/{rid}") is None
    # Internal URLs that don't resolve to a known resource shape.
    assert internal_resource_kind(_url("/widgets/123")) is None


def test_previewed_attachment_id():
    rid = uuid4()

    # Only an attachment download URL resolves to an attachment id — across every scope.
    assert previewed_attachment_id(_url(f"/workspaces/attachments/{rid}/download")) == rid
    assert previewed_attachment_id(_url(f"/workspaces/{uuid4()}/attachments/{rid}/download")) == rid
    assert previewed_attachment_id(_url(f"/chats/{uuid4()}/attachments/{rid}/download")) == rid

    # Any other preview kind is not a file, so the strip must not treat it as one.
    assert previewed_attachment_id(_url(f"/posts/{rid}")) is None
    assert previewed_attachment_id(_url(f"/goals#goal-{rid}")) is None
    assert previewed_attachment_id(f"https://evil.example.com/workspaces/attachments/{rid}/download") is None
    assert previewed_attachment_id(_url("/widgets/123")) is None


@pytest.mark.asyncio
async def test_resolve_internal_preview_attachment(client):
    user = await create_user()
    content = b"%PDF-1.4 fake pdf body"
    attachment = await create_attachment(
        user_id=user.id, workspace_id=None, filename="report.pdf", content_type="application/pdf", content=content
    )

    expected_file = {"file_name": "report.pdf", "content_type": "application/pdf", "byte_size": len(content)}

    # Resolves from every download-URL scope, with the filename as the title and file metadata
    # carried under the "file" key for the card.
    for path in (
        f"/workspaces/attachments/{attachment.id}/download",
        f"/chats/{uuid4()}/attachments/{attachment.id}/download",
    ):
        preview = await resolve_internal_preview(_url(path), user)
        assert preview is not None, path
        assert preview["title"] == "report.pdf", path
        assert preview["file"] == expected_file, path

    # A user in another org can't resolve it, and a missing attachment resolves to nothing.
    other_org_user = await create_user()
    foreign_path = _url(f"/workspaces/attachments/{attachment.id}/download")
    assert await resolve_internal_preview(foreign_path, other_org_user) is None
    assert await resolve_internal_preview(_url(f"/workspaces/attachments/{uuid4()}/download"), user) is None


@pytest.mark.asyncio
async def test_resolve_attachment_enforces_workspace_access(client):
    # An attachment claimed to a private workspace resolves only for a collaborator; a same-org
    # non-collaborator is denied, matching the download route rather than leaking name/type/size.
    owner = await create_user()
    chat = await create_chat(organization_id=owner.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=owner.id)
    attachment = await create_attachment(
        user_id=owner.id, workspace_id=chat.workspace_id, filename="private.pdf", content_type="application/pdf"
    )
    url = _url(f"/chats/{chat.id}/attachments/{attachment.id}/download")

    preview = await resolve_internal_preview(url, owner)
    assert preview is not None
    assert preview["file"]["file_name"] == "private.pdf"

    # Same-org non-collaborator is denied even though org-scoping matches the uploader's org.
    outsider = await create_user(organization_id=owner.organization_id)
    assert await resolve_internal_preview(url, outsider) is None


@pytest.mark.asyncio
async def test_resolve_attachment_files_enforces_workspace_access(client):
    # The batch enrichment path re-hydrates previews per reader, so it must apply the same
    # per-collaborator check as compose-time resolution — org-scoping alone would leak a private
    # attachment's name/type/size to a same-org non-collaborator reading someone else's paste.
    owner = await create_user()
    chat = await create_chat(organization_id=owner.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=owner.id)
    attachment = await create_attachment(
        user_id=owner.id, workspace_id=chat.workspace_id, filename="private.pdf", content_type="application/pdf"
    )
    url = _url(f"/chats/{chat.id}/attachments/{attachment.id}/download")

    files = await resolve_attachment_files([url], owner)
    assert files[url]["file_name"] == "private.pdf"

    outsider = await create_user(organization_id=owner.organization_id)
    assert await resolve_attachment_files([url], outsider) == {}
