import re
from dataclasses import dataclass

IMAGE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)")
# The destination allows one level of balanced parens and backslash-escaped
# parens (the editor serializes hrefs with \( \) — see urlFormatting.ts), so a
# URL like .../Scheme_(programming_language) survives instead of truncating at
# the first ")".
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!\!)\[([^\]]+)\]\(((?:[^()\s\\]|\\[()]|\([^()]*\))+)\)")
PLAIN_URL_PATTERN = re.compile(r"(?P<url>https?://[^\s<>]+)")
IMAGE_EXTENSION_PATTERN = re.compile(r"\.(jpe?g|png|gif|webp|svg|ico|bmp)(\?.*)?$", re.IGNORECASE)
# Mirrors the client-side findPreviewUrl (app/javascript/richText/linkPreview.ts)
# so the compose-time preview predicts the unfurl performed at submit. Both keep
# balanced parens in a URL while dropping a wrapping ")" from surrounding prose.
TRAILING_PUNCTUATION_PATTERN = re.compile(r"[.,;:!?]+$")


@dataclass
class Link:
    title: str
    url: str
    description: str = ""


def _is_image_url(url: str) -> bool:
    return bool(IMAGE_EXTENSION_PATTERN.search(url))


def _unescape_parens(url: str) -> str:
    return url.replace("\\(", "(").replace("\\)", ")")


def _trim_bare_url(url: str) -> str:
    # A bare URL ending a sentence drags its punctuation into the match. Then
    # drop a trailing ")" that has no matching "(" — i.e. a URL wrapped in prose
    # parens like "(https://example.com)" — while keeping balanced parens that
    # belong to the URL itself.
    url = TRAILING_PUNCTUATION_PATTERN.sub("", url)
    while url.endswith(")") and url.count(")") > url.count("("):
        url = TRAILING_PUNCTUATION_PATTERN.sub("", url[:-1])
    return url


def extract_links_from_text(text: str):
    # Strip image markdown so image URLs aren't treated as links
    text = IMAGE_PATTERN.sub("", text)

    # Find all markdown links and extract their titles and URLs
    results: list[Link] = []
    for match in MARKDOWN_LINK_PATTERN.finditer(text):
        title = match.group(1)
        url = _unescape_parens(match.group(2))
        if not _is_image_url(url):
            results.append(Link(title=title, url=url))

    # Remove markdown links from text to avoid duplicating URLs
    text_without_links = MARKDOWN_LINK_PATTERN.sub("", text)

    # Find all plain URLs in the remaining text. Markdown link targets are
    # explicitly delimited and need no trimming.
    for match in PLAIN_URL_PATTERN.finditer(text_without_links):
        url = _trim_bare_url(match.group("url"))
        if not _is_image_url(url):
            results.append(Link(title=url, url=url))

    return results
