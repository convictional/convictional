import io

import pytest
from PIL import Image

from lib.images import ImageProcessingError, to_square_webp
from tests.helpers.images import png_bytes


def test_to_square_webp_produces_square_webp():
    output = to_square_webp(png_bytes(800, 600), size=512, quality=85)
    image = Image.open(io.BytesIO(output))
    assert image.format == "WEBP"
    assert image.size == (512, 512)


def test_to_square_webp_handles_portrait_and_landscape_with_center_crop():
    landscape = to_square_webp(png_bytes(1200, 400), size=256, quality=85)
    portrait = to_square_webp(png_bytes(400, 1200), size=256, quality=85)
    assert Image.open(io.BytesIO(landscape)).size == (256, 256)
    assert Image.open(io.BytesIO(portrait)).size == (256, 256)


def test_to_square_webp_flattens_transparency_to_white():
    rgba = Image.new("RGBA", (100, 100), color=(0, 0, 0, 0))
    buffer = io.BytesIO()
    rgba.save(buffer, format="PNG")

    output = to_square_webp(buffer.getvalue(), size=64, quality=85)
    rendered = Image.open(io.BytesIO(output)).convert("RGB")
    # A fully transparent input should land on a white background.
    assert rendered.getpixel((10, 10)) == (255, 255, 255)


def test_to_square_webp_rejects_non_image_bytes():
    with pytest.raises(ImageProcessingError):
        to_square_webp(b"not an image", size=64, quality=85)
