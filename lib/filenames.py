import re
from pathlib import PurePosixPath, PureWindowsPath

DEFAULT_FILENAME = "file"
# 255 is the safe ceiling across GCS, S3, ext4, NTFS, and Content-Disposition headers.
MAX_FILENAME_LENGTH = 255

# Control characters (incl. NUL), DEL, and characters that break the
# `filename="..."` parameter of Content-Disposition or response_disposition.
_UNSAFE_CHARS = re.compile(r'[\x00-\x1f\x7f"]')


def sanitize_filename(filename: str | None) -> str:
    """Return a safe, storable filename derived from user input.

    - Drops directory components — anything before the last `/` or `\\` is discarded,
      so `../../etc/passwd` and `C:\\evil\\shell.exe` collapse to their basename.
    - Strips control chars, NUL, DEL, CR/LF, and `"` (which would break
      Content-Disposition `filename="..."`).
    - Strips leading dots so `..`, `.`, and dotfile-looking inputs don't survive.
    - Truncates to MAX_FILENAME_LENGTH, preserving a single trailing extension.
    - Falls back to DEFAULT_FILENAME if the result is empty.
    """
    if not filename:
        return DEFAULT_FILENAME

    # PureWindowsPath treats both `/` and `\` as separators, so this collapses
    # unix and windows path traversal to a basename regardless of the host OS.
    basename = PureWindowsPath(filename).name

    cleaned = _UNSAFE_CHARS.sub("", basename).strip().lstrip(".")

    if not cleaned:
        return DEFAULT_FILENAME

    if len(cleaned) <= MAX_FILENAME_LENGTH:
        return cleaned

    # Preserve a single trailing extension when truncating so MIME hints survive.
    # cleaned has no separators at this point, so PurePosixPath is a deterministic
    # way to split stem/suffix across hosts.
    path = PurePosixPath(cleaned)
    extension = path.suffix
    if not extension or len(extension) >= MAX_FILENAME_LENGTH:
        return cleaned[:MAX_FILENAME_LENGTH]
    return path.stem[: MAX_FILENAME_LENGTH - len(extension)] + extension
