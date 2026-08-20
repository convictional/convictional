from lib.markdown import (
    markdown_to_plain_text,
    preview_excerpt,
)


def test_markdown_to_plain_text_basic_formatting():
    # Empty / None pass through.
    assert markdown_to_plain_text(None) == ""
    assert markdown_to_plain_text("") == ""

    # Plain text is preserved with whitespace collapsed.
    assert markdown_to_plain_text("Hello there") == "Hello there"
    assert markdown_to_plain_text("Line one\n\nLine two") == "Line one Line two"

    # Emphasis markers are stripped.
    assert markdown_to_plain_text("**bold** and *italic*") == "bold and italic"
    assert markdown_to_plain_text("~~struck~~") == "struck"
    assert markdown_to_plain_text("`code` inline") == "code inline"


def test_markdown_to_plain_text_links_keep_visible_text():
    assert markdown_to_plain_text("Check out [this link](https://example.com)") == "Check out this link"
    # Bare URLs render as their own visible text.
    assert markdown_to_plain_text("See https://example.com") == "See https://example.com"


def test_markdown_to_plain_text_images_substitute_alt():
    # Alt text survives.
    assert markdown_to_plain_text("![a cat](https://example.com/cat.png)") == "[a cat]"
    # Empty alt falls back to a generic placeholder.
    assert markdown_to_plain_text("![](https://example.com/cat.png)") == "[image]"
    # Mixed with prose.
    assert markdown_to_plain_text("look ![logo](https://x.com/l.png) here") == "look [logo] here"


def test_markdown_to_plain_text_block_constructs():
    # Headings collapse to their text.
    assert markdown_to_plain_text("# Heading\n\nbody") == "Heading body"
    # Lists become space-separated items.
    assert markdown_to_plain_text("- one\n- two\n- three") == "one two three"
    # Block quotes lose the leading ">".
    assert markdown_to_plain_text("> quoted line") == "quoted line"
    # Fenced code blocks render as their contents.
    assert markdown_to_plain_text("```\nprint('hi')\n```") == "print('hi')"


def test_markdown_to_plain_text_html_inline_is_stripped():
    # Raw HTML in a chat message is sanitized away by the strip pass.
    assert markdown_to_plain_text("<p>Hello <strong>there</strong></p>") == "Hello there"


def test_preview_excerpt_short_text_passthrough():
    # Fits within the budget → returned whole, markers left intact for the caller.
    assert preview_excerpt("Hey @[Bob], thoughts?", "@[Bob]", 500) == "Hey @[Bob], thoughts?"
    # Marker absent → still safe (excerpt_around falls back to a head truncation).
    assert preview_excerpt("no mention here", "@[Bob]", 500) == "no mention here"


def test_preview_excerpt_windows_around_the_marker():
    body = "OPENING " + ("filler word " * 60) + "please review @[Bob] now " + ("more filler " * 60) + "CLOSING"
    result = preview_excerpt(body, "@[Bob]", 200)
    assert "@[Bob]" in result
    assert "please review" in result and "now" in result
    # Far-away text at both ends is dropped, with ellipses marking the trim.
    assert "OPENING" not in result and "CLOSING" not in result
    assert result.startswith("…") and result.endswith("…")
    assert len(result) <= 200 + 2


def test_preview_excerpt_drops_inline_images():
    body = "Here is the logo ![logo](https://x.com/l.png) next to @[Bob]."
    result = preview_excerpt(body, "@[Bob]", 500)
    assert "https://x.com/l.png" not in result and "![" not in result
    assert "@[Bob]" in result
