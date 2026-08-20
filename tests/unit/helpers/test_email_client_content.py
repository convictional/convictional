from app.helpers.html import EmailMarkdownHTMLRenderer, render_email_html
from app.helpers.strings import html_to_plain_text


class TestEmailClientRenderer:
    def test_paragraph_with_inline_styles(self):
        renderer = EmailMarkdownHTMLRenderer()
        result = renderer.paragraph("Hello world")
        assert result == "<div>Hello world</div>"

    def test_headings_with_inline_styles(self):
        renderer = EmailMarkdownHTMLRenderer()

        h1 = renderer.heading("Title", 1)
        assert 'style="font-size: 1.5em; font-weight: bold; margin: 1em 0 0.5em 0;"' in h1
        assert "<h1" in h1 and "</h1>" in h1

        h2 = renderer.heading("Subtitle", 2)
        assert 'style="font-size: 1.3em; font-weight: bold; margin: 1em 0 0.5em 0;"' in h2
        assert "<h2" in h2 and "</h2>" in h2

    def test_link_with_inline_styles(self):
        renderer = EmailMarkdownHTMLRenderer()
        result = renderer.link("Google", "https://google.com", "Search")
        expected = (
            '<a href="https://google.com" style="color: #0066cc; text-decoration: underline;" '
            'title="Search">Google</a>'
        )
        assert result == expected

    def test_image_external_url(self):
        renderer = EmailMarkdownHTMLRenderer()
        result = renderer.image("Alt text", "https://example.com/image.jpg", "Title")
        expected = (
            '<img src="https://example.com/image.jpg" alt="Alt text" '
            'style="max-width: 100%; height: auto;" title="Title">'
        )
        assert result == expected

    def test_blockquote_with_inline_styles(self):
        renderer = EmailMarkdownHTMLRenderer()
        result = renderer.block_quote("Quote text")
        expected = (
            '<blockquote style="margin: 1em 0; padding-left: 1em; border-left: 3px solid #ccc; '
            'color: #666; font-style: italic;">Quote text</blockquote>'
        )
        assert result == expected

    def test_lists_with_inline_styles(self):
        renderer = EmailMarkdownHTMLRenderer()

        ul = renderer.list("content", False)
        assert 'style="margin: 1em 0; padding-left: 2em;"' in ul
        assert "<ul" in ul and "</ul>" in ul
        assert "list-style-type" not in ul

        # A missing depth kwarg defaults to level 0 (decimal).
        ol = renderer.list("content", True)
        assert "margin: 1em 0; padding-left: 2em;" in ol
        assert "<ol" in ol and "</ol>" in ol
        assert "list-style-type: decimal" in ol

        assert "list-style-type: lower-alpha" in renderer.list("x", True, depth=1)
        assert "list-style-type: lower-roman" in renderer.list("x", True, depth=2)
        # Levels deeper than 2 stay lower-roman.
        assert "list-style-type: lower-roman" in renderer.list("x", True, depth=5)

        # End-to-end: depth is threaded through render_email_html, so nested ordered
        # markdown yields decimal → lower-alpha → lower-roman in document order.
        nested_markdown = "1. one\n    1. two\n        1. three\n            1. four\n"
        html = render_email_html(nested_markdown)
        decimal_index = html.find("list-style-type: decimal")
        alpha_index = html.find("list-style-type: lower-alpha")
        roman_index = html.find("list-style-type: lower-roman")
        assert 0 <= decimal_index < alpha_index < roman_index

    def test_table_with_inline_styles(self):
        renderer = EmailMarkdownHTMLRenderer()

        table = renderer.table("content")
        assert 'style="border-collapse: collapse; width: 100%; margin: 1em 0;"' in table
        assert "<table" in table and "</table>" in table

        cell = renderer.table_cell("Cell content", head=True)
        assert 'style="padding: 0.5em; border: 1px solid #ddd; font-weight: bold;"' in cell
        assert "<th" in cell and "</th>" in cell

    def test_code_elements_with_inline_styles(self):
        renderer = EmailMarkdownHTMLRenderer()

        inline_code = renderer.codespan("code")
        assert (
            'style="background-color: #f5f5f5; padding: 0.2em 0.4em; '
            'border-radius: 3px; font-family: monospace;"' in inline_code
        )

        block_code = renderer.block_code("print('hello')")
        assert (
            'style="background-color: #f5f5f5; padding: 1em; border-radius: 5px; '
            'overflow-x: auto; font-family: monospace; margin: 1em 0;"' in block_code
        )


class TestRenderEmailMarkdown:
    def test_empty_string(self):
        result = render_email_html("")
        assert result == ""

    def test_none_input(self):
        result = render_email_html(None)
        assert result == ""

    def test_basic_formatting(self):
        markdown = "This is **bold** and *italic* text"
        result = render_email_html(markdown)
        assert "<strong>bold</strong>" in result
        assert "<em>italic</em>" in result
        assert "<div>" in result

    def test_headings(self):
        markdown = "# Main Title\n## Subtitle"
        result = render_email_html(markdown)
        assert "<h1" in result and "</h1>" in result
        assert "<h2" in result and "</h2>" in result
        assert "font-size: 1.5em" in result
        assert "font-size: 1.3em" in result

    def test_links(self):
        markdown = "[Google](https://google.com)"
        result = render_email_html(markdown)
        assert 'href="https://google.com"' in result
        assert 'style="color: #0066cc; text-decoration: underline;"' in result

    def test_blockquotes(self):
        markdown = "> This is a quote"
        result = render_email_html(markdown)
        assert "<blockquote" in result and "</blockquote>" in result
        assert "border-left: 3px solid #ccc" in result

    def test_lists(self):
        markdown = """
- Item 1
- Item 2

1. Numbered 1
2. Numbered 2
        """
        result = render_email_html(markdown)
        assert "<ul" in result and "</ul>" in result
        assert "<ol" in result and "</ol>" in result
        assert "padding-left: 2em" in result

    def test_tables(self):
        markdown = """
| Header 1 | Header 2 |
|----------|----------|
| Cell 1   | Cell 2   |
        """
        result = render_email_html(markdown)
        assert "<table" in result and "</table>" in result
        assert "<th" in result and "</th>" in result
        assert "<td" in result and "</td>" in result
        assert "border-collapse: collapse" in result

    def test_inline_code(self):
        markdown = "Use `print('hello')` to output"
        result = render_email_html(markdown)
        assert "<code" in result and "</code>" in result
        assert "font-family: monospace" in result

    def test_code_blocks(self):
        markdown = """
```python
def hello():
    return "world"
```
        """
        result = render_email_html(markdown)
        assert "<pre" in result and "</pre>" in result
        assert "<code>" in result and "</code>" in result

    def test_strikethrough(self):
        markdown = "~~strikethrough text~~"
        result = render_email_html(markdown)
        assert "<del>strikethrough text</del>" in result

    def test_attachment_references(self):
        markdown = "![Alt text](image.jpg)"
        result = render_email_html(markdown)
        assert 'alt="Alt text"' in result

    def test_html_sanitization(self):
        markdown = 'Hello <script>alert("xss")</script> world'
        result = render_email_html(markdown)
        assert "<script>" not in result
        # The sanitizer HTML-escapes dangerous content rather than removing it
        assert "&lt;script&gt;" in result or "script" not in result
        assert "Hello" in result
        assert "world" in result

    def test_complex_document(self):
        markdown = """
# Email Newsletter

Welcome to our **newsletter**!

## Features
- Email-safe HTML
- Inline styles
- [Links](https://example.com)

> Important note about our service

| Feature | Status |
|---------|--------|
| Email   | ✓      |
| Mobile  | ✓      |

Contact us at `support@example.com`.
        """
        result = render_email_html(markdown)

        # Check all major elements are present
        assert "<h1" in result and "Email Newsletter" in result
        assert "<h2" in result and "Features" in result
        assert "<strong>newsletter</strong>" in result
        assert "<ul" in result and "<li" in result
        assert 'href="https://example.com"' in result
        assert "<blockquote" in result and "Important note" in result
        assert "<table" in result and "<th" in result and "<td" in result
        assert "<code" in result and "support@example.com" in result

        # Check inline styles are present (for non-paragraph elements)
        assert "<div>" in result
        assert 'style="color: #0066cc; text-decoration: underline;"' in result
        assert 'style="border-collapse: collapse; width: 100%; margin: 1em 0;"' in result


def test_html_to_plain_text():
    # Test empty/None inputs
    assert html_to_plain_text("") == ""
    assert html_to_plain_text(None) == ""

    # Test basic HTML to text conversion
    assert html_to_plain_text("<div>Hello world</div>") == "Hello world"

    # Test formatting removal
    html = "<p><strong>Bold</strong> and <em>italic</em> text</p>"
    result = html_to_plain_text(html)
    assert result == "Bold and italic text"
    assert "**" not in result and "*" not in result

    # Test link text preservation with URL in parentheses format
    html = '<a href="https://example.com">Click here</a>'
    result = html_to_plain_text(html)
    assert "Click here" in result
    assert "https://example.com" in result
    assert "Click here (https://example.com)" in result

    # Test image removal
    html = '<p>Text <img src="image.jpg" alt="Image"> more text</p>'
    result = html_to_plain_text(html)
    assert result.strip() == "Text more text"
    assert "image.jpg" not in result

    # Test blockquotes are converted to "> " prefixed lines
    html = "<blockquote>Important note about our service</blockquote>"
    result = html_to_plain_text(html)
    assert "> Important note about our service" in result

    # Test multi-line blockquotes
    html = "<blockquote>Line one\nLine two</blockquote>"
    result = html_to_plain_text(html)
    assert "> Line one" in result
    assert "> Line two" in result

    # Test block elements are separated by newlines (not merged together)
    html = "<p>First paragraph</p><p>Second paragraph</p>"
    result = html_to_plain_text(html)
    assert "First paragraph" in result
    assert "Second paragraph" in result
    assert "First paragraphSecond" not in result

    # Test complex document
    html = """
    <h1>Newsletter</h1>
    <p>Welcome to our <strong>newsletter</strong>!</p>
    <ul><li>First item</li><li>Second item with <a href="https://example.com">link</a></li></ul>
    <blockquote>Important note</blockquote>
    <table><tr><th>Header</th><td>Data</td></tr></table>
    """
    result = html_to_plain_text(html)
    assert "Newsletter" in result
    assert "Welcome to our newsletter!" in result
    assert "First item" in result
    assert "> Important note" in result
    assert "Header" in result
    assert "Data" in result
    assert "<h1>" not in result and "<strong>" not in result
    # Should contain URLs in parentheses format now
    assert "link (https://example.com)" in result
