# Browser-supported image formats (as of 2026)
BROWSER_SUPPORTED_IMAGE_FORMATS = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "image/bmp",
    "image/x-icon",
    "image/vnd.microsoft.icon",
}


def is_browser_supported_image(content_type: str) -> bool:
    """Check if an image format is natively supported by modern browsers."""
    return content_type.lower() in BROWSER_SUPPORTED_IMAGE_FORMATS


# Content types browsers can render inline safely. Everything else gets
# attachment disposition so the browser downloads instead of rendering.
INLINE_MIME_PREFIXES = ("image/", "video/", "audio/")
INLINE_MIME_EXACT = {"application/pdf"}


def is_inline_content_type(content_type: str | None) -> bool:
    """Whether a stored file's content type should be served with `Content-Disposition: inline`.

    SVG is excluded despite matching `image/*` because it can embed JavaScript
    via `<script>` and event handlers — the user-visible benefit of inline
    preview doesn't justify the attack surface.
    """
    if not content_type:
        return False
    base = content_type.split(";", 1)[0].strip().lower()
    if base == "image/svg+xml":
        return False
    return base.startswith(INLINE_MIME_PREFIXES) or base in INLINE_MIME_EXACT
