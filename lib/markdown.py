import re
from typing import cast

import mistune
from mistune.plugins.formatting import strikethrough
from mistune.plugins.table import table
from mistune.plugins.task_lists import task_lists

from lib.html import strip_html
from lib.strings import excerpt_around

# `![alt](url)` renders as <img>, and BeautifulSoup.get_text() drops the alt
# attribute — an image-only message would otherwise preview as empty.
_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\([^)]*\)")


# escape=False: we strip all HTML downstream, so escaping just leaves encoded
# entities to re-strip.
_to_html = mistune.create_markdown(
    renderer=mistune.HTMLRenderer(escape=False), plugins=[table, task_lists, strikethrough]
)


def _substitute_image(match: re.Match[str]) -> str:
    alt = match.group(1).strip()
    return f"[{alt}]" if alt else "[image]"


def markdown_to_plain_text(text: str | None) -> str:
    """Render markdown to single-line plain text suitable for previews."""
    if not text:
        return ""
    # mistune's signature says `str | list`, but the list form only happens with
    # an AST renderer; cast keeps the type checker honest.
    html = cast(str, _to_html(_IMAGE_PATTERN.sub(_substitute_image, text)))
    return " ".join(strip_html(html, whitespace_separator=" ").split())


def preview_excerpt(text: str, needle: str, length: int) -> str:
    """A preview-sized window of `text` around `needle`, with inline images removed.

    Images are dropped because they render as broken/empty placeholders in a text
    preview; the rest is left as markdown for the caller to render. Windowing is
    delegated to `excerpt_around`, which snaps to word boundaries and adds
    ellipses when it trims.
    """
    return excerpt_around(_IMAGE_PATTERN.sub("", text), needle, length)
