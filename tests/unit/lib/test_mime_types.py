from lib.mime_types import is_browser_supported_image, is_inline_content_type


def test_is_browser_supported_image_supported_formats():
    assert is_browser_supported_image("image/jpeg") is True
    assert is_browser_supported_image("image/jpg") is True
    assert is_browser_supported_image("image/png") is True
    assert is_browser_supported_image("image/gif") is True
    assert is_browser_supported_image("image/webp") is True
    assert is_browser_supported_image("image/svg+xml") is True
    assert is_browser_supported_image("IMAGE/JPEG") is True
    assert is_browser_supported_image("Image/Png") is True


def test_is_browser_supported_image_unsupported_formats():
    assert is_browser_supported_image("image/heic") is False
    assert is_browser_supported_image("image/tiff") is False
    assert is_browser_supported_image("image/unknown") is False
    assert is_browser_supported_image("application/pdf") is False


def test_is_inline_content_type_previewable():
    assert is_inline_content_type("video/mp4") is True
    assert is_inline_content_type("image/png") is True
    assert is_inline_content_type("audio/mpeg") is True
    assert is_inline_content_type("application/pdf") is True
    # Capitalization and MIME parameters are normalized.
    assert is_inline_content_type('video/mp4; codecs="avc1.42E01E"') is True
    assert is_inline_content_type("Application/PDF") is True


def test_is_inline_content_type_non_previewable():
    assert is_inline_content_type("text/plain") is False
    assert is_inline_content_type("text/csv") is False
    assert is_inline_content_type("application/octet-stream") is False
    assert is_inline_content_type("application/json") is False
    # SVG can embed JavaScript — security exclusion despite matching image/*.
    assert is_inline_content_type("image/svg+xml") is False
    # Non-canonical PDF type is not treated as PDF.
    assert is_inline_content_type("application/x-pdf") is False
    assert is_inline_content_type(None) is False
    assert is_inline_content_type("") is False
