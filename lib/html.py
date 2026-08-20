import re

import nh3  # type: ignore[import]
from bs4 import BeautifulSoup, NavigableString, Tag
from markupsafe import Markup

MAX_HTML_SIZE = 1048576  # 1MB limit for security
MAX_CSS_SIZE = 10000  # 10KB limit for security
MAX_URL_SIZE = 2048  # 2KB limit for security

ALLOWED_HTML_TAGS = {
    "p",
    "br",
    "div",
    "span",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "ul",
    "ol",
    "li",
    "a",
    "img",
    "blockquote",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "caption",
    "pre",
    "code",
    "hr",
    "sup",
    "sub",
    "del",
    "ins",
    "details",
    "summary",
}

ALLOWED_HTML_ATTRIBUTES = {
    "a": ["href", "title"],
    "img": ["src", "alt", "title", "width", "height"],
    "table": ["width", "cellpadding", "cellspacing", "border", "align", "bgcolor"],
    "td": ["colspan", "rowspan", "width", "align", "bgcolor"],
    "th": ["colspan", "rowspan", "width", "align"],
    "tr": ["align"],
    "div": ["align"],
    "details": ["open"],
    "summary": ["aria-label"],
    "*": ["style", "class"],  # Allow on all tags
}


DANGEROUS_HTML_TAGS = ["script", "style", "link", "meta", "object", "embed", "iframe", "form", "head", "title"]

DANGEROUS_CSS_PATTERNS = [
    "javascript:",
    "expression(",
    "behavior:",
    "@import",
    "url(",
    "\\",
    "eval(",
    "mozhtmlbinding:",
    "-moz-binding:",
    "vbscript:",
    "livescript:",
    "data:",
]

DANGEROUS_URL_SCHEMES = [
    "javascript:",
    "data:",
    "vbscript:",
    "file:",
    "ftp:",
    "about:",
    "chrome:",
    "chrome-extension:",
    "moz-extension:",
    "ms-appx:",
    "ms-appx-web:",
    "view-source:",
    "jar:",
    "livescript:",
    "mocha:",
    "opera:",
    "resource:",
]

SUSPICIOUS_URL_CHARS = ["<", ">", '"', "'", "\\", "\n", "\r", "\t"]


def strip_html(text: str, whitespace_separator: str = "") -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    if whitespace_separator:
        return soup.get_text(whitespace_separator, strip=True)
    return soup.get_text()


def sanitize_email_html_content(html_content: str, preserve_whitespace: bool = False) -> Markup:
    if not html_content:
        return Markup("")

    if len(html_content) > MAX_HTML_SIZE:
        return Markup("")

    # Build configuration for allowed tags and attributes
    allowed_attributes = {}
    for tag, attrs in ALLOWED_HTML_ATTRIBUTES.items():
        if tag != "*":
            allowed_attributes[tag] = set(attrs + ALLOWED_HTML_ATTRIBUTES.get("*", []))

    # Add global attributes to all allowed tags
    global_attrs = set(ALLOWED_HTML_ATTRIBUTES.get("*", []))
    for tag in ALLOWED_HTML_TAGS:
        if tag not in allowed_attributes:
            allowed_attributes[tag] = global_attrs.copy()
        else:
            allowed_attributes[tag].update(global_attrs)

    def attribute_filter(tag: str, attribute: str, value: str):
        if attribute == "class":
            classes = value.split()
            if ("gmail_quote_container" in classes or "gmail_quote" in classes) and "quote_container" not in classes:
                return value + " quote_container"
        elif attribute == "style":
            if not _is_safe_css(value):
                return None
        elif attribute in ["href", "src"]:
            if not _is_safe_url(value):
                return None
            if value.lower().startswith("cid:") and not (tag == "img" and attribute == "src"):
                return None
        return value

    cleaned_html = nh3.clean(
        html_content,
        tags=ALLOWED_HTML_TAGS,
        attributes=allowed_attributes,
        url_schemes={"http", "https", "mailto", "data", "cid"},
        strip_comments=True,
        link_rel="noopener noreferrer",
        attribute_filter=attribute_filter,
        set_tag_attribute_values={"a": {"target": "_blank"}},
        clean_content_tags=set(DANGEROUS_HTML_TAGS),
    ).strip()

    cleaned_html = _linkify_bare_urls(cleaned_html)

    # Authored content (composed via render_email_html) is already whitespace-tight and
    # must keep its runs/breaks byte-faithful, so it skips the two whitespace regexes
    # below. Only untrusted inbound HTML runs the defensive normalization.
    if not preserve_whitespace:
        # Remove leading whitespace from all lines to prevent markdown from
        # interpreting indented lines as code blocks when embedded in templates,
        # and collapse 3+ consecutive newlines to at most 2 — but NEVER inside
        # <pre>/<code>, whose whitespace is significant (indentation, blank lines).
        segments = WHITESPACE_PRESERVING_BLOCK_RE.split(cleaned_html)
        for index in range(0, len(segments), 2):  # even indices are outside pre/code
            segment = segments[index]
            # Strip leading whitespace only at genuine line starts. A segment after a
            # preserved block begins mid-line (right after its closing tag), so its
            # first-line whitespace must survive — else "<code>x</code> y" becomes
            # "<code>x</code>y". Only segment 0 starts at a true line start.
            if index == 0:
                segment = re.sub(r"^[ \t]+", "", segment)
            segment = re.sub(r"(?<=\n)[ \t]+", "", segment)
            segment = re.sub(r"\n\n\n+", "\n\n", segment)
            segments[index] = segment
        cleaned_html = "".join(segments)

    return Markup(cleaned_html)


# <pre> and <code> hold whitespace-significant content (code blocks, inline code) and are
# exempt from every whitespace transform on the email path. Shared by the two consumers
# that split them out: sanitize_email_html_content's leading-strip below, and
# app.helpers.html._strip_cosmetic_newlines. The <pre> alternative is listed first so a
# <pre>...</pre> block — including any nested <code> — is consumed whole before the inner
# <code> is reached. Both consumers feed it balanced HTML (nh3.clean/_linkify_bare_urls, or
# mistune's own output), so a lazy match is well-formed. Keep exactly one capturing group:
# both call sites' split-on-even-index loops depend on it.
WHITESPACE_PRESERVING_BLOCK_RE = re.compile(
    r"(<pre\b[^>]*>.*?</pre>|<code\b[^>]*>.*?</code>)", re.IGNORECASE | re.DOTALL
)

# Greedy match (no lazy quantifier + lookahead — that combination is
# catastrophic-backtracking-prone on long trailing punctuation runs). Excludes
# whitespace, angle brackets, quotes, and C0 controls. Length is capped to
# MAX_URL_SIZE. Trailing punctuation commonly written next to a URL (.,;:!?)])
# is stripped imperatively after the match.
_BARE_URL_REGEX = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"'\x00-\x1f]{1,2048}")
_URL_TRAILING_PUNCT = ".,;:!?)]"
_BARE_HOST_RE = re.compile(r"[A-Za-z0-9.\-]+(?::[0-9]+)?")

# Must run AFTER nh3.clean — relies on nh3 having stripped nested <a>, <script>,
# <style>, etc. from the tree.
_LINKIFY_SKIP_ANCESTORS = {"a", "code", "pre"}


def _linkify_bare_urls(html: str) -> str:
    if not html or ("http" not in html and "www." not in html):
        return html

    soup = BeautifulSoup(html, "html.parser")
    for text_node in list(soup.find_all(string=True)):
        if any(parent.name in _LINKIFY_SKIP_ANCESTORS for parent in text_node.parents if parent.name):
            continue
        original = str(text_node)
        if not _BARE_URL_REGEX.search(original):
            continue

        replacements: list[NavigableString | Tag] = []
        cursor = 0
        for match in _BARE_URL_REGEX.finditer(original):
            raw = match.group(0).rstrip(_URL_TRAILING_PUNCT)
            host_with_port = raw.split("://", 1)[-1].split("/", 1)[0]
            # Reject userinfo (`user@host` is the classic phishing primitive) and
            # any host that contains characters outside the bare-domain alphabet.
            if "@" in host_with_port:
                continue
            if not _BARE_HOST_RE.fullmatch(host_with_port):
                continue
            href = raw if raw.lower().startswith(("http://", "https://")) else f"https://{raw}"
            if not _is_safe_url(href):
                continue
            if cursor < match.start():
                replacements.append(NavigableString(original[cursor : match.start()]))
            anchor = soup.new_tag("a", href=href, target="_blank", rel="noopener noreferrer")
            anchor.string = raw
            replacements.append(anchor)
            cursor = match.start() + len(raw)

        if not replacements:
            continue
        if cursor < len(original):
            replacements.append(NavigableString(original[cursor:]))
        text_node.replace_with(*replacements)

    return str(soup)


def _is_safe_css(css: str) -> bool:
    if not css:
        return True

    if len(css) > MAX_CSS_SIZE:
        return False

    css_lower = css.lower().replace(" ", "").replace("\t", "").replace("\n", "")

    for pattern in DANGEROUS_CSS_PATTERNS:
        if pattern in css_lower:
            return False

    return True


def _is_safe_url(url: str) -> bool:
    if not url:
        return False

    url = url.strip()
    if len(url) > MAX_URL_SIZE:
        return False

    url_lower = url.lower()

    for scheme in DANGEROUS_URL_SCHEMES:
        if url_lower.startswith(scheme):
            # Allow data URLs for images only
            if scheme == "data:" and url_lower.startswith("data:image/"):
                return True
            return False

    # Allow only safe schemes and relative URLs
    if url.startswith(("/", "./", "../", "http://", "https://", "mailto:", "cid:", "#")):
        if any(char in url for char in SUSPICIOUS_URL_CHARS):
            return False
        return True

    return False
