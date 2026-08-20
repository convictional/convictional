import re

from bs4 import BeautifulSoup, NavigableString
from markupsafe import Markup, escape

from config import settings
from config.enums import Sharing
from lib.markdown import markdown_to_plain_text

BLOCK_TAGS = {"div", "p", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "li", "tr", "br", "hr"}


def convert_none_to_string(value):
    return value if value is not None else ""


def page_title_prefix() -> str:
    # The SPA shell stamps this into a meta tag so the client-side
    # useDocumentTitle hook can reproduce format_page_title without re-deriving
    # the environment.
    if settings.is_local:
        return f"{settings.dev_label} | "
    if not settings.is_env("production"):
        return f"[{settings.env.upper()}] "
    return ""


def format_page_title(value: str) -> str:
    return f"{page_title_prefix()}{value} - {settings.product_name}"


def format_sharing(value: Sharing):
    sharing_display = {"private": "Private", "organization": "Organization"}
    return sharing_display.get(value, value)


def pluralize(value: int, singular: str, plural: str = "") -> str:
    return singular if value == 1 else plural or make_plural(singular)


def make_plural(word: str) -> str:
    # Special cases dictionary
    irregulars = {
        "child": "children",
        "person": "people",
        "man": "men",
        "woman": "women",
        "foot": "feet",
        "tooth": "teeth",
        "goose": "geese",
        "mouse": "mice",
    }

    # Check for irregular forms first
    if word.lower() in irregulars:
        return irregulars[word.lower()]

    # Words that don't change
    if word.lower() in {"sheep", "fish", "deer", "species", "aircraft"}:
        return word

    # Common rules
    if word.endswith(("s", "sh", "ch", "x", "z")):
        return word + "es"
    elif word.endswith("y"):
        if word[-2].lower() in "aeiou":
            return word + "s"
        return word[:-1] + "ies"
    elif word.endswith(("f", "fe")):
        if word.endswith("fe"):
            return word[:-2] + "ves"
        return word[:-1] + "ves"
    elif word.endswith("o"):
        if word.lower() in {"photo", "piano", "halo"}:
            return word + "s"
        return word + "es"
    else:
        return word + "s"


def titleize(value: str) -> str:
    if not value:
        return ""

    # First convert the string to handle consecutive capitals
    modified = ""
    prev_upper = False

    for i, c in enumerate(value):
        if c.isupper():
            # Only add space if:
            # 1. Not the first character
            # 2. Previous character wasn't uppercase (start of new word)
            # 3. Next character isn't uppercase (end of acronym)
            if i > 0 and not prev_upper and (i == len(value) - 1 or not value[i + 1].isupper()):
                modified += " "
            modified += c.lower()
            prev_upper = True
        else:
            modified += c
            prev_upper = False

    # Handle underscores and multiple spaces
    words = [word for word in modified.replace("_", " ").split() if word]
    return " ".join(words).title()


def snake_case(value: str) -> str:
    result = value[0].lower()
    for char in value[1:]:
        if char.isupper():
            result += "_" + char.lower()
        elif char == " ":
            result += "_"
        else:
            result += char
    return result


def html_to_plain_text(html: str | None) -> str:
    """Convert HTML to clean plain text using BeautifulSoup"""
    if not html:
        return ""

    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")

    # Handle links by converting to "text (url)" format
    for link in soup.find_all("a", href=True):
        link_text = link.get_text()
        link_url = link["href"]
        if link_text and link_url:
            link.replace_with(f"{link_text} ({link_url})")
        elif link_text:
            link.replace_with(link_text)

    # Remove images completely
    for img in soup.find_all("img"):
        img.decompose()

    # Convert blockquotes to "> " prefixed lines before general block processing
    for bq in soup.find_all("blockquote"):
        bq_text = bq.get_text()
        quoted_lines = [f"> {line}" if line.strip() else ">" for line in bq_text.strip().split("\n")]
        bq.replace_with(NavigableString("\n" + "\n".join(quoted_lines) + "\n"))

    # Insert newlines around block-level elements so get_text() doesn't merge them
    for tag in soup.find_all(BLOCK_TAGS):
        if tag.string is None:
            # For tags with mixed content, prepend/append newlines
            tag.insert(0, NavigableString("\n"))
            tag.append(NavigableString("\n"))
        else:
            tag.string = f"\n{tag.string}\n"

    # Get plain text
    plain_text = soup.get_text()

    # Clean up whitespace
    # Replace multiple spaces with single space
    plain_text = re.sub(r" +", " ", plain_text)
    # Replace multiple newlines with at most double newlines
    plain_text = re.sub(r"\n\s*\n\s*\n+", "\n\n", plain_text)
    # Strip leading/trailing whitespace from each line
    lines = [line.strip() for line in plain_text.split("\n")]
    plain_text = "\n".join(lines)

    return plain_text.strip()


def og_description(content: str | None, max_length: int = 200) -> str:
    text = markdown_to_plain_text(content)
    if len(text) > max_length:
        return text[:max_length].rsplit(" ", 1)[0] + "..."
    return text


def linebreaksbr(text: str | None) -> Markup:
    """Convert plain text to HTML, escaping special chars and converting newlines to <br> tags."""
    if not text:
        return Markup("")
    return Markup(str(escape(text)).replace("\n", "<br>"))
