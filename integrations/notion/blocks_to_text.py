from collections.abc import Iterable
from typing import Any

# Block types we render. Anything not in this set is skipped silently. Media blocks
# (image/file/pdf/video/audio) render using the original Notion URL read directly from the
# block payload; embed/link_preview remain out of scope.
SUPPORTED_TEXT_BLOCKS = frozenset(
    {
        "paragraph",
        "heading_1",
        "heading_2",
        "heading_3",
        "bulleted_list_item",
        "numbered_list_item",
        "to_do",
        "toggle",
        "quote",
        "code",
        "divider",
        "callout",
        "table",
        "image",
        "file",
        "pdf",
        "video",
        "audio",
        "bookmark",
        "equation",
    }
)

MEDIA_LINK_BLOCKS = frozenset({"file", "pdf", "video", "audio"})


# List-item blocks stay "tight" (separated by a single newline) so nested-list indentation
# survives. Every other block boundary gets a blank line: Markdown only keeps block-level
# elements distinct when they're separated by one. Joining everything with a single newline
# merges consecutive paragraphs and — worse — pulls the line after a quote into the quote as
# a lazy continuation, silently absorbing the following block (e.g. a callout) into it.
LIST_ITEM_BLOCKS = frozenset({"bulleted_list_item", "numbered_list_item", "to_do"})


def blocks_to_text(blocks: Iterable[dict[str, Any]]) -> str:
    """Render a flat sequence of Notion blocks (as produced by NotionClient.walk_page_blocks)
    into a markdown-flavored text string.

    Blocks must carry a `_depth` integer (the walker adds this) for indentation. Blocks may
    optionally carry `_synced_duplicate=True` — those are skipped to avoid double-emitting
    content from synced_block duplicates.

    Media blocks (image/file/pdf/video/audio) reference the original Notion URL read directly
    from the block payload (`file`-type signed URLs or `external` URLs); a block with no usable
    URL renders nothing.
    """
    rendered: list[tuple[bool, str]] = []
    for block in blocks:
        if block.get("_synced_duplicate"):
            continue
        block_type = block.get("type")
        if block_type not in SUPPORTED_TEXT_BLOCKS:
            continue
        depth = int(block.get("_depth", 0))
        text = _render_block(block, block_type, depth)
        if text is not None:
            rendered.append((block_type in LIST_ITEM_BLOCKS, text))

    if not rendered:
        return ""

    out = rendered[0][1]
    for index in range(1, len(rendered)):
        prev_is_list = rendered[index - 1][0]
        curr_is_list, text = rendered[index]
        separator = "\n" if prev_is_list and curr_is_list else "\n\n"
        out += separator + text
    return out


def _render_block(block: dict[str, Any], block_type: str, depth: int) -> str | None:
    indent = "  " * depth
    payload = block.get(block_type) or {}

    if block_type == "image" or block_type in MEDIA_LINK_BLOCKS:
        return _render_media(block_type, payload)

    if block_type == "table":
        return _render_table(block, payload)

    if block_type == "bookmark":
        url = payload.get("url")
        if not url:
            return None
        caption = _render_rich_text(payload.get("caption") or [])
        return f"[{caption or url}]({url})"

    if block_type == "equation":
        # A Notion equation is block-level LaTeX; render it as a plain (un-highlighted) fenced
        # code block, mirroring the `code` branch's fence idiom so multi-line LaTeX survives.
        expression = payload.get("expression") or ""
        if not expression:
            return None
        fence = f"{indent}```"
        body = "\n".join(f"{indent}{line}" for line in expression.splitlines())
        return f"{fence}\n{body}\n{fence}"

    if block_type == "divider":
        return f"{indent}---"

    if block_type == "code":
        rich_text = payload.get("rich_text") or []
        language = payload.get("language") or ""
        content = "".join(item.get("plain_text", "") for item in rich_text if isinstance(item, dict))
        fence_open = f"{indent}```{language}".rstrip()
        fence_close = f"{indent}```"
        body = "\n".join(f"{indent}{line}" for line in content.splitlines()) if content else ""
        return f"{fence_open}\n{body}\n{fence_close}" if body else f"{fence_open}\n{fence_close}"

    text = _render_rich_text(payload.get("rich_text") or [])

    if block_type == "paragraph":
        return f"{indent}{text}" if text else None

    if block_type == "heading_1":
        return f"{indent}# {text}"
    if block_type == "heading_2":
        return f"{indent}## {text}"
    if block_type == "heading_3":
        return f"{indent}### {text}"

    if block_type == "bulleted_list_item":
        return f"{indent}- {text}"

    if block_type == "numbered_list_item":
        # Notion API doesn't track numbering; the renderer must — we keep it simple and
        # emit "1." for every item. Markdown renderers re-number on display anyway.
        return f"{indent}1. {text}"

    if block_type == "to_do":
        checked = bool(payload.get("checked"))
        marker = "[x]" if checked else "[ ]"
        return f"{indent}- {marker} {text}"

    if block_type == "toggle":
        return f"{indent}{text}" if text else None

    if block_type == "quote":
        return f"{indent}> {text}"

    if block_type == "callout":
        # Drop the emoji icon for v1; render just the text.
        return f"{indent}{text}"

    return None


def _render_media(block_type: str, payload: dict[str, Any]) -> str | None:
    url = _media_url(payload)
    if not url:
        return None

    caption = _render_rich_text(payload.get("caption") or [])
    if block_type == "image":
        return f"![{caption}]({url})"

    # RTE has no embed node for file/pdf/video/audio, so a link is the faithful representation.
    label = caption or payload.get("name") or block_type
    return f"[{label}]({url})"


def _media_url(payload: dict[str, Any]) -> str | None:
    # Notion sometimes returns a media block with neither `file` nor `external` populated —
    # e.g. an uploaded image the integration hasn't been granted file access to comes back as
    # just `{"caption": []}`. There's no URL to reference, so the block renders nothing; the
    # fix is Notion-side (re-share the page/file with the connection), not here.
    file_ref = payload.get("file")
    if isinstance(file_ref, dict) and file_ref.get("url"):
        return file_ref["url"]
    external = payload.get("external")
    if isinstance(external, dict) and external.get("url"):
        return external["url"]
    return None


def _render_table(block: dict[str, Any], payload: dict[str, Any]) -> str | None:
    # GFM tables can't be meaningfully indented, so we emit at column 0 and ignore
    # `_depth`. A table nested in a toggle/column thus renders flush-left; this is a
    # known v1 limitation (the alternative — HTML <table> — defeats round-tripping).
    rows = block.get("_table_rows") or []
    cell_rows = [_render_table_row(row) for row in rows if isinstance(row, dict)]

    column_count = payload.get("table_width")
    if not isinstance(column_count, int) or column_count <= 0:
        column_count = max((len(cells) for cells in cell_rows), default=0)
    if column_count <= 0:
        return None

    def line(cells: list[str]) -> str:
        padded = (cells + [""] * column_count)[:column_count]
        return "| " + " | ".join(padded) + " |"

    if payload.get("has_column_header") and cell_rows:
        header, *body = cell_rows
    else:
        # Notion headerless tables have no header row; GFM requires one, so synthesize
        # a blank header so the table still parses as a table rather than paragraphs.
        header, body = [""] * column_count, cell_rows

    separator = "| " + " | ".join(["---"] * column_count) + " |"
    return "\n".join([line(header), separator, *(line(cells) for cells in body)])


def _render_table_row(row: dict[str, Any]) -> list[str]:
    cells = row.get("cells") or []
    return [_render_table_cell(cell if isinstance(cell, list) else []) for cell in cells]


def _render_table_cell(cell: list[dict[str, Any]]) -> str:
    # GFM cells are single-line and pipe-delimited: newlines become <br>, literal pipes
    # are escaped so they don't split the cell.
    return _render_rich_text(cell).replace("\n", "<br>").replace("|", "\\|")


def _render_rich_text(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        parts.append(_render_rich_text_item(item))
    return "".join(parts)


def _render_rich_text_item(item: dict[str, Any]) -> str:
    plain = item.get("plain_text", "") or ""
    annotations = item.get("annotations") or {}

    # For mentions, Notion's plain_text is already the canonical display (e.g. "@Alice",
    # the page title, the ISO date). Use it verbatim — the API gives us no better signal here.
    href: str | None = None
    item_type = item.get("type")
    if item_type == "text":
        text_payload = item.get("text") or {}
        link = text_payload.get("link") or {}
        href = link.get("url") if isinstance(link, dict) else None
    elif item_type == "mention":
        href = item.get("href")

    rendered = plain

    if annotations.get("code"):
        rendered = f"`{rendered}`"
    if annotations.get("bold"):
        rendered = f"**{rendered}**"
    if annotations.get("italic"):
        rendered = f"*{rendered}*"
    if annotations.get("strikethrough"):
        rendered = f"~~{rendered}~~"

    if href:
        rendered = f"[{rendered}]({href})"

    return rendered
