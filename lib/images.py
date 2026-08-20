import io

from PIL import Image, UnidentifiedImageError


class ImageProcessingError(Exception):
    pass


def to_square_webp(data: bytes, *, size: int, quality: int) -> bytes:
    """Center-crop, resize, and re-encode an image as square WebP.

    Transparent pixels are flattened onto a white background. EXIF and other
    metadata are dropped because Pillow's `save` does not propagate them
    unless asked.
    """
    try:
        opened = Image.open(io.BytesIO(data))
        opened.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ImageProcessingError("Could not decode image") from exc

    image: Image.Image = _flatten_to_rgb(opened)
    image = _center_crop_square(image)
    image = image.resize((size, size), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=quality, method=6)
    return buffer.getvalue()


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image
    if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
        background = Image.new("RGB", image.size, (255, 255, 255))
        rgba = image.convert("RGBA")
        background.paste(rgba, mask=rgba.split()[-1])
        return background
    return image.convert("RGB")


def _center_crop_square(image: Image.Image) -> Image.Image:
    width, height = image.size
    if width == height:
        return image
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    return image.crop((left, top, left + side, top + side))
