import re
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.helpers.link_previews import is_internal_url
from app.helpers.strings import og_description
from app.models.accounts import User
from app.models.collaboration.workspace import Attachment, CollaborationPolicy, LinkPreview
from app.models.workspaces.chat import Chat
from app.models.workspaces.documents import Document, DocumentComment
from app.models.workspaces.email.thread import EmailThread
from app.models.workspaces.goals import Goal, GoalComment
from app.models.workspaces.meetings import Meeting
from app.models.workspaces.posts import Post, PostComment
from config.enums import LinkPreviewStatus, LinkPreviewType, Sharing
from infra.db import GlobalID, InvalidGlobalIDParamError

# Internal URLs resolve to a preview in-process instead of by HTTP-fetching the
# server-rendered page (which disappears as routes move into the React SPA shell).
# The GlobalID `/gid/{param}` form is the primary, type-bearing path; friendly
# address-bar URLs (`/posts/{id}`, `/goals#goal-{id}`) are a thin best-effort fallback.

_GID_PATH = re.compile(r"^/gid/(?P<param>[^/]+)/?$")
_GOAL_FRAGMENT = re.compile(r"^goal-(?P<id>[0-9a-f-]+)$", re.IGNORECASE)
_COMMENT_FRAGMENT = re.compile(r"^comment-(?P<id>[0-9a-f-]+)$", re.IGNORECASE)

# Leading path segment of a friendly resource URL -> resource kind.
_COLLECTION_KINDS: dict[str, str] = {
    "posts": "post",
    "documents": "document",
    "meetings": "meeting",
    "email_threads": "email_thread",
    "chats": "chat",
}

# GlobalID record_type -> resource kind. Comment types route to their parent.
_RECORD_TYPE_KINDS: dict[str, str] = {
    "Goal": "goal",
    "Post": "post",
    "Document": "document",
    "Meeting": "meeting",
    "EmailThread": "email_thread",
    "Chat": "chat",
    "GoalComment": "goal_comment",
    "PostComment": "post_comment",
    "DocumentComment": "document_comment",
}

# Comment sub-kinds resolve to — and display as — their parent resource.
_PARENT_KINDS: dict[str, str] = {
    "goal_comment": "goal",
    "post_comment": "post",
    "document_comment": "document",
}


async def resolve_internal_preview(url: str, current_user: User) -> dict[str, Any] | None:
    """Resolve an internal URL to link-preview attrs, or None when it doesn't resolve
    or the user may not view the resource. The attrs dict matches LinkPreview.upsert."""
    target = _parse_target(url)
    if not target:
        return None

    kind, record_id = target
    handler = _HANDLERS.get(kind)
    if not handler:
        return None
    return await handler(record_id, current_user)


def internal_resource_kind(url: str) -> str | None:
    """The display resource kind for an internal URL, or None for external URLs.
    Derived purely from the URL so it works on already-persisted previews without
    a stored column. The is_internal_url guard stops an external URL that happens
    to match a resource path (e.g. /posts/{uuid}) from posing as a native card."""
    if not is_internal_url(url):
        return None
    target = _parse_target(url)
    if not target:
        return None
    kind = target[0]
    return _PARENT_KINDS.get(kind, kind)


def previewed_attachment_id(url: str) -> UUID | None:
    """The attachment id an internal download URL points at, or None for any other URL.
    The is_internal_url guard mirrors internal_resource_kind: an external URL that mimics
    the attachment download path must not match a local attachment."""
    if not is_internal_url(url):
        return None
    target = _parse_target(url)
    return target[1] if target and target[0] == "file" else None


def _parse_target(url: str) -> tuple[str, UUID] | None:
    parsed = urlparse(url)
    path = parsed.path

    gid_match = _GID_PATH.match(path)
    if gid_match:
        return _parse_gid(gid_match.group("param"))

    segments = [segment for segment in path.split("/") if segment]

    # Attachment download URLs across every scope (/workspaces/attachments/{id}/download,
    # /workspaces/{wid}/attachments/{id}/download, /chats/{cid}/attachments/{id}/download)
    # resolve to a file card. Checked before the collection branch below so that a chat
    # attachment URL isn't mistaken for the chat itself (segments[0] == "chats"). The id is
    # the segment right after "attachments", not a fixed position from the end.
    if segments and segments[-1] == "download" and "attachments" in segments:
        try:
            return "file", UUID(segments[segments.index("attachments") + 1])
        except (ValueError, IndexError):
            return None

    # Goals appear two ways: the detail page /goals/{id}, and the index page with
    # the id in the fragment (/goals#goal-{id}).
    if segments[:1] == ["goals"]:
        if len(segments) >= 2:
            try:
                return "goal", UUID(segments[1])
            except ValueError:
                return None
        return _parse_goal_fragment(parsed.fragment)

    if len(segments) >= 2 and segments[0] in _COLLECTION_KINDS:
        try:
            return _COLLECTION_KINDS[segments[0]], UUID(segments[1])
        except ValueError:
            return None

    return None


def _parse_gid(param: str) -> tuple[str, UUID] | None:
    try:
        gid = GlobalID.from_param(param)
    except InvalidGlobalIDParamError:
        return None
    if not gid.is_internal or gid.record_type is None:
        return None
    kind = _RECORD_TYPE_KINDS.get(gid.record_type)
    if not kind:
        return None
    try:
        return kind, gid.record_id
    except (ValueError, IndexError):
        return None


def _parse_goal_fragment(fragment: str) -> tuple[str, UUID] | None:
    goal_match = _GOAL_FRAGMENT.match(fragment)
    if goal_match:
        try:
            return "goal", UUID(goal_match.group("id"))
        except ValueError:
            return None
    comment_match = _COMMENT_FRAGMENT.match(fragment)
    if comment_match:
        try:
            return "goal_comment", UUID(comment_match.group("id"))
        except ValueError:
            return None
    return None


def _attrs(title: str | None, description: str | None) -> dict[str, Any]:
    return {
        "status": LinkPreviewStatus.READY,
        "type": LinkPreviewType.LINK,
        "title": title,
        "description": description,
        "image_url": None,
        "site_name": None,
        "oembed_html": None,
    }


async def _resolve_goal(goal_id: UUID, user: User) -> dict[str, Any] | None:
    goal = await Goal.get_or_none(id=goal_id, organization_id=user.organization_id)
    if not goal:
        return None
    # A goal's description is its long-form title (the prominent statement the goal
    # list renders); goal.title is a short, often-empty label we don't surface here.
    long_title = og_description(goal.description) if goal.description else None
    return _attrs(long_title or goal.title, None)


async def _resolve_post(post_id: UUID, user: User) -> dict[str, Any] | None:
    post = await Post.get_or_none(id=post_id, organization_id=user.organization_id).prefetch_related(
        "workspace__collaborators", "comments"
    )
    if not post:
        return None
    if post.sharing == Sharing.PRIVATE and not post.collaboration.can_be_accessed_by(user):
        return None
    original = post.original_comment
    description = og_description(original.content) if original else None
    return _attrs(post.title, description)


async def _resolve_document(document_id: UUID, user: User) -> dict[str, Any] | None:
    document = await Document.get_or_none(id=document_id, organization_id=user.organization_id).prefetch_related(
        "workspace__collaborators"
    )
    if not document or not document.collaboration.can_be_accessed_by(user):
        return None
    return _attrs(document.title, None)


async def _resolve_meeting(meeting_id: UUID, user: User) -> dict[str, Any] | None:
    meeting = await Meeting.get_or_none(id=meeting_id, organization_id=user.organization_id).prefetch_related(
        "workspace__collaborators"
    )
    if not meeting or not meeting.collaboration.can_be_accessed_by(user):
        return None
    return _attrs(meeting.title, None)


async def _resolve_email_thread(thread_id: UUID, user: User) -> dict[str, Any] | None:
    thread = await EmailThread.get_or_none(id=thread_id, organization_id=user.organization_id).prefetch_related(
        "workspace__collaborators"
    )
    if not thread or not thread.collaboration.can_be_accessed_by(user):
        return None
    return _attrs(thread.title or "No subject", None)


async def _resolve_chat(chat_id: UUID, user: User) -> dict[str, Any] | None:
    chat = await Chat.get_or_none(id=chat_id, organization_id=user.organization_id).prefetch_related(
        "workspace__collaborators__user"
    )
    if not chat or not chat.collaboration.can_be_accessed_by(user):
        return None
    return _attrs(chat.resolved_title(user.id), None)


async def _resolve_goal_comment(comment_id: UUID, user: User) -> dict[str, Any] | None:
    comment = await GoalComment.get_or_none(id=comment_id, goal__organization_id=user.organization_id)
    if not comment:
        return None
    return await _resolve_goal(comment.goal_id, user)


async def _resolve_post_comment(comment_id: UUID, user: User) -> dict[str, Any] | None:
    comment = await PostComment.get_or_none(id=comment_id, post__organization_id=user.organization_id)
    if not comment:
        return None
    return await _resolve_post(comment.post_id, user)


async def _resolve_document_comment(comment_id: UUID, user: User) -> dict[str, Any] | None:
    comment = await DocumentComment.get_or_none(id=comment_id, document__organization_id=user.organization_id)
    if not comment:
        return None
    return await _resolve_document(comment.document_id, user)


def _attachment_file_attrs(attachment: Attachment) -> dict[str, Any]:
    return {
        "file_name": attachment.file.filename,
        "content_type": attachment.file.content_type,
        "byte_size": attachment.file.byte_size,
    }


def _attachment_accessible_by(attachment: Attachment, user: User) -> bool:
    # Mirror the download route's access control (workspace_attachments.py): a workspace-claimed
    # attachment follows its workspace's sharing/collaborator rules, an unclaimed one is visible
    # only to its uploader. Org-scoping alone would leak a private file's name/type/size to
    # non-collaborators in the same org even though the download itself would 404 them.
    if attachment.workspace is not None:
        return CollaborationPolicy(attachment.workspace).can_be_accessed_by(user)
    return attachment.user_id == user.id


async def _resolve_attachment(attachment_id: UUID, user: User) -> dict[str, Any] | None:
    # The "file" attrs key carries display metadata for the card and is dropped before
    # persistence (no LinkPreview column) — see prepare_link_preview_for_comment.
    attachment = (
        await Attachment.filter(Attachment.filters.by_organization(user.organization_id), id=attachment_id)
        .prefetch_related("file", "workspace__collaborators")
        .first()
    )
    if not attachment or not _attachment_accessible_by(attachment, user):
        return None
    attrs = _attrs(attachment.file.filename, None)
    attrs["file"] = _attachment_file_attrs(attachment)
    return attrs


async def resolve_attachment_files(urls: list[str], user: User) -> dict[str, dict[str, Any]]:
    """Batch-resolve file-card metadata for attachment download URLs in a single query.
    Returns url -> file attrs for the URLs pointing at an attachment `user` may view; missing,
    foreign, or inaccessible attachments are omitted. Lets a caller enrich many file previews at
    once instead of one DB round-trip per preview. Applies the same per-collaborator check as
    _resolve_attachment (via _attachment_accessible_by): a preview is re-hydrated per reader, so a
    cross-workspace pasted link resolves for its author but not for a non-collaborator reading the
    same chat/post — org-scoping alone would leak a private file's name/type/size to them."""
    ids_by_url = {}
    for url in urls:
        target = _parse_target(url)
        if target and target[0] == "file":
            ids_by_url[url] = target[1]
    if not ids_by_url:
        return {}
    attachments = await Attachment.filter(
        Attachment.filters.by_organization(user.organization_id), id__in=list(ids_by_url.values())
    ).prefetch_related("file", "workspace__collaborators")
    attrs_by_id = {
        attachment.id: _attachment_file_attrs(attachment)
        for attachment in attachments
        if _attachment_accessible_by(attachment, user)
    }
    return {
        url: attrs_by_id[attachment_id] for url, attachment_id in ids_by_url.items() if attachment_id in attrs_by_id
    }


async def resolve_preview_files(link_previews: Iterable[LinkPreview | None], user: User) -> dict[str, dict[str, Any]]:
    """Batch-resolve file-card metadata for the attachment links among `link_previews`, keyed by
    URL. Pair with the `*_response` builders' `files_by_url` argument: resolve first, then build,
    so each preview is constructed with its file metadata rather than mutated afterward — the same
    resolve-then-build shape as `users_by_id`."""
    return await resolve_attachment_files([lp.url for lp in link_previews if lp is not None], user)


_HANDLERS = {
    "goal": _resolve_goal,
    "post": _resolve_post,
    "document": _resolve_document,
    "meeting": _resolve_meeting,
    "email_thread": _resolve_email_thread,
    "chat": _resolve_chat,
    "goal_comment": _resolve_goal_comment,
    "post_comment": _resolve_post_comment,
    "document_comment": _resolve_document_comment,
    "file": _resolve_attachment,
}
