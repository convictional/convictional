from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.helpers.link_previews import is_internal_url
from app.models.accounts import User
from app.models.collaboration.workspace import LinkPreview, url_hash
from app.presenters.internal_link_previews import (
    internal_resource_kind,
    resolve_internal_preview,
)
from app.presenters.link_previews import unfurl_link_preview
from app.routers.api.schemas import LinkPreviewFileResponse
from app.routers.dependencies import get_current_user
from config.enums import LinkPreviewStatus
from lib.unfurl import is_safe_url

FAILED_BACKOFF_MINUTES = 5

router = APIRouter(tags=["link previews"])


class LinkPreviewResponse(BaseModel):
    url: str
    type: str
    title: str | None
    description: str | None
    image_url: str | None
    site_name: str | None
    domain: str
    # The internal resource kind (goal/post/document/file/…), or None for external
    # links. Lets the card render a native icon + label and navigate in-app.
    resource_kind: str | None = None
    # Display metadata for a pasted attachment link (resource_kind == "file"). Set on the
    # compose-time response and re-resolved at render; null for non-file previews.
    file: LinkPreviewFileResponse | None = None


def link_preview_response(
    lp: LinkPreview, files_by_url: dict[str, dict[str, Any]] | None = None
) -> LinkPreviewResponse:
    # A pasted attachment link persists only its filename; content type/size come from
    # files_by_url (resolve_preview_files), keyed by URL and gated by the reader's access.
    return LinkPreviewResponse(
        url=lp.url,
        type=lp.type.value,
        title=lp.title,
        description=lp.description,
        image_url=lp.image_url,
        site_name=lp.site_name,
        domain=lp.domain,
        resource_kind=internal_resource_kind(lp.url),
        file=LinkPreviewFileResponse.from_attrs((files_by_url or {}).get(lp.url)),
    )


def internal_preview_response(url: str, attrs: dict[str, Any]) -> LinkPreviewResponse:
    return LinkPreviewResponse(
        url=url,
        type=attrs["type"].value,
        title=attrs.get("title"),
        description=attrs.get("description"),
        image_url=attrs.get("image_url"),
        site_name=attrs.get("site_name"),
        domain=urlparse(url).hostname or url,
        resource_kind=internal_resource_kind(url),
        file=LinkPreviewFileResponse.from_attrs(attrs.get("file")),
    )


class UnfurlRequest(BaseModel):
    url: str = Field(max_length=2048)


class UnfurlResponse(BaseModel):
    link_preview: LinkPreviewResponse | None


@router.post("/link_previews/unfurl", response_model=UnfurlResponse)
async def api_unfurl_link_preview(
    body: UnfurlRequest,
    current_user: User = Depends(get_current_user),
):
    url = body.url

    # Internal URLs resolve in-process against the viewer's permissions. They are not
    # cached in the LinkPreview table: that cache is keyed by URL alone, so serving a
    # cached internal preview to another user would bypass the per-request permission check.
    if is_internal_url(url):
        attrs = await resolve_internal_preview(url, current_user)
        if attrs is None:
            return UnfurlResponse(link_preview=None)
        return UnfurlResponse(link_preview=internal_preview_response(url, attrs))

    if not is_safe_url(url):
        return UnfurlResponse(link_preview=None)

    link_preview = await LinkPreview.filter(url_hash=url_hash(url)).first()
    if link_preview:
        if link_preview.status == LinkPreviewStatus.READY and not link_preview.is_expired:
            return UnfurlResponse(link_preview=link_preview_response(link_preview))
        # Don't re-fetch URLs that recently failed
        if link_preview.status == LinkPreviewStatus.FAILED and link_preview.fetched_at:
            backoff_until = link_preview.fetched_at + timedelta(minutes=FAILED_BACKOFF_MINUTES)
            if datetime.now(UTC) < backoff_until:
                return UnfurlResponse(link_preview=None)

    attrs = await unfurl_link_preview(url)
    link_preview = await LinkPreview.upsert(url, attrs)

    if link_preview.status == LinkPreviewStatus.FAILED:
        return UnfurlResponse(link_preview=None)

    return UnfurlResponse(link_preview=link_preview_response(link_preview))
