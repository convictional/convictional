import re
from re import Match
from typing import cast

import mistune
from markupsafe import Markup
from mistune import BlockParser, BlockState, Markdown, safe_entity
from mistune.plugins import Plugin
from mistune.plugins.formatting import strikethrough
from mistune.plugins.table import table
from mistune.plugins.url import url

from app.helpers.markdown import BaseMarkdownRenderer, hard_break
from lib.html import WHITESPACE_PRESERVING_BLOCK_RE, sanitize_email_html_content

QUOTED_HTML_DIRECTIVE_PATTERN = (
    r"^ {0,3}:{3,}(?P<type>\w+)"  # Opening marker with directive type
    r"(?:\{(?P<attributes>[^}]*)\})?"  # Optional attributes in curly braces
    r"[ \t]*\n"  # Optional spaces/tabs followed by a newline
    r"(?P<content>(?:(?!^ {0,3}:{3,}[ \t]*(?:\n|$)).|\n)*?)"  # Content until closing marker
    r"\n^ {0,3}:{3,}[ \t]*(?:\n|$)"  # Closing marker
)


def quoted_html_directive(md: "Markdown") -> None:
    def parse_quoted_html_directive(block: BlockParser, match: Match[str], state: BlockState) -> int:
        content = match.group("content")
        attributes = match.group("attributes") or ""

        state.append_token(
            {
                "type": "quoted_html_directive",
                "raw": content,
                "attributes": attributes,
            }
        )

        return match.end()

    def render_quoted_html_directive(renderer, text: str) -> str:
        html_content = text

        wrapper_style = (
            "border-left: 4px solid #d1d5db; padding: 8px 16px; margin: 16px 0; "
            "background-color: #f9fafb; border-radius: 0 6px 6px 0;"
        )
        return f'<div class="quote_container" style="{wrapper_style}">{html_content}</div>'

    md.block.register(
        "quoted_html_directive", QUOTED_HTML_DIRECTIVE_PATTERN, parse_quoted_html_directive, before="paragraph"
    )
    if md.renderer and md.renderer.NAME == "html":
        md.renderer.register("quoted_html_directive", render_quoted_html_directive)


class EmailMarkdownHTMLRenderer(BaseMarkdownRenderer):
    def paragraph(self, text: str) -> str:
        # Empty paragraphs should render as <div><br></div> to match Gmail
        if not text or not text.strip():
            return "<div><br></div>"
        return f"<div>{text}</div>"

    def heading(self, text: str, level: int, **attrs) -> str:
        styles = {
            1: "font-size: 1.5em; font-weight: bold; margin: 1em 0 0.5em 0;",
            2: "font-size: 1.3em; font-weight: bold; margin: 1em 0 0.5em 0;",
            3: "font-size: 1.1em; font-weight: bold; margin: 1em 0 0.5em 0;",
            4: "font-size: 1em; font-weight: bold; margin: 1em 0 0.5em 0;",
            5: "font-size: 0.9em; font-weight: bold; margin: 1em 0 0.5em 0;",
            6: "font-size: 0.8em; font-weight: bold; margin: 1em 0 0.5em 0;",
        }
        return f'<h{level} style="{styles[level]}">{text}</h{level}>'

    def link(self, text: str, url: str, title=None) -> str:
        safe = self.safe_url(url)
        title_attr = f' title="{safe_entity(title)}"' if title else ""
        return f'<a href="{safe}" style="color: #0066cc; text-decoration: underline;"{title_attr}>{text}</a>'

    def image(self, alt: str, url: str, title=None) -> str:
        safe = self.safe_url(url)
        title_attr = f' title="{safe_entity(title)}"' if title else ""

        return f'<img src="{safe}" alt="{safe_entity(alt)}" style="max-width: 100%; height: auto;"{title_attr}>'

    def block_quote(self, text: str) -> str:
        style = "margin: 1em 0; padding-left: 1em; border-left: 3px solid #ccc; color: #666; font-style: italic;"
        return f'<blockquote style="{style}">{text}</blockquote>'

    def list(self, text: str, ordered: bool, **attrs) -> str:
        tag = "ol" if ordered else "ul"
        style = "margin: 1em 0; padding-left: 2em;"
        if ordered:
            # `depth` counts any container (ul, blockquote), so an ol nested only under non-ol
            # containers diverges from the CSS surfaces (markdown-content.css / email.css count
            # ol ancestors only). Accepted — do not reconcile.
            depth = attrs.get("depth", 0)
            list_style_type = {0: "decimal", 1: "lower-alpha"}.get(depth, "lower-roman")
            style += f" list-style-type: {list_style_type};"
        return f'<{tag} style="{style}">{text}</{tag}>'

    def list_item(self, text: str) -> str:
        return f'<li style="margin: 0.5em 0;">{text}</li>'

    def table(self, text: str) -> str:
        return f'<table style="border-collapse: collapse; width: 100%; margin: 1em 0;">{text}</table>'

    def table_head(self, text: str) -> str:
        # mistune's table plugin calls table_head(cells) directly, bypassing table_row,
        # so the header cells arrive without a <tr>. Wrap them here to emit well-formed
        # HTML rather than relying on nh3 to repair the missing row on the way out.
        return f'<thead style="background-color: #f5f5f5;"><tr>{text}</tr></thead>'

    def table_body(self, text: str) -> str:
        return f"<tbody>{text}</tbody>"

    def table_row(self, text: str) -> str:
        return f"<tr>{text}</tr>"

    def table_cell(self, text: str, align=None, head=False) -> str:
        tag = "th" if head else "td"
        style = "padding: 0.5em; border: 1px solid #ddd;"
        if align:
            style += f" text-align: {align};"
        if head:
            style += " font-weight: bold;"
        return f'<{tag} style="{style}">{text}</{tag}>'

    def codespan(self, text: str) -> str:
        style = "background-color: #f5f5f5; padding: 0.2em 0.4em; border-radius: 3px; font-family: monospace;"
        return f'<code style="{style}">{text}</code>'

    def block_code(self, text: str, info=None) -> str:
        style = (
            "background-color: #f5f5f5; padding: 1em; border-radius: 5px; "
            "overflow-x: auto; font-family: monospace; margin: 1em 0;"
        )
        return f'<pre style="{style}"><code>{text}</code></pre>'

    def emphasis(self, text: str) -> str:
        return f"<em>{text}</em>"

    def strong(self, text: str) -> str:
        return f"<strong>{text}</strong>"

    def strikethrough(self, text: str) -> str:
        return f"<del>{text}</del>"


# Create the email markdown renderer with email-compatible plugins
email_client_renderer = EmailMarkdownHTMLRenderer()
email_plugins = [table, url, strikethrough, hard_break, quoted_html_directive]
email_plugins_typed: list[Plugin] = [cast(Plugin, plugin) for plugin in email_plugins]
email_markdown = mistune.create_markdown(renderer=email_client_renderer, plugins=email_plugins_typed)


# Block-level tags the email renderer emits. A whitespace-only newline run touching one
# of these is inter-block pretty-print, not an authored soft break.
_BLOCK_TAGS = "div|p|h[1-6]|ul|ol|li|table|thead|tbody|tfoot|tr|td|th|blockquote|pre|hr"
_WHITESPACE_WITH_NEWLINE_RE = re.compile(r"[ \t\r\n]*\n[ \t\r\n]*")
_ENDS_WITH_BREAK_RE = re.compile(r"<br\s*/?>\Z", re.IGNORECASE)
_STARTS_WITH_BREAK_RE = re.compile(r"\A<br\s*/?>", re.IGNORECASE)
_ENDS_WITH_BLOCK_TAG_RE = re.compile(rf"</?(?:{_BLOCK_TAGS})\b[^>]*>\Z", re.IGNORECASE)
_STARTS_WITH_BLOCK_TAG_RE = re.compile(rf"\A</?(?:{_BLOCK_TAGS})\b", re.IGNORECASE)


def _strip_cosmetic_newlines(html: str) -> str:
    # mistune serializes a bare `<br>` with a trailing cosmetic `\n`, and pretty-prints a
    # `\n` between block siblings. Both are invisible under white-space: normal but under
    # the email display iframe's pre-wrap (email.css) they render as visible extra breaks,
    # doubling every hard break. Strip them here, symmetric with the client's rehype pass.
    # An authored soft break between inline content (`a\nb`, `<em>x</em>\n<em>y</em>`) is a
    # real newline pre-wrap should render, so it is preserved: a whitespace-newline run is
    # removed only when it touches a `<br>` or block-level tag. <pre>/<code> is exempt.
    segments = WHITESPACE_PRESERVING_BLOCK_RE.split(html)
    for index in range(0, len(segments), 2):  # even indices are outside pre/code
        segments[index] = _strip_segment_cosmetic_newlines(segments[index])
    return "".join(segments)


def _strip_segment_cosmetic_newlines(segment: str) -> str:
    def replace(match: Match[str]) -> str:
        before = segment[: match.start()]
        after = segment[match.end() :]
        touches_break = bool(_ENDS_WITH_BREAK_RE.search(before)) or bool(_STARTS_WITH_BREAK_RE.match(after))
        touches_block = bool(_ENDS_WITH_BLOCK_TAG_RE.search(before)) or bool(_STARTS_WITH_BLOCK_TAG_RE.match(after))
        return "" if touches_break or touches_block else match.group(0)

    return _WHITESPACE_WITH_NEWLINE_RE.sub(replace, segment)


def render_email_html(text: str | None) -> Markup:
    """Convert markdown to email-compatible HTML"""
    if not text:
        return Markup("")

    html = email_markdown(text)

    # Ensure we have a string (mistune sometimes returns list)
    if isinstance(html, list):
        html = "".join([item.get("text", str(item)) for item in html])

    html = _strip_cosmetic_newlines(html)

    # Wrap in outer div to match Gmail structure
    html = f"<div>{html}</div>"

    # Authored content: preserve whitespace (no leading strip / newline collapse) so the
    # user's runs and breaks survive to display. Sanitized once here at compose; the
    # display path trusts the stored body_html for authored messages.
    return sanitize_email_html_content(html, preserve_whitespace=True)
