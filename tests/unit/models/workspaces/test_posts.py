from app.models.collaboration.workspace import LinkPreview, url_hash


def test_url_hash():
    hash1 = url_hash("https://example.com")
    hash2 = url_hash("https://example.com")
    hash3 = url_hash("https://different.com")

    assert hash1 == hash2
    assert hash1 != hash3
    assert len(hash1) == 64


def test_link_preview_domain():
    preview = LinkPreview(url="https://www.youtube.com/watch?v=abc123")
    assert preview.domain == "www.youtube.com"

    preview = LinkPreview(url="https://github.com/anthropics/claude-code")
    assert preview.domain == "github.com"

    preview = LinkPreview(url="http://example.com/path/to/page")
    assert preview.domain == "example.com"

    preview = LinkPreview(url="example.com")
    assert preview.domain == "example.com"
