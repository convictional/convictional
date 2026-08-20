import pytest

from lib.filenames import DEFAULT_FILENAME, MAX_FILENAME_LENGTH, sanitize_filename


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("report.pdf", "report.pdf"),
        # RFC 5987-style real-world filenames with spaces/commas/parens are preserved.
        (
            "Convictional Commerce, Inc._Engagement Letter (to be signed).pdf",
            "Convictional Commerce, Inc._Engagement Letter (to be signed).pdf",
        ),
        # Path traversal: basename only survives.
        ("../../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
        ("/absolute/path/to/file.txt", "file.txt"),
        ("C:\\Users\\evil\\shell.exe", "shell.exe"),
        # Control characters and NUL are stripped.
        ("my\x00file.png", "myfile.png"),
        ("name\twith\ttabs.txt", "namewithtabs.txt"),
        ("name\r\n.png", "name.png"),
        # Double quotes would break Content-Disposition filename="...".
        ('a"b".txt', "ab.txt"),
        # Leading dots stripped so traversal sequences and dotfiles don't survive.
        ("...evil", "evil"),
        (".bashrc", "bashrc"),
        # Falls back to DEFAULT_FILENAME on empty / whitespace / pure-junk input.
        (None, DEFAULT_FILENAME),
        ("", DEFAULT_FILENAME),
        ("   ", DEFAULT_FILENAME),
        ("\x00\x01\x02", DEFAULT_FILENAME),
        ("...", DEFAULT_FILENAME),
        ("/", DEFAULT_FILENAME),
    ],
)
def test_sanitize_filename(raw: str | None, expected: str):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_truncates_preserving_extension():
    long_name = "a" * 300 + ".pdf"
    result = sanitize_filename(long_name)
    assert len(result) == MAX_FILENAME_LENGTH
    assert result.endswith(".pdf")
    assert result == "a" * (MAX_FILENAME_LENGTH - 4) + ".pdf"


def test_sanitize_filename_truncates_without_extension():
    long_name = "a" * 300
    result = sanitize_filename(long_name)
    assert result == "a" * MAX_FILENAME_LENGTH


def test_sanitize_filename_truncates_when_extension_too_long():
    # If the "extension" is longer than the budget, fall back to a plain cut.
    name = "x." + "y" * 300
    result = sanitize_filename(name)
    assert len(result) == MAX_FILENAME_LENGTH
