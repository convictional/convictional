from typing import Any

from integrations.notion.blocks_to_text import blocks_to_text


def _text_item(content: str, **annotations: Any) -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": content, "link": None},
        "plain_text": content,
        "href": None,
        "annotations": {
            "bold": annotations.get("bold", False),
            "italic": annotations.get("italic", False),
            "strikethrough": annotations.get("strikethrough", False),
            "underline": False,
            "code": annotations.get("code", False),
            "color": "default",
        },
    }


def _link_item(content: str, url: str) -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": content, "link": {"url": url}},
        "plain_text": content,
        "href": url,
        "annotations": {
            "bold": False,
            "italic": False,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default",
        },
    }


def _mention_item(display: str, href: str | None = None) -> dict[str, Any]:
    return {
        "type": "mention",
        "mention": {"type": "page", "page": {"id": "page-123"}},
        "plain_text": display,
        "href": href,
        "annotations": {
            "bold": False,
            "italic": False,
            "strikethrough": False,
            "underline": False,
            "code": False,
            "color": "default",
        },
    }


def _block(block_type: str, payload: dict[str, Any], depth: int = 0, **extra: Any) -> dict[str, Any]:
    return {"id": f"{block_type}-id", "type": block_type, block_type: payload, "_depth": depth, **extra}


def test_blocks_to_text_renders_all_supported_types_and_indents_children():
    blocks = [
        _block("heading_1", {"rich_text": [_text_item("Quarterly Plan")]}),
        _block("heading_2", {"rich_text": [_text_item("Goals")]}),
        _block("heading_3", {"rich_text": [_text_item("Q1")]}),
        _block(
            "paragraph",
            {
                "rich_text": [
                    _text_item("This is "),
                    _text_item("bold", bold=True),
                    _text_item(" and "),
                    _text_item("italic", italic=True),
                    _text_item(" and "),
                    _text_item("code", code=True),
                    _text_item(" and "),
                    _text_item("strike", strikethrough=True),
                    _text_item(" with a "),
                    _link_item("link", "https://example.com"),
                    _text_item(" and a "),
                    _mention_item("@Alice"),
                    _text_item("."),
                ]
            },
        ),
        _block("bulleted_list_item", {"rich_text": [_text_item("First bullet")]}),
        _block("bulleted_list_item", {"rich_text": [_text_item("Nested bullet")]}, depth=1),
        _block("numbered_list_item", {"rich_text": [_text_item("First numbered")]}),
        _block("to_do", {"rich_text": [_text_item("Do this thing")], "checked": False}),
        _block("to_do", {"rich_text": [_text_item("Done thing")], "checked": True}),
        _block("toggle", {"rich_text": [_text_item("Open me")]}),
        _block("paragraph", {"rich_text": [_text_item("hidden under toggle")]}, depth=1),
        _block("quote", {"rich_text": [_text_item("To be is to do.")]}),
        _block(
            "code",
            {"rich_text": [_text_item("print('hi')")], "language": "python"},
        ),
        _block("divider", {}),
        _block("callout", {"rich_text": [_text_item("Heads up")], "icon": {"type": "emoji", "emoji": "⚠️"}}),
        _block("image", {"caption": [], "type": "external", "external": {}}),
        {
            "id": "dup",
            "type": "synced_block",
            "synced_block": {"synced_from": {"block_id": "orig"}},
            "_depth": 0,
            "_synced_duplicate": True,
        },
    ]

    expected = "\n".join(
        [
            "# Quarterly Plan",
            "",
            "## Goals",
            "",
            "### Q1",
            "",
            "This is **bold** and *italic* and `code` and ~~strike~~ with a [link](https://example.com) and a @Alice.",
            "",
            "- First bullet",
            "  - Nested bullet",
            "1. First numbered",
            "- [ ] Do this thing",
            "- [x] Done thing",
            "",
            "Open me",
            "",
            "  hidden under toggle",
            "",
            "> To be is to do.",
            "",
            "```python",
            "print('hi')",
            "```",
            "",
            "---",
            "",
            "Heads up",
        ]
    )

    assert blocks_to_text(blocks) == expected


def test_blocks_to_text_separates_blocks_with_blank_lines():
    # Regression: a quote must not absorb the following block as a lazy continuation,
    # and consecutive paragraphs must not merge into one.
    blocks = [
        _block("quote", {"rich_text": [_text_item("A wise quote.")]}),
        _block("callout", {"rich_text": [_text_item("A separate callout.")]}),
        _block("paragraph", {"rich_text": [_text_item("First paragraph.")]}),
        _block("paragraph", {"rich_text": [_text_item("Second paragraph.")]}),
    ]

    expected = "\n".join(
        [
            "> A wise quote.",
            "",
            "A separate callout.",
            "",
            "First paragraph.",
            "",
            "Second paragraph.",
        ]
    )

    assert blocks_to_text(blocks) == expected


def test_blocks_to_text_keeps_code_block_interior_tight():
    # The blank-line separation must not leak inside a fenced code block.
    blocks = [
        _block("paragraph", {"rich_text": [_text_item("Before.")]}),
        _block("code", {"rich_text": [_text_item("line one\nline two")], "language": "python"}),
        _block("paragraph", {"rich_text": [_text_item("After.")]}),
    ]

    expected = "\n".join(
        [
            "Before.",
            "",
            "```python",
            "line one",
            "line two",
            "```",
            "",
            "After.",
        ]
    )

    assert blocks_to_text(blocks) == expected


def test_blocks_to_text_skips_empty_and_unknown_block_types():
    blocks = [
        _block("paragraph", {"rich_text": []}),
        {"type": "unsupported", "unsupported": {"block_type": "form"}, "_depth": 0},
        {"type": "embed", "embed": {"url": "https://x"}, "_depth": 0},
    ]
    # Empty paragraph still emits an empty line; unsupported/embed are skipped entirely.
    assert blocks_to_text(blocks) == ""


def _table_block(
    rows: list[list[list[dict[str, Any]]]], *, has_header: bool, width: int | None = None
) -> dict[str, Any]:
    return {
        "id": "table-id",
        "type": "table",
        "table": {
            "table_width": width if width is not None else (len(rows[0]) if rows else 0),
            "has_column_header": has_header,
            "has_row_header": False,
        },
        "_depth": 0,
        "_table_rows": [{"cells": row} for row in rows],
    }


def test_blocks_to_text_renders_table_with_and_without_header_and_sanitizes_cells():
    # With a column header, row 0 is the header. Cells exercise inline marks (bold/italic/
    # code/link via _render_rich_text), embedded pipes (escaped), and multi-line text (<br>).
    header_table = _table_block(
        [
            [[_text_item("Name")], [_text_item("Detail")]],
            [
                [_text_item("Bold", bold=True), _text_item(" & "), _text_item("code", code=True)],
                [_text_item("a | b"), _link_item(" link", "https://x")],
            ],
            [[_text_item("line one\nline two")], []],
        ],
        has_header=True,
    )

    # Without a header, GFM still needs one, so a blank header row is synthesized.
    headerless_table = _table_block(
        [
            [[_text_item("only")], [_text_item("row")]],
        ],
        has_header=False,
    )

    assert blocks_to_text([header_table]) == "\n".join(
        [
            "| Name | Detail |",
            "| --- | --- |",
            "| **Bold** & `code` | a \\| b[ link](https://x) |",
            "| line one<br>line two |  |",
        ]
    )

    assert blocks_to_text([headerless_table]) == "\n".join(
        [
            "|  |  |",
            "| --- | --- |",
            "| only | row |",
        ]
    )


def test_blocks_to_text_table_gets_blank_line_separation_and_handles_ragged_rows():
    # A table is not a list item, so it gets blank-line separation from neighbors. Ragged
    # rows (fewer cells than table_width) are padded; column count falls back to max row
    # length when table_width is missing/invalid.
    blocks = [
        _block("paragraph", {"rich_text": [_text_item("Before.")]}),
        {
            "id": "t",
            "type": "table",
            "table": {"table_width": 3, "has_column_header": True},
            "_depth": 0,
            "_table_rows": [
                {"cells": [[_text_item("A")], [_text_item("B")], [_text_item("C")]]},
                {"cells": [[_text_item("1")]]},
            ],
        },
        _block("paragraph", {"rich_text": [_text_item("After.")]}),
    ]

    assert blocks_to_text(blocks) == "\n".join(
        [
            "Before.",
            "",
            "| A | B | C |",
            "| --- | --- | --- |",
            "| 1 |  |  |",
            "",
            "After.",
        ]
    )


def test_blocks_to_text_renders_media_from_payload_and_skips_when_no_url():
    image = _block("image", {"caption": [_text_item("A diagram")], "type": "file", "file": {"url": "https://s3/x"}})
    file_block = _block("file", {"caption": [], "type": "file", "file": {"url": "https://s3/y"}, "name": "report.pdf"})
    pdf = _block("pdf", {"caption": [_text_item("Spec")], "type": "external", "external": {"url": "https://e/z"}})
    video = _block("video", {"caption": [], "type": "file", "file": {"url": "https://s3/v"}, "name": "demo.mp4"})
    audio = _block("audio", {"caption": [], "type": "external", "external": {"url": "https://e/a"}})
    no_url = _block("image", {"caption": [], "type": "file", "file": {}}, id="img-skip")

    expected = "\n\n".join(
        [
            "![A diagram](https://s3/x)",
            "[report.pdf](https://s3/y)",
            "[Spec](https://e/z)",
            "[demo.mp4](https://s3/v)",
            "[audio](https://e/a)",
        ]
    )

    assert blocks_to_text([image, file_block, pdf, video, audio, no_url]) == expected
    assert blocks_to_text([no_url]) == ""


def test_blocks_to_text_renders_bookmarks_with_caption_url_fallback_and_skips_when_no_url():
    with_caption = _block("bookmark", {"url": "https://example.com", "caption": [_text_item("Example site")]})
    without_caption = _block("bookmark", {"url": "https://plain.example.com", "caption": []})
    no_url = _block("bookmark", {"url": "", "caption": [_text_item("ignored")]})

    expected = "\n\n".join(
        [
            "[Example site](https://example.com)",
            # No caption -> the url itself is the link text.
            "[https://plain.example.com](https://plain.example.com)",
        ]
    )

    assert blocks_to_text([with_caption, without_caption, no_url]) == expected
    assert blocks_to_text([no_url]) == ""


def test_blocks_to_text_renders_equation_as_fenced_code_block_and_keeps_ordering():
    # An empty/missing expression renders nothing; a non-list block gets blank-line separation
    # from its neighbors so ordering and separators are preserved.
    blocks = [
        _block("paragraph", {"rich_text": [_text_item("Before.")]}),
        _block("equation", {"expression": "E = mc^2"}),
        _block("equation", {"expression": ""}),
        _block("paragraph", {"rich_text": [_text_item("After.")]}),
    ]

    expected = "\n".join(
        [
            "Before.",
            "",
            "```",
            "E = mc^2",
            "```",
            "",
            "After.",
        ]
    )

    assert blocks_to_text(blocks) == expected


def test_blocks_to_text_renders_nested_link_with_bold_annotation():
    blocks = [
        _block(
            "paragraph",
            {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": "click", "link": {"url": "https://x"}},
                        "plain_text": "click",
                        "href": "https://x",
                        "annotations": {
                            "bold": True,
                            "italic": False,
                            "strikethrough": False,
                            "underline": False,
                            "code": False,
                            "color": "default",
                        },
                    }
                ]
            },
        )
    ]
    assert blocks_to_text(blocks) == "[**click**](https://x)"
