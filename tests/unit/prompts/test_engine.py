from app.prompts.engine import _strip_base64_images


def test_strip_base64_images():
    # Test removal of base64 images from markdown format.
    text_with_markdown_image = (
        "Here's an image: ![alt text](data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==) "
        "and some text after."
    )
    expected = "Here's an image:  and some text after."
    assert _strip_base64_images(text_with_markdown_image) == expected

    # Test removal of base64 images from HTML img tags.
    text_with_html_image = (
        'Before <img src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD" alt="test" class="image"> after'
    )
    expected = "Before  after"
    assert _strip_base64_images(text_with_html_image) == expected

    # Test removal of standalone data URI base64 images.
    text_with_data_uri = (
        "Check this out: data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7 "
        "isn't that cool?"
    )
    expected = "Check this out:  isn't that cool?"
    assert _strip_base64_images(text_with_data_uri) == expected

    # Test removal of multiple image formats in the same text.
    text_with_multiple = (
        "\n    Markdown: ![image](data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==)\n"
        '    HTML: <img src="data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD" />\n'
        "    Data URI: data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7\n    "
    )
    expected = "\n    Markdown: \n    HTML: \n    Data URI: \n    "
    assert _strip_base64_images(text_with_multiple) == expected

    # Test removal from complex HTML with multiple attributes.
    html_complex = (
        '<img class="large" src="data:image/webp;base64,'
        'UklGRnoAAABXRUJQVlA4IG4AAAAwAQCdASoBAAEAAwA0JaQAA3AA/vuUAAA=" '
        'alt="test image" style="width:100%">'
    )
    expected = ""
    assert _strip_base64_images(html_complex) == expected

    # Test removal from markdown with complex alt text.
    markdown_complex = (
        '![Complex alt text with "quotes" and symbols](data:image/svg+xml;base64,'
        "PHN2ZyB3aWR0aD0iMSIgaGVpZ2h0PSIxIiB2aWV3Qm94PSIwIDAgMSAxIiBmaWxsPSJub25lIiB4bWxucz0i"
        "aHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxIiBoZWlnaHQ9IjEiIGZpbGw9"
        "IndoaXRlIi8+PC9zdmc+)"
    )
    expected = ""
    assert _strip_base64_images(markdown_complex) == expected

    # Test that text without base64 images remains unchanged.
    text_without_images = "This is just regular text with no images."
    assert _strip_base64_images(text_without_images) == text_without_images

    # Test that text with regular images (not base64) remains unchanged.
    text_with_regular_images = "![alt](https://example.com/image.png) and <img src='/path/to/image.jpg' />"
    assert _strip_base64_images(text_with_regular_images) == text_with_regular_images

    # Test that empty string is handled correctly.
    assert _strip_base64_images("") == ""
