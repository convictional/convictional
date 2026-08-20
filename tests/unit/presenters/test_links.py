from app.presenters.links import extract_links_from_text


def test_extract_links_from_text():
    assert extract_links_from_text("") == []
    assert extract_links_from_text("no links here") == []

    # Bare URL
    links = extract_links_from_text("Visit https://example.com today")
    assert len(links) == 1
    assert links[0].url == "https://example.com"

    # Markdown link
    links = extract_links_from_text("[Example](https://example.com)")
    assert len(links) == 1
    assert links[0].url == "https://example.com"
    assert links[0].title == "Example"

    # Image markdown is ignored
    assert extract_links_from_text("![](https://img.example.com/photo.jpg)") == []
    assert extract_links_from_text("![alt text](https://img.example.com/photo.jpg)") == []

    # Image with a real link
    links = extract_links_from_text("![](https://img.example.com/photo.jpg)\n\nhttps://example.com")
    assert len(links) == 1
    assert links[0].url == "https://example.com"

    # Bare image URLs are ignored
    assert extract_links_from_text("https://example.com/photo.jpg") == []
    assert extract_links_from_text("https://example.com/photo.png") == []
    assert extract_links_from_text("https://example.com/photo.gif") == []
    assert extract_links_from_text("https://example.com/photo.webp") == []

    # Image URLs with query strings are ignored
    assert extract_links_from_text("https://example.com/photo.jpg?w=800") == []

    # Markdown links pointing to images are ignored
    assert extract_links_from_text("[photo](https://example.com/photo.png)") == []

    # Non-image URL alongside image URL
    links = extract_links_from_text("https://example.com/photo.jpg\nhttps://example.com/article")
    assert len(links) == 1
    assert links[0].url == "https://example.com/article"

    # Trailing sentence punctuation is stripped from plain URLs (matching the
    # client-side findPreviewUrl, so the compose preview predicts the unfurl)
    links = extract_links_from_text("see https://example.com.")
    assert len(links) == 1
    assert links[0].url == "https://example.com"
    links = extract_links_from_text("see https://example.com/article, then reply")
    assert links[0].url == "https://example.com/article"
    assert extract_links_from_text("see https://example.com/photo.png.") == []

    # Balanced parens in a URL are preserved (mirror the cases in
    # tests/javascript/richText/linkPreview.test.ts so client and server agree).
    paren_url = "https://en.wikipedia.org/wiki/Scheme_(programming_language)"
    assert extract_links_from_text(paren_url)[0].url == paren_url
    # Markdown link with balanced parens in the href
    assert extract_links_from_text(f"[Scheme]({paren_url})")[0].url == paren_url
    # Legacy serialized form with backslash-escaped parens still unfurls
    escaped = "[Scheme](https://en.wikipedia.org/wiki/Scheme_\\(programming_language\\))"
    assert extract_links_from_text(escaped)[0].url == paren_url
    # A URL wrapped in prose parens drops the wrapping ")"
    assert extract_links_from_text("(https://example.com)")[0].url == "https://example.com"
    # Trailing punctuation stripped, balanced parens kept
    assert extract_links_from_text("see https://en.wikipedia.org/wiki/Foo_(bar).")[0].url == (
        "https://en.wikipedia.org/wiki/Foo_(bar)"
    )
