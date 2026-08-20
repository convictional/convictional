import re
import unicodedata

JINJA_PATTERN = re.compile(r"\{\{.*?\}\}|\{%.*?%\}")

NAME_MAX_LENGTH = 50
# Spaces and the punctuation that appears in real names (hyphenated names,
# O'Brien, initials); everything else must be a Latin-script letter.
NAME_ALLOWED_PUNCTUATION = frozenset(" -.'’")


def normalize_name(raw: str) -> str:
    """Strip and validate a human display name, returning the normalized form.

    Allows Latin-script letters, spaces, and common name punctuation only, so
    non-Latin scripts, emoji, symbols, and decorative characters are rejected.
    Raises ValueError (surfaced as a 422 by the Pydantic field validator) when
    the name is blank, exceeds NAME_MAX_LENGTH, has no letters, or contains a
    disallowed character. Rejecting control characters also blocks CR/LF being
    smuggled into an email From header via a display name.
    """
    # NFC composes accents into single Latin code points (José as one "é", not
    # "e" + combining accent) so it validates as a letter, while stray combining
    # marks (Zalgo text) stay uncomposed and are rejected below.
    normalized = unicodedata.normalize("NFC", raw).strip()

    if not normalized:
        raise ValueError("Name cannot be blank")
    if len(normalized) > NAME_MAX_LENGTH:
        raise ValueError(f"Name must be {NAME_MAX_LENGTH} characters or fewer")

    has_letter = False
    for char in normalized:
        if char in NAME_ALLOWED_PUNCTUATION:
            continue
        if unicodedata.category(char).startswith("L") and unicodedata.name(char, "").startswith("LATIN"):
            has_letter = True
            continue
        raise ValueError("Name contains invalid characters")

    if not has_letter:
        raise ValueError("Name must contain a letter")

    return normalized


def canonicalize_email(email: str) -> str:
    """Canonicalize an email so aliases of the same mailbox compare equal.

    Lowercases and strips a +tag from the local part; for Gmail addresses also removes
    dots and canonicalizes the domain to gmail.com, since Gmail treats `k.r.is+x@gmail.com`
    and `kris@gmail.com` as the same mailbox. Returns the input lowercased/stripped when it
    isn't a parseable address. Intended for equality/matching (e.g. blocklists), not for
    storage or display.
    """
    email = email.strip().lower()
    if "@" not in email:
        return email
    local, _, domain = email.rpartition("@")
    local = local.split("+", 1)[0]
    if domain in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def escape_jinja(text: str) -> str:
    """
    Escapes Jinja template syntax to prevent downstream template injection.

    Libraries like instructor process prompts through Jinja templating,
    so user input containing {{ }} or {% %} can cause errors.

    Wraps the entire text in {% raw %}...{% endraw %} if any Jinja syntax is detected.
    """
    if JINJA_PATTERN.search(text):
        return f"{{% raw %}}{text}{{% endraw %}}"
    return text


def truncate(text: str, limit: int) -> str:
    """Cap a string at `limit` characters, replacing the last with "…" if it overflows."""
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def excerpt_around(text: str, marker: str, length: int) -> str:
    """Return a ~`length`-char window of `text` centered on the first `marker`.

    Unlike `truncate`, which keeps the head of the string, this keeps the region
    around `marker` — the caller anchors on something deep in a long body (e.g. an
    @mention marker) and wants the surrounding context, not the opening. The full
    marker is always included; when the window is trimmed at an end it gets a "…",
    and both ends prefer to cut on whitespace so words aren't split. Returns `text`
    unchanged when it already fits or the marker isn't found.
    """
    if len(text) <= length:
        return text

    marker_start = text.find(marker)
    if marker_start == -1:
        return truncate(text, length)

    marker_end = marker_start + len(marker)
    # Split the leftover budget around the marker, spilling whatever an edge can't
    # use to the other side so a marker near the start or end still fills the window.
    budget = max(length - len(marker), 0)
    left = min(marker_start, budget // 2)
    right = min(len(text) - marker_end, budget - left)
    left = min(marker_start, budget - right)
    start = marker_start - left
    end = marker_end + right

    # Nudge each cut to the nearest whitespace inside the window so we don't split
    # a word; skip when that would eat into the marker itself.
    if start > 0:
        space = text.find(" ", start, marker_start)
        if space != -1:
            start = space + 1
    if end < len(text):
        space = text.rfind(" ", marker_end, end)
        if space != -1:
            end = space

    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def normalize_text(text: str | None) -> str | None:
    """
    Normalizes text for search by:
    - Converting to lowercase
    - Removing diacritical marks (é -> e, ñ -> n)
    - Collapsing whitespace

    Args:
        text: The text to normalize

    Returns:
        Normalized text, or None if input is None
    """
    if text is None:
        return None

    # Lowercase for case-insensitive search
    text = text.lower()

    # Decompose unicode characters and remove diacritical marks
    # NFD decomposes characters like é into e + combining accent
    normalized = unicodedata.normalize("NFD", text)
    # Filter out combining characters (category 'Mn' = nonspacing marks)
    without_accents = "".join(char for char in normalized if unicodedata.category(char) != "Mn")

    # Normalize whitespace: strip leading/trailing and collapse multiple spaces
    return " ".join(without_accents.split())
