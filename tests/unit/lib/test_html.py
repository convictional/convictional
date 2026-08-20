from lib.html import (
    DANGEROUS_CSS_PATTERNS,
    DANGEROUS_HTML_TAGS,
    DANGEROUS_URL_SCHEMES,
    MAX_CSS_SIZE,
    MAX_HTML_SIZE,
    MAX_URL_SIZE,
    SUSPICIOUS_URL_CHARS,
    _is_safe_css,
    _is_safe_url,
    _linkify_bare_urls,
    sanitize_email_html_content,
    strip_html,
)


def test_strip_html():
    assert strip_html("") == ""
    assert strip_html("<p>Hello World</p>") == "Hello World"
    assert strip_html("<script>alert('xss')</script>Hello") == "Hello"
    assert strip_html("<div><p>Hello</p><span>World</span></div>") == "HelloWorld"
    assert strip_html("<div><p>Hello</p><span>World</span></div>", " ") == "Hello World"
    assert strip_html("<ul><li>Item 1</li><li>Item 2</li></ul>", " ") == "Item 1 Item 2"


def test_sanitize_email_html_content():
    # Test empty input
    assert sanitize_email_html_content("") == ""

    # Test size limits
    large_html = "<p>" + "x" * MAX_HTML_SIZE + "</p>"
    assert sanitize_email_html_content(large_html) == ""

    # Test Gmail class normalization
    gmail_html = '<div class="gmail_quote gmail_quote_container">Quoted content</div>'
    result = sanitize_email_html_content(gmail_html)
    assert 'class="gmail_quote gmail_quote_container quote_container"' in result

    # Test basic safe HTML content
    for tag in ["p", "div", "span", "strong", "em", "ul", "li"]:
        html = f"<{tag}>content</{tag}>"
        result = sanitize_email_html_content(html)
        assert f"<{tag}>content</{tag}>" in result

    # Test table-specific content (nh3 enforces proper table structure)
    table_html = "<table><tr><td>content</td></tr></table>"
    result = sanitize_email_html_content(table_html)
    assert "<table>" in result and "<td>content</td>" in result and "</table>" in result

    # Test that dangerous tags are removed
    for tag in DANGEROUS_HTML_TAGS:
        html = f"<p>before</p><{tag}>malicious content</{tag}><p>after</p>"
        result = sanitize_email_html_content(html)
        assert tag not in result
        assert "before" in result
        assert "after" in result

        # For container tags like script/style, content should be preserved
        if tag in ["script", "style", "iframe", "form", "object"]:
            assert f"<{tag}>" not in result
            assert f"</{tag}>" not in result

    # Test disallowed tag handling (video tag should be removed)
    html = "<video>Video content</video>"
    result = sanitize_email_html_content(html)
    assert "<video>" not in result
    assert "</video>" not in result
    assert "Video content" in result

    # Test allowed attributes are preserved
    html = '<a href="https://example.com" title="Example">Link</a>'
    result = sanitize_email_html_content(html)
    assert 'href="https://example.com"' in result
    assert 'title="Example"' in result

    # Use a proper URL for images since relative URLs get filtered
    html = '<img src="https://example.com/image.jpg" alt="Image" width="100" height="50">'
    result = sanitize_email_html_content(html)
    assert 'src="https://example.com/image.jpg"' in result
    assert 'alt="Image"' in result
    assert 'width="100"' in result
    assert 'height="50"' in result

    # Test disallowed attributes are removed
    html = '<p onclick="alert(\'xss\')" data-evil="malicious">Content</p>'
    result = sanitize_email_html_content(html)
    assert "onclick" not in result
    assert "data-evil" not in result
    assert "Content" in result

    # Test safe CSS is preserved
    html = '<p style="color: red; font-size: 14px;">Styled text</p>'
    result = sanitize_email_html_content(html)
    assert 'style="color: red; font-size: 14px;"' in result

    # Test dangerous CSS is removed
    html = "<p style=\"javascript:alert('xss')\">Dangerous styling</p>"
    result = sanitize_email_html_content(html)
    assert "style=" not in result
    assert "javascript" not in result
    assert "Dangerous styling" in result

    # Test safe URLs are preserved
    html = '<a href="https://example.com">Safe link</a>'
    result = sanitize_email_html_content(html)
    assert 'href="https://example.com"' in result

    # Test that target="_blank" is automatically added to links
    html = '<a href="https://example.com">Link without target</a>'
    result = sanitize_email_html_content(html)
    assert 'target="_blank"' in result

    # Test that existing target attribute is overridden to "_blank"
    html = '<a href="https://example.com" target="_self">Link with target</a>'
    result = sanitize_email_html_content(html)
    assert 'target="_blank"' in result
    assert 'target="_self"' not in result

    # Test dangerous URLs are removed
    html = "<a href=\"javascript:alert('xss')\">Dangerous link</a>"
    result = sanitize_email_html_content(html)
    assert "href=" not in result
    assert "javascript" not in result
    assert "Dangerous link" in result


def test_sanitize_email_html_content_preserves_details_elements():
    """Test that <details> and <summary> are allowed through sanitization"""
    html = """
    <div>
        <details class="quote_container">
            <summary>Show more</summary>
            <div>Hidden content</div>
        </details>
    </div>
    """
    result = sanitize_email_html_content(html)

    assert "<details" in result
    assert "<summary>" in result
    assert "Show more" in result
    assert "Hidden content" in result
    assert 'class="quote_container"' in result


def test_sanitize_email_html_content_preserves_details_open_attribute():
    """Test that open attribute is preserved on details element"""
    html = "<details open><summary>Open by default</summary><p>Content</p></details>"
    result = sanitize_email_html_content(html)

    assert "<details" in result
    assert "open" in result or "open=" in result
    assert "<summary>Open by default</summary>" in result


def test_sanitize_email_html_content_comprehensive():
    html = """
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Head titles should be removed</title>
    </head>
    <div class="container">
        <h1>Email Title</h1>
        <p style="color: blue;">This is a <strong>safe</strong> paragraph.</p>
        <script>alert('xss')</script>
        <table border="1">
            <tr>
                <td>Cell 1</td>
                <td>Cell 2</td>
            </tr>
        </table>
        <a href="https://example.com" onclick="malicious()">Safe Link</a>
        <img src="data:image/png;base64,abc123" alt="Safe image">
        <style>body { background: red; }</style>
    </div>
    """

    result = sanitize_email_html_content(html)

    # Should preserve safe content
    assert "Email Title" in result
    assert "safe" in result
    assert "Cell 1" in result
    assert "Cell 2" in result
    assert "Safe Link" in result
    assert "Safe image" in result
    assert 'href="https://example.com"' in result
    assert 'style="color: blue;"' in result
    assert 'target="_blank"' in result  # All links should get target="_blank"

    # Should remove head elements and everything inside of them
    assert "<head>" not in result
    assert "<title>" not in result
    assert "<meta>" not in result
    assert "Head titles should be removed" not in result

    # Should remove dangerous content
    assert "<script>" not in result
    assert "</script>" not in result
    assert "alert" not in result
    assert "onclick" not in result
    assert "malicious" not in result
    assert "<style>" not in result
    assert "</style>" not in result


def test_is_safe_css():
    # Test basic input
    assert _is_safe_css("") is True
    assert _is_safe_css("color: red; font-size: 14px;") is True
    assert _is_safe_css("margin: 10px; padding: 5px;") is True
    assert _is_safe_css("background-color: #ffffff;") is True

    # Test each dangerous pattern
    for pattern in DANGEROUS_CSS_PATTERNS:
        css = f"color: red; {pattern}something;"
        assert _is_safe_css(css) is False, f"Should block CSS containing: {pattern}"

    # Test case insensitive detection
    assert _is_safe_css("color: red; JAVASCRIPT:alert(1);") is False
    assert _is_safe_css("color: red; Expression(alert(1));") is False

    # Test size limit
    large_css = "color: red; " * (MAX_CSS_SIZE // 10)
    assert _is_safe_css(large_css) is False


def test_is_safe_url():
    # Safe URL patterns
    assert _is_safe_url("https://example.com") is True
    assert _is_safe_url("http://example.com") is True
    assert _is_safe_url("mailto:test@example.com") is True
    assert _is_safe_url("/relative/path") is True
    assert _is_safe_url("./relative/path") is True
    assert _is_safe_url("../relative/path") is True
    assert _is_safe_url("#anchor") is True
    assert _is_safe_url("data:image/png;base64,abc123") is True  # Images allowed

    # Test each dangerous scheme
    for scheme in DANGEROUS_URL_SCHEMES:
        if scheme != "data:":  # data: has special handling for images
            url = f"{scheme}malicious_content"
            assert _is_safe_url(url) is False, f"Should block URL with scheme: {scheme}"

    # Test that non-image data URLs are blocked
    assert _is_safe_url("data:text/html,<script>alert(1)</script>") is False
    assert _is_safe_url("data:application/javascript,alert(1)") is False

    # Test each suspicious character
    for char in SUSPICIOUS_URL_CHARS:
        url = f"https://example.com{char}malicious"
        assert _is_safe_url(url) is False, f"Should block URL containing: {repr(char)}"

    # Test edge cases
    assert _is_safe_url("") is False
    large_url = "https://example.com/" + "x" * MAX_URL_SIZE
    assert _is_safe_url(large_url) is False
    assert _is_safe_url("  https://example.com  ") is True


def test_sanitize_email_html_content_removes_empty_lines():
    # Test that empty lines with only whitespace are removed
    html = """<div>
    <style>body { color: red; }</style>

    <p>Content</p>
</div>"""
    result = sanitize_email_html_content(html)
    # Should not have lines with only spaces/tabs
    assert "\n    \n" not in result
    assert "\n        \n" not in result
    # Should have content preserved
    assert "Content" in result
    assert "<p>Content</p>" in result

    # Test that indented empty lines are collapsed
    html = """<table>
    <tr>
        <td>
            <script>alert('xss')</script>


            <p>Cell content</p>
        </td>
    </tr>
</table>"""
    result = sanitize_email_html_content(html)
    # Should not have excessive empty lines
    assert "\n\n\n" not in result
    # Should preserve content
    assert "Cell content" in result
    assert "<p>Cell content</p>" in result
    assert "<table>" in result

    # Test with multiple dangerous tags creating empty lines
    html = """<div>
    <style>.class { color: blue; }</style>

    <script>malicious();</script>

    <link rel="stylesheet" href="evil.css">

    <p>Actual content</p>
</div>"""
    result = sanitize_email_html_content(html)
    # Empty lines should be collapsed
    assert "\n\n\n" not in result
    # No indented-only lines
    assert "\n    \n" not in result
    # Content preserved
    assert "Actual content" in result
    assert "<p>Actual content</p>" in result


def test_sanitize_email_html_content_preserves_code_block_whitespace():
    # Indented lines inside a <pre><code> block keep their exact leading whitespace
    result = str(sanitize_email_html_content("<pre><code>    if True:\n        return 1</code></pre>"))
    assert "    if True:\n        return 1" in result

    # A run of 4 consecutive newlines inside a code block is preserved exactly (not collapsed to 3 or 2)
    result = str(sanitize_email_html_content("<pre><code>line1\n\n\n\nline2</code></pre>"))
    assert "line1\n\n\n\nline2" in result

    # A standalone <code> block (not inside <pre>) preserves indentation after a newline
    result = str(sanitize_email_html_content("<code>foo\n    bar</code>"))
    assert "foo\n    bar" in result

    # Mixed document: whitespace OUTSIDE the code block is stripped/collapsed while INSIDE it is preserved
    mixed = "<p>\n    indented paragraph</p>\n\n\n\n<pre><code>    inside:\n\n\n\n        deep</code></pre>"
    result = str(sanitize_email_html_content(mixed))
    assert "    inside:\n\n\n\n        deep" in result  # inside preserved
    assert "\n    indented paragraph" not in result  # outside leading whitespace stripped
    assert "<p>\n    " not in result  # outside indentation gone
    assert "\n\n\n" not in result.split("<pre>")[0]  # outside blank-line run collapsed

    # A <pre> wrapping a nested <code> is preserved as a whole with no corruption at the tag boundary
    result = str(sanitize_email_html_content("<pre><code>    a\n        b</code></pre>"))
    assert "<pre><code>    a\n        b</code></pre>" in result

    # A blank-line run on each side of a <pre> block still collapses outside while the block is preserved
    result = str(sanitize_email_html_content("<p>x</p>\n\n\n\n<pre><code>a\n\n\n\nb</code></pre>\n\n\n\n<p>y</p>"))
    assert "a\n\n\n\nb" in result  # inside the block: 4-newline run preserved
    assert "\n\n\n" not in result.replace("a\n\n\n\nb", "")  # outside the block: runs collapsed on both sides

    # A space right after a closing </code>/</pre> is mid-line, not a line start, so it must
    # survive the leading-whitespace strip (regression: "Use <code>foo</code> here" became "...here").
    result = str(sanitize_email_html_content("<p>Use <code>foo</code> here.</p>"))
    assert "<code>foo</code> here." in result

    # Two inline code spans on one line: the space after each must be preserved.
    result = str(sanitize_email_html_content("<p>See <code>x = 1</code> and <code>y = 2</code> now.</p>"))
    assert "<code>x = 1</code> and <code>y = 2</code> now." in result

    # Text on the same line as a closing </pre> keeps its leading space too.
    result = str(sanitize_email_html_content("<pre><code>code</code></pre> trailing text."))
    assert "</pre> trailing text." in result


def test_sanitize_email_html_content_linkifies_bare_urls():
    # Bare http/https URLs become clickable links
    result = sanitize_email_html_content("<p>See https://example.com/foo for details.</p>")
    assert '<a href="https://example.com/foo"' in result
    assert 'target="_blank"' in result
    assert 'rel="noopener noreferrer"' in result
    # Trailing punctuation is not consumed into the href
    assert ">https://example.com/foo</a>" in result
    assert " for details." in result

    # Schemeless www. URLs get an https:// prefix in href but keep the displayed text
    result = sanitize_email_html_content("<p>Visit www.example.com/path today</p>")
    assert '<a href="https://www.example.com/path"' in result
    assert ">www.example.com/path</a>" in result

    # Existing <a> tags are not re-wrapped
    result = sanitize_email_html_content('<p><a href="https://example.com">click</a></p>')
    assert result.count("<a ") == 1

    # URLs inside <code> and <pre> are left as plain text
    for tag in ("code", "pre"):
        html = f"<p>Inline: <{tag}>https://example.com/keep-as-text</{tag}></p>"
        result = sanitize_email_html_content(html)
        assert "<a " not in result
        assert "https://example.com/keep-as-text" in result

    # Multiple URLs in the same text node all linkify independently
    result = sanitize_email_html_content("<p>One https://a.example.com and two https://b.example.com end.</p>")
    assert result.count("<a ") == 2
    assert "https://a.example.com" in result
    assert "https://b.example.com" in result

    # Dangerous schemes that happen to match the regex shape are rejected by _is_safe_url
    # (sanitize strips javascript: from existing hrefs already; the linkifier must not
    # introduce them via schemeless matches either)
    result = sanitize_email_html_content("<p>javascript://evil and not a link</p>")
    # No anchor should be created for a javascript: pseudo-URL
    assert "<a " not in result


def test_sanitize_email_html_content_linkifier_rejects_userinfo_phishing():
    # `user@host` in a URL is the classic phishing primitive: the displayed
    # text begins with a trusted-looking domain but the browser navigates to
    # the host after `@`. The linkifier must NOT wrap such inputs.
    for payload in (
        "<p>Visit www.foo.com@evil.com today</p>",
        "<p>Visit https://www.foo.com@evil.com today</p>",
        "<p>Visit https://foo.com:8080@evil.com today</p>",
    ):
        result = sanitize_email_html_content(payload)
        assert "<a " not in result, f"unexpectedly linkified phishing payload: {payload!r} -> {result}"
        assert "evil.com" in result  # text is preserved, just inert


def test_sanitize_email_html_content_linkifier_rejects_non_domain_hosts():
    # Hosts whose "port" part is non-numeric (or otherwise outside the bare-
    # domain alphabet) must not be linkified. Guards against schemes like
    # `www.javascript:alert(1)` slipping through after we prepend https://,
    # which would produce a clickable but bogus href.
    result = sanitize_email_html_content("<p>www.javascript:alert(1) here</p>")
    assert "<a " not in result, f"unexpectedly linkified: {result}"


def test_linkify_bare_urls_excludes_control_characters():
    # nh3 normally strips C0 controls before _linkify_bare_urls runs, but the
    # regex itself is the last line of defense: any NUL or other control char
    # must terminate the URL so it cannot end up inside a generated href
    # (historically browsers truncate the rendered URL at NUL, letting the
    # displayed link and navigated link diverge). Call the function directly
    # so we can pass a NUL through.
    result = _linkify_bare_urls("<p>See https://foo.com\x00.evil end</p>")
    assert '<a href="https://foo.com"' in result
    assert "foo.com\x00" not in result
