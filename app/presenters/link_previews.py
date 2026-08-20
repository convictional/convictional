from typing import Any

from app.helpers.link_previews import is_internal_url
from app.models.accounts import User
from app.models.collaboration.workspace import LinkPreview
from app.presenters.internal_link_previews import resolve_internal_preview
from app.presenters.links import extract_links_from_text
from config.enums import LinkPreviewStatus, LinkPreviewType
from lib.unfurl import is_safe_url, unfurl


async def unfurl_link_preview(url: str) -> dict[str, Any]:
    """Unfurl an external URL and return link preview attributes (including failed fallback)."""
    result = await unfurl(url)

    if result:
        return {
            "status": LinkPreviewStatus.READY,
            "type": LinkPreviewType.VIDEO if result.oembed_type == "video" else LinkPreviewType.LINK,
            "title": result.title,
            "description": result.description,
            "image_url": result.image_url,
            "site_name": result.site_name,
            "oembed_html": result.oembed_html,
        }
    return {"status": LinkPreviewStatus.FAILED, "type": LinkPreviewType.LINK}


async def prepare_link_preview_for_comment(content: str, current_user: User) -> tuple[str, dict[str, Any]] | None:
    """Extract URL and fetch link preview data. Call BEFORE entering a transaction."""
    links = extract_links_from_text(content)
    if not links:
        return None

    first_url = links[0].url

    # Internal URLs resolve in-process against the viewer's permissions. The unfurl
    # endpoint re-resolves them per-request and never serves cached data, so the
    # permission check can't be bypassed there. The preview returned here is then
    # persisted via LinkPreview.associate as a per-comment row, not a per-viewer one.
    if is_internal_url(first_url):
        attrs = await resolve_internal_preview(first_url, current_user)
        if attrs is None:
            return None
        # File metadata is a display-only extra carried for the compose response; it has no
        # LinkPreview column, so drop it before this dict is persisted via upsert. The card's
        # filename survives in `title`, and content type/size are re-resolved at render.
        attrs.pop("file", None)
        return first_url, attrs

    if not is_safe_url(first_url):
        return None

    if await LinkPreview.find_valid(first_url):
        return first_url, {}

    attrs = await unfurl_link_preview(first_url)
    return first_url, attrs
