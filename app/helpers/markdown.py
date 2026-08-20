import re
from dataclasses import dataclass, field
from re import Match
from typing import cast
from uuid import UUID

import mistune
from markupsafe import Markup
from mistune import HTMLRenderer, InlineParser, InlineState, Markdown, safe_entity
from mistune.plugins import Plugin
from mistune.plugins.formatting import strikethrough
from mistune.plugins.table import table
from mistune.plugins.task_lists import task_lists
from mistune.plugins.url import url

from app.helpers.url import citation_url
from app.models.collaboration.content import CONTENT_CITATION_PATTERN, Content
from app.models.collaboration.workspace import MENTION_PATTERN

INCOMPLETE_FOOTNOTE_PATTERN = r"\[\^.*"
HARD_BREAK_PATTERN = r" {2,}$|\\$"


def hard_break(md: "Markdown") -> None:
    def parse_hard_break(inline: InlineParser, match: Match[str], state: InlineState) -> int:
        state.append_token({"type": "hard_break"})
        return match.end()

    def render_hard_break(renderer: HTMLRenderer) -> str:
        return "<br>"

    md.inline.register("hard_break", HARD_BREAK_PATTERN, parse_hard_break, before="linebreak")
    if md.renderer and md.renderer.NAME == "html":
        md.renderer.register("hard_break", render_hard_break)


def mentions(md: "Markdown") -> None:
    def parse_mention(inline: InlineParser, match: Match[str], state: InlineState) -> int:
        mention = match.group("mention")
        username = mention[2:-1]
        state.append_token({"type": "mention", "raw": username})
        return match.end()

    def render_mention(renderer: HTMLRenderer, text: str) -> str:
        return f'<span class="text-info-content">@{text}</span>'

    md.inline.register("mention", MENTION_PATTERN, parse_mention, before="link")
    if md.renderer and md.renderer.NAME == "html":
        md.renderer.register("mention", render_mention)


def content_citation_element(uuid: str):
    return f"""
        <span
            class="mx-0.5 inline-block"
            x-data="{{contentCitationTooltipOptions: {{content: '',
                    appendTo: $root,
                    interactive: true,
                    allowHTML: true
                }}
            }}",
            x-tooltip="contentCitationTooltipOptions"
            @mouseover="
                contentCitationTooltipOptions.content = `<div class='-m-3'>
                    ${{document.getElementById('content-citation-{uuid}').innerHTML}}
                </div>`;
            "
        >
            <sup class="-top-0.5 footnote-ref cursor-pointer bg-info border border-info-content rounded-full
                px-0.5 text-center">
                <span class="no-underline text-info-content">
                    <span class="material-symbols-outlined text-base relative top-1">link</span>
                </span>
            </sup>
        </span>
        """


def content_citations(md: "Markdown") -> None:
    def parse_content_citation(inline: InlineParser, match: Match[str], state: InlineState) -> int:
        uuid = match.group("uuid")
        state.append_token({"type": "content_citation", "raw": uuid})
        return match.end()

    def render_content_citation(renderer: TailwindRenderer, uuid: str) -> str:
        return content_citation_element(uuid)

    md.inline.register("content_citation", CONTENT_CITATION_PATTERN, parse_content_citation, before="link")
    if md.renderer and md.renderer.NAME == "html":
        md.renderer.register("content_citation", render_content_citation)


def incomplete_footnote(md: "Markdown") -> None:
    def parse_incomplete_footnote(inline: InlineParser, match: Match[str], state: InlineState) -> int:
        state.append_token({"type": "incomplete_footnote", "raw": ""})
        return match.end()

    def render_incomplete_footnote(renderer: HTMLRenderer, uuid: str) -> str:
        return ""

    md.inline.register("incomplete_footnote", INCOMPLETE_FOOTNOTE_PATTERN, parse_incomplete_footnote, before="link")
    if md.renderer and md.renderer.NAME == "html":
        md.renderer.register("incomplete_footnote", render_incomplete_footnote)


class BaseMarkdownRenderer(HTMLRenderer):
    html_character_reference_re = re.compile(r"(&(?:[a-z0-9]+|#[0-9]{1,6}|#x[0-9a-fA-F]{1,6});)")

    allowed_inline_html = ["<br />", "<br>"]
    escape_chars = ["<", ">"]

    def inline_html(self, html: str) -> str:
        if html in self.allowed_inline_html:
            return html

        return super().inline_html(html)

    def text(self, text: str) -> str:
        escaped_text = ""

        # Rescue HTML character entities
        for i, match in enumerate(self.html_character_reference_re.split(text)):
            # Odd indexes are always the regex matches
            escaped_text += super().text(match) if i % 2 == 0 else match

        return escaped_text


TABLE_CELL_ALIGNMENT_CLASSES = {"left": "text-left", "right": "text-right", "center": "text-center"}


class TailwindRenderer(BaseMarkdownRenderer):
    def heading(self, text: str, level: int, **attrs) -> str:
        return f"<h{level}>{text}</h{level}>"

    def paragraph(self, text: str) -> str:
        return f"<p>{text}</p>"

    def block_quote(self, text: str) -> str:
        return f"<blockquote>{text}</blockquote>"

    def list(self, text: str, ordered: bool, **attrs) -> str:
        tag = "ol" if ordered else "ul"
        list_class = "list-decimal" if ordered else "list-disc"
        return f'<{tag} class="{list_class} pl-5">{text}</{tag}>'

    def list_item(self, text: str) -> str:
        return f"<li>{text}</li>"

    def task_list_item(self, text: str, checked: bool) -> str:
        # `list-none` on the <li> suppresses the bullet inherited from the parent <ul>'s
        # list-disc, so task items render with only the checkbox visible regardless of
        # whether they share the list with regular bullet items.
        checkbox = (
            f'<input class="task-checkbox absolute -left-5 top-1" type="checkbox"'
            f"{' checked' if checked else ''} disabled>"
        )
        return f'<li class="!my-1 list-none relative">{checkbox}{text}</li>'

    def link(self, text: str, url: str, title=None) -> str:
        safe = self.safe_url(url)
        title_attr = f' title="{safe_entity(title)}"' if title else ""
        return f'<a href="{safe}" class="link"{title_attr} target="_blank" rel="noopener noreferrer">{text}</a>'

    def table(self, text: str) -> str:
        return '<table class="w-full border-collapse table-fixed">\n' + text + "</table>\n"

    def table_cell(self, text: str, align: str | None = None, head: bool = False) -> str:
        alignment_class = TABLE_CELL_ALIGNMENT_CLASSES.get(align or "")
        if head:
            tag = "th"
            class_attr = f"border border-base-300 p-1.5 font-semibold bg-base-200/50 {alignment_class or 'text-left'}"
        else:
            tag = "td"
            base = "border border-base-300 p-1.5"
            class_attr = f"{base} {alignment_class}" if alignment_class else base
        return f'  <{tag} class="{class_attr}">{text}</{tag}>\n'


renderer = TailwindRenderer()
plugins = [
    mentions,
    table,
    url,
    task_lists,
    strikethrough,
    content_citations,
    incomplete_footnote,
    hard_break,
]
plugins_typed: list[Plugin] = [cast(Plugin, plugin) for plugin in plugins]
markdown = mistune.create_markdown(renderer=renderer, plugins=plugins_typed)


def render_markdown(text: str) -> Markup:
    return Markup(markdown(text))


@dataclass
class MarkdownCitationFormatter:
    results_by_id: dict[UUID, Content] = field(default_factory=dict)
    footnotes: dict[int, dict[str, str | None]] = field(default_factory=dict)
    _content_id_to_footnote: dict[str, int] = field(default_factory=dict, init=False)

    def format(self, markdown: str) -> str:
        if not markdown:
            return markdown

        self._map_matches_to_footnotes(markdown)
        with_replaced_citations = self._replace_matches(markdown)
        return self._append_footnote_block(with_replaced_citations)

    def _map_matches_to_footnotes(self, markdown: str) -> None:
        footnote_counter = 1
        matches = list(re.finditer(CONTENT_CITATION_PATTERN, markdown))

        for match in matches:
            content_id_str = match.group(1)
            if content_id_str in self._content_id_to_footnote:
                continue

            content_id = UUID(content_id_str)
            if content_id in self.results_by_id:
                content = self.results_by_id[content_id]
                self._content_id_to_footnote[content_id_str] = footnote_counter
                url = citation_url(content)
                self.footnotes[footnote_counter] = {"title": content.title, "url": url}
                footnote_counter += 1

    def _replace_matches(self, markdown: str):
        def _replace_token(token_match: re.Match[str]) -> str:
            token_id_str = token_match.group(1)
            if token_id_str in self._content_id_to_footnote:
                footnote_num = self._content_id_to_footnote[token_id_str]
                url = self.footnotes[footnote_num]["url"]
                if not url:
                    return f"<sup>[{footnote_num}]</sup>"
                return f"<sup>[{footnote_num}]({url})</sup>"
            return ""

        result = re.sub(CONTENT_CITATION_PATTERN, _replace_token, markdown)
        result = re.sub(r"</sup><sup>", ",</sup> <sup>", result)
        return result

    def _append_footnote_block(self, markdown: str) -> str:
        if self.footnotes:
            if not markdown.endswith("\n"):
                markdown += "\n"
            markdown += "\n"
            markdown += "### References\n\n"

            for num in sorted(self.footnotes):
                title = self.footnotes[num]["title"]
                url = self.footnotes[num]["url"]
                if not url:
                    markdown += f"{num}. {title}\n"
                else:
                    markdown += f"{num}. [{title}]({url})\n"

        return markdown


def with_markdown_format_citations(text: str, results_by_id: dict[UUID, Content]) -> str:
    return MarkdownCitationFormatter(results_by_id).format(text)
