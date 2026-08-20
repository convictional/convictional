import os
from datetime import datetime
from functools import lru_cache
from typing import Any, Literal
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlunparse

from fastapi import Request
from fastapi.routing import APIRoute
from starlette.datastructures import URL
from starlette.requests import HTTPConnection
from starlette.routing import NoMatchFound

from app.helpers.assets import manifest_data
from app.models.collaboration.content import Content, ContentLookup
from app.models.workspaces.email.thread import EmailMessage
from config import settings
from infra.db import GlobalID

BackFallbackRoute = Literal[
    "search_index",
    "documents_index",
    "posts_index",
    "mailbox_index",
    "mailbox_unread",
    "mailbox_archived",
    "mailbox_sent",
    "mailbox_snoozed",
    "mailbox_drafts",
    "mailbox_assigned_to_me",
    "goals_index",
    "chats_index",
    "meetings_index",
]

# Keep the keys of BACK_LABELS in sync with BackFallbackRoute; mypy enforces
# it at call sites of back_navigation.
BACK_LABELS: dict[BackFallbackRoute, str] = {
    "search_index": "Back to search",
    "documents_index": "Back to documents",
    "posts_index": "Back to posts",
    "mailbox_index": "Back to inbox",
    "mailbox_unread": "Back to unread",
    "mailbox_archived": "Back to archived",
    "mailbox_sent": "Back to sent",
    "mailbox_snoozed": "Back to snoozed",
    "mailbox_drafts": "Back to drafts",
    "mailbox_assigned_to_me": "Back to assigned",
    "goals_index": "Back to goals",
    "chats_index": "Back to chats",
    "meetings_index": "Back to meetings",
}


# AJAX-only query params that must never survive into a back/redirect URL.
# Otherwise paginated load-more requests leak `?cursor=...` into return_to and
# the browser ends up parked on a paginated URL after a back-nav.
_TRANSIENT_REDIRECT_QUERY_PARAMS = frozenset({"cursor"})


def build_safe_redirect_url(url: str | None) -> str | None:
    if not url:
        return None

    parsed_redirect = urlparse(url)
    if not parsed_redirect.path.startswith("/"):
        return None

    cleaned_query = urlencode(
        [
            (k, v)
            for k, v in parse_qsl(parsed_redirect.query, keep_blank_values=True)
            if k not in _TRANSIENT_REDIRECT_QUERY_PARAMS
        ]
    )

    # Drop scheme and netloc so an absolute URL is always normalized to a
    # relative path on our own origin — prevents open-redirect.
    return urlunparse(parsed_redirect._replace(scheme="", netloc="", query=cleaned_query))


def back_navigation(request: Request, *, fallback_route: BackFallbackRoute) -> dict[str, str]:
    return_to = build_safe_redirect_url(request.query_params.get("return_to"))

    if return_to:
        parsed = urlparse(return_to)
        label = _back_label_for_path(request, parsed.path)
        if label:
            # Custom mailbox views live at the inbox path with a query param
            # selecting a template or saved view; call it out so the back label
            # isn't just "Back to inbox".
            if label == BACK_LABELS["mailbox_index"] and _is_mailbox_custom_view(parsed.query):
                label = "Back to custom view"
            return {"url": return_to, "label": label}

    return {
        "url": request.url_for(fallback_route).path,
        "label": BACK_LABELS[fallback_route],
    }


def _is_mailbox_custom_view(query_string: str) -> bool:
    if not query_string:
        return False
    params = parse_qs(query_string)
    return "mailbox_view_template" in params or "mailbox_view_id" in params


def _back_label_for_path(request: Request, path: str) -> str | None:
    normalized_path = path.rstrip("/") or "/"
    best: tuple[int, str] | None = None
    for route_name, label in BACK_LABELS.items():
        try:
            route_path = request.url_for(route_name).path
        except NoMatchFound:
            continue
        normalized_route = route_path.rstrip("/") or "/"
        if normalized_route == "/":
            matches = normalized_path == "/"
        else:
            matches = normalized_path == normalized_route or normalized_path.startswith(normalized_route + "/")
        if matches:
            length = len(normalized_route)
            if best is None or length > best[0]:
                best = (length, label)
    return best[1] if best else None


def url_for_bundled_file(filename: str) -> str:
    if settings.asset_building_enabled:
        return urljoin(str(settings.vite_url), filename)

    host = settings.asset_host or settings.base_url
    return urljoin(str(host), path_for_bundled_file(filename))


def path_for_bundled_file(filename: str):
    hashed_filename: dict[str, Any] | None = manifest_data.get(filename, None)
    if settings.asset_building_enabled and not hashed_filename:
        raise ValueError(f"File {filename} not found in Vite manifest")
    if not hashed_filename:
        return urljoin(settings.static_asset_url_prefix, filename)

    return urljoin(settings.static_asset_url_prefix, f"build/{hashed_filename.get('file')}")


def url_for_static_file(filename: str) -> str:
    """Generates a URL for a static file with a cache-busting query parameter.
    This is useful for ensuring that browsers always fetch the latest version of a file.
    """
    host = settings.asset_host or settings.base_url
    path = path_for_static_file(filename)
    return urljoin(str(host), path)


def path_for_static_file(filename: str):
    path = urljoin(settings.static_asset_url_prefix, filename)

    if settings.asset_host:
        return path

    file_path = settings.root / "static" / filename
    last_modified_time = _get_last_modified_time(str(file_path))
    return f"{path}?v={last_modified_time}"


def _get_last_modified_time(file_path: str) -> float:
    try:
        return os.path.getmtime(file_path)
    except OSError:
        return datetime.now().timestamp()


if not settings.is_hot_reload:
    _get_last_modified_time = lru_cache(maxsize=128)(_get_last_modified_time)


def current_route(request: Request) -> APIRoute:
    from_scope = request.scope.get("route")
    if not from_scope:
        raise ValueError("Request scope does not contain a route")

    return from_scope


def convert_cid_urls_to_attachment_downloads(
    connection: Request | HTTPConnection, html_content: str, message: EmailMessage
) -> str:
    """Convert CID URLs in email HTML to attachment download URLs.

    Accepts any starlette HTTPConnection (Request or WebSocket) since only
    url_for() is needed. Lets the channel handler reuse this helper without
    juggling a Request the WebSocket scope doesn't provide.
    """
    if not html_content or not message.attachments:
        return html_content

    content_id_to_url: dict[str, str] = {}
    for attachment in message.attachments:
        if attachment.content_id and attachment.is_referenced_in_html:
            download_url = connection.url_for(
                "email_attachments_download", email_thread_id=message.thread_id, attachment_id=attachment.id
            )
            content_id_to_url[attachment.content_id] = str(download_url)

    if not content_id_to_url:
        return html_content

    for content_id, download_url_str in content_id_to_url.items():
        cid_url = f"cid:{content_id}"
        html_content = html_content.replace(cid_url, download_url_str)

    return html_content


def absolute_url(path: str) -> str:
    return urljoin(str(settings.base_url), str(path))


def url_for_content(request: Request | None, content: Content | ContentLookup) -> str:
    if content.metadata.get("url", None):
        return str(content.metadata["url"])

    if request is not None:
        return str(request.url_for("gid_redirect", gid=content.source_global_id.to_param))

    gid = GlobalID.parse(content.source_url)
    if gid.is_internal:
        path = f"/gid/{gid.to_param}"
        return absolute_url(path)

    return content.source_url


# Canonical set of citation record types that resolve to a workspace URL. Lives here
# (not with the get_workspace_url registry in app/routers/global_ids.py) because helpers/
# cannot import from routers/ (enforced by .importlinter). A test pins it equal to the
# registry's keys so the resolver coverage and this gate can't drift.
LINKABLE_CITATION_RECORD_TYPES: frozenset[str] = frozenset(
    {
        "Meeting",
        "Goal",
        "GoalComment",
        "Post",
        "PostComment",
        "DocumentComment",
        "User",
        "EmailThreadComment",
        "Document",
        "EmailThread",
        "Chat",
    }
)


def citation_url(content: Content | ContentLookup) -> str | None:
    # Mirror url_for_content's precedence: an explicit metadata override wins even
    # when the source GID itself isn't a linkable record type.
    if content.metadata.get("url"):
        return str(content.metadata["url"])
    gid = GlobalID.parse(content.source_url)
    if gid.is_internal and gid.record_type not in LINKABLE_CITATION_RECORD_TYPES:
        return None
    return url_for_content(None, content)


def url_with_fragment(url: URL | str, fragment: str) -> str:
    parsed = urlparse(str(url))
    return urlunparse(parsed._replace(fragment=fragment))
