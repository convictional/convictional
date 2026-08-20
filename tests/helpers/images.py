import io

from PIL import Image


def png_bytes(width: int = 200, height: int = 200, mode: str = "RGB") -> bytes:
    """A throwaway in-memory PNG of the given dimensions, for upload/processing tests."""
    buffer = io.BytesIO()
    Image.new(mode, (width, height), color=(120, 200, 30)).save(buffer, format="PNG")
    return buffer.getvalue()
