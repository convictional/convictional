import json
from pathlib import Path

import pytest

from app.helpers.html import render_email_html

# The whitespace contract is pinned in cases.json. Each case's `email_target` is the raw
# render_email_html(wire) output (the authored compose path) both this renderer and PR4's
# cross-surface normalizer build against. Asserting byte-for-byte here fails loudly on any
# regression that reintroduces a cosmetic \n, un-tightens an empty block, drops the
# table-head <tr>, or lets the sanitizer collapse a run.
_CASES = json.loads((Path(__file__).parents[2] / "fixtures" / "markdown_whitespace" / "cases.json").read_text())[
    "cases"
]
_EMAIL_CONFORMANCE_CASES = [case for case in _CASES if case.get("email_target") is not None]


@pytest.mark.parametrize("case", _EMAIL_CONFORMANCE_CASES, ids=[case["name"] for case in _EMAIL_CONFORMANCE_CASES])
def test_email_target_conformance(case):
    assert str(render_email_html(case["wire"])) == case["email_target"]


def test_email_conformance_set_covers_code_block_regression_guard():
    # code_block_fenced is the guard that the nh3 <pre>/<code>-aware fix keeps code-block
    # whitespace intact; a fixture edit that drops it must not silently shrink coverage.
    names = {case["name"] for case in _EMAIL_CONFORMANCE_CASES}
    assert "code_block_fenced" in names
    assert len(_EMAIL_CONFORMANCE_CASES) > 10


def test_render_email_html_with_quoted_html_directive():
    # Test that quoted HTML directive is processed correctly with <div> element
    markdown_with_directive = """# Email Content

:::quoted_html
<p>This is quoted HTML content.</p>
<strong>Bold text in HTML</strong>
:::

Regular markdown paragraph."""

    result = render_email_html(markdown_with_directive)

    # Should contain basic markdown rendering
    assert "Email Content" in result
    assert "Regular markdown paragraph" in result

    # The directive should be processed as <div> element with quote_container class
    assert '<div class="quote_container"' in result

    # Should NOT have <details> or <summary> (that's done client-side)
    assert "<details" not in result
    assert "<summary" not in result

    # Content should be inside the quote_container div
    assert "<p>This is quoted HTML content.</p>" in result
    assert "<strong>Bold text in HTML</strong>" in result

    # Should have the wrapper styling
    assert 'style="border-left: 4px solid #d1d5db' in result

    # Should not contain unprocessed directive markers
    assert ":::" not in result


def test_render_email_html_comprehensive():
    # Test email HTML rendering with various markdown features
    complex_markdown = """# Main Title

Regular **bold** and *italic* text.

- List item 1
- List item 2

[Link to example](https://example.com)

> This is a blockquote

`inline code` and:

```
code block
```

Final paragraph."""

    result = render_email_html(complex_markdown)

    # Should handle all markdown features correctly
    assert "Main Title" in result
    assert "<strong>bold</strong>" in result
    assert "<em>italic</em>" in result
    assert "<ul" in result
    assert "<li" in result
    assert 'href="https://example.com"' in result
    assert "<blockquote" in result
    assert "<code" in result
    assert "Final paragraph" in result

    # Should process without errors and be substantial
    assert len(result) > 200


def test_hardbreak():
    test = """Line one.  \nLine two."""

    # The cosmetic newline mistune emits after <br> is stripped so pre-wrap display
    # does not double the break (the whitespace contract).
    expected_html = """<div><div>Line one.<br>Line two.</div></div>"""
    assert render_email_html(test).strip() == expected_html.strip()


def test_empty_paragraphs():
    # Test Gmail-style empty paragraph rendering
    test = """Para 1

<br />

Para 2"""

    expected_html = """<div><div>Para 1</div><div><br></div><div>Para 2</div></div>"""
    assert render_email_html(test).strip() == expected_html.strip()


def test_multiple_empty_paragraphs():
    # Test multiple empty lines
    test = """Para 1

<br />

<br />

Para 2"""

    expected_html = """<div><div>Para 1</div><div><br></div><div><br></div><div>Para 2</div></div>"""
    assert render_email_html(test).strip() == expected_html.strip()
