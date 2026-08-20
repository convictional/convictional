import pytest

from lib.email_reply_parser import strip_email_reply_quotes
from lib.strings import (
    NAME_MAX_LENGTH,
    canonicalize_email,
    escape_jinja,
    excerpt_around,
    normalize_name,
    normalize_text,
    truncate,
)


def test_canonicalize_email():
    # Lowercased and +tag stripped for any domain.
    assert canonicalize_email("User+Tag@Example.com") == "user@example.com"

    # Gmail aliases collapse: dots and +tags are ignored, googlemail == gmail.
    assert canonicalize_email("k.r.i.s.braun@gmail.com") == "krisbraun@gmail.com"
    assert canonicalize_email("krisbraun+anything@gmail.com") == "krisbraun@gmail.com"
    assert canonicalize_email("KrisBraun@googlemail.com") == "krisbraun@gmail.com"

    # Non-Gmail domains keep their dots (only +tag and case are normalized).
    assert canonicalize_email("first.last@company.com") == "first.last@company.com"

    # A non-address input is returned lowercased/stripped rather than raising.
    assert canonicalize_email("  NotAnEmail  ") == "notanemail"


def test_normalize_name():
    # Trims surrounding whitespace.
    assert normalize_name("  Alex Doe  ") == "Alex Doe"
    assert normalize_name("Alex") == "Alex"

    # Latin letters with accents and common name punctuation are allowed.
    assert normalize_name("José García") == "José García"
    assert normalize_name("Anne-Marie O'Brien") == "Anne-Marie O'Brien"

    # Blank (or whitespace/zero-width-only) is rejected.
    for blank in ["", "   ", "​‌"]:
        with pytest.raises(ValueError):
            normalize_name(blank)

    # Control characters (e.g. CR/LF header-injection attempts) are rejected.
    with pytest.raises(ValueError):
        normalize_name("Alex\r\nBcc: evil@example.com")

    # Emoji, non-Latin scripts, decorative unicode, and standalone combining
    # marks (Zalgo) are rejected.
    for invalid in ["🎉 Party", "名前 太郎", "Владимир", "𝓯𝓪𝓷𝓬𝔂", "a̶̴̵bc"]:
        with pytest.raises(ValueError):
            normalize_name(invalid)

    # A name with no letters at all is rejected.
    with pytest.raises(ValueError):
        normalize_name("- . '")

    # Over the length cap is rejected; exactly at the cap is allowed.
    with pytest.raises(ValueError):
        normalize_name("x" * (NAME_MAX_LENGTH + 1))
    assert normalize_name("x" * NAME_MAX_LENGTH) == "x" * NAME_MAX_LENGTH


def test_truncate():
    # Pass-through when within the limit.
    assert truncate("", 10) == ""
    assert truncate("short", 10) == "short"
    assert truncate("exact", 5) == "exact"

    # Overflow: result is exactly `limit` chars, ending with the ellipsis.
    assert truncate("abcdefghij", 5) == "abcd…"
    assert len(truncate("abcdefghij", 5)) == 5

    # Trailing whitespace before the ellipsis is stripped so the card doesn't render " …".
    assert truncate("abcd efghij", 6) == "abcd…"

    # Limit of 1 collapses to just the ellipsis.
    assert truncate("anything", 1) == "…"


def test_excerpt_around():
    marker = "@[Bob Clams]"

    # Pass-through when the whole text already fits within the window.
    short = f"Hey {marker}, take a look."
    assert excerpt_around(short, marker, 500) == short

    # Marker buried deep in a long body: the window keeps the mention's nearby
    # context and drops far-away text at both ends, marked with ellipses.
    body = "ZZSTART " + ("filler " * 60) + f"please {marker} review " + ("filler " * 60) + "ZZEND"
    result = excerpt_around(body, marker, 60)
    assert marker in result
    assert result.startswith("…")
    assert result.endswith("…")
    assert "please" in result and "review" in result
    assert "ZZSTART" not in result and "ZZEND" not in result
    # Bounded to roughly the window (plus ellipses / whitespace-cut slack).
    assert len(result) <= 60 + 2

    # Marker at the very start: no leading ellipsis, trailing one when trimmed.
    # The unused left-side budget spills right, so the window still fills ~length
    # rather than stopping at half.
    at_start = f"{marker} " + ("tail " * 100)
    result = excerpt_around(at_start, marker, 60)
    assert result.startswith(marker)
    assert not result.startswith("…")
    assert result.endswith("…")
    assert len(result) >= 50  # would be ~36 without redistributing the left budget

    # Marker at the very end: leading ellipsis, no trailing one.
    at_end = ("head " * 100) + f" {marker}"
    result = excerpt_around(at_end, marker, 60)
    assert result.startswith("…")
    assert result.endswith(marker)

    # No marker present falls back to a head truncation rather than raising.
    assert excerpt_around("x" * 100, marker, 10) == "x" * 9 + "…"


def test_escape_jinja():
    assert escape_jinja("Hello world") == "Hello world"
    assert escape_jinja("{{ variable }}") == "{% raw %}{{ variable }}{% endraw %}"
    assert escape_jinja("{{ this.name }}") == "{% raw %}{{ this.name }}{% endraw %}"
    assert escape_jinja("Multiple {{ one }} and {{ two }}") == "{% raw %}Multiple {{ one }} and {{ two }}{% endraw %}"
    assert escape_jinja("{% if true %}yes{% endif %}") == "{% raw %}{% if true %}yes{% endif %}{% endraw %}"
    assert escape_jinja("Normal {braces}") == "Normal {braces}"
    assert escape_jinja("") == ""


def test_normalize_text():
    # Test lowercase normalization
    assert normalize_text("Python") == "python"
    assert normalize_text("PYTHON") == "python"
    assert normalize_text("PyThOn") == "python"

    # Test accent removal
    assert normalize_text("résumé") == "resume"
    assert normalize_text("café") == "cafe"
    assert normalize_text("naïve") == "naive"
    assert normalize_text("Müller") == "muller"
    assert normalize_text("Señor") == "senor"

    # Test combined lowercase and accent removal
    assert normalize_text("Résumé") == "resume"
    assert normalize_text("CAFÉ") == "cafe"
    assert normalize_text("Naïve") == "naive"

    # Test various unicode characters with decomposable accents
    assert normalize_text("François") == "francois"
    assert normalize_text("São Paulo") == "sao paulo"
    assert normalize_text("Zürich") == "zurich"
    assert normalize_text("Øresund") == "øresund"  # Ø doesn't decompose, but ó does

    # Test null handling
    assert normalize_text(None) is None

    # Test empty string
    assert normalize_text("") == ""

    # Test whitespace normalization
    assert normalize_text("Hello World") == "hello world"
    assert normalize_text("  spaces  ") == "spaces"
    assert normalize_text("multiple    spaces") == "multiple spaces"
    assert normalize_text("  leading and trailing  ") == "leading and trailing"
    assert normalize_text("tabs\t\there") == "tabs here"
    assert normalize_text("newlines\n\nhere") == "newlines here"
    assert normalize_text("mixed \t\n whitespace") == "mixed whitespace"

    # Test special characters preservation
    assert normalize_text("test-case_123") == "test-case_123"
    assert normalize_text("email@example.com") == "email@example.com"

    # Test complex real-world examples with accents and whitespace
    assert normalize_text("Développement") == "developpement"
    assert normalize_text("Björk Guðmundsdóttir") == "bjork guðmundsdottir"  # ð is a separate letter
    assert normalize_text("Tōkyō, Japan") == "tokyo, japan"
    assert normalize_text("  Résumé Builder  ") == "resume builder"
    assert normalize_text("CAFÉ\n\tPARIS") == "cafe paris"

    # Test that non-decomposable characters remain (these are separate letters, not accented variants)
    assert normalize_text("Łódź") == "łodz"  # Ł stays, ó decomposes
    assert normalize_text("Øresund") == "øresund"  # Ø is a separate letter in Danish/Norwegian


def test_strip_email_reply_quotes():
    # Strips quoted reply content (real Gmail reply format from email seeds)
    text = (
        "And this is the reply inside Gmail.\r\n\r\n"
        "On Wed, Dec 10, 2025 at 7:42\u202fAM Marcus Larkin <marcus@example.com> wrote:\r\n\r\n"
        "> This is the initial email content.\r\n>\r\n"
    )
    result = strip_email_reply_quotes(text)
    assert "And this is the reply inside Gmail." in result
    assert "This is the initial email content." not in result

    # Preserves plain message without quotes
    assert strip_email_reply_quotes("Just a simple message with no quotes.") == "Just a simple message with no quotes."

    # Preserves intentional blockquotes (no reply header)
    blockquote_text = (
        "Here is what the contract says:\n\n"
        "> All parties must agree\n"
        "> to the terms within 30 days\n\n"
        "Let me know your thoughts."
    )
    result = strip_email_reply_quotes(blockquote_text)
    assert "All parties must agree" in result
    assert "Let me know your thoughts." in result

    # Strips Convictional reply where attribution is on its own line
    convictional_text = (
        "This is the reply inside Convictional.\n\n"
        "On December 10, 2025 at 07:42 AM, Marcus Larkin wrote:\n"
        "...\n"
        "And this is the reply inside Gmail.\n\n"
        "On Wed, Dec 10, 2025 at 7:42\u202fAM Marcus Larkin "
        "<marcus@example.com (mailto:marcus@example.com)> wrote:\n"
        "This is the initial email content."
    )
    result = strip_email_reply_quotes(convictional_text)
    assert "This is the reply inside Convictional." in result
    assert "This is the initial email content." not in result

    # Handles empty string
    assert strip_email_reply_quotes("") == ""


def test_strip_email_reply_quotes_with_backslash_in_quote_header():
    """Regression: literal backslash sequences in quote headers must not crash re.sub()."""
    text = (
        "Thanks for the update.\n\n"
        "On Sat, Nov 29, 2025 at 10:45\\u202fAM Someone\n"
        "<someone@example.com> wrote:\n\n"
        "> Original message content.\n"
    )
    result = strip_email_reply_quotes(text)
    assert "Thanks for the update." in result
    assert "Original message content." not in result
