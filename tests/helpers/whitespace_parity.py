from bs4 import BeautifulSoup, NavigableString, Tag
from bs4.formatter import EntitySubstitution, HTMLFormatter

# Reduces a renderer's raw HTML (in-app React or server email) to the canonical
# whitespace-tight form the cases' `target_html` is written in, so cross-surface parity can be
# asserted on meaning, not on bytes the two surfaces legitimately differ on. See
# tests/fixtures/markdown_whitespace/README.md for the contract.

# Minimal entity escaping (only & < >), U+00A0 kept raw (&nbsp;/&#160;/raw NBSP all
# converge on the U+00A0 byte — never re-encoded to &nbsp;), and void elements emitted as
# <br> with no self-closing slash (so <br> and <br/> unify).
_FORMATTER = HTMLFormatter(
    entity_substitution=EntitySubstitution.substitute_xml,
    void_element_close_prefix="",
)

# Whitespace inside these blocks is authored and significant — a space run, a soft break,
# or a cosmetic \n a regressing renderer must NOT reintroduce next to a <br> (which under
# white-space: pre-wrap would render as a visible extra blank line). It is preserved
# verbatim. Whitespace between block siblings in any other (structural) container is a
# pretty-print artifact and is dropped.
_TEXT_BEARING_TAGS = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "td", "th", "blockquote"}

# <pre>/<code> content is verbatim and exempt from every normalization rule.
_VERBATIM_TAGS = {"pre", "code"}

# Block-level tags the email renderer emits. A <div> whose non-whitespace children are
# ALL block-level is a structural wrapper (the outer document <div> or a grouping div) and
# is unwrapped; any inline element or bare text makes it a paragraph div that maps to <p>.
# An empty block <div><br></div> is a paragraph div (<br> is inline).
_BLOCK_LEVEL_TAGS = {
    "div",
    "p",
    "ul",
    "ol",
    "li",
    "table",
    "thead",
    "tbody",
    "tr",
    "td",
    "th",
    "blockquote",
    "pre",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
}

# Presentational attributes the email renderer emits (inline styles, utility classes) and
# the in-app renderer omits; stripped so both map to the bare semantic tag.
_PRESENTATIONAL_ATTRIBUTES = ("style", "class")


def normalize_whitespace_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _strip_presentational_attributes(soup)
    _canonicalize_divs(soup)
    _drop_inter_block_whitespace(soup)
    return soup.decode(formatter=_FORMATTER)


def _strip_presentational_attributes(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        for attribute in _PRESENTATIONAL_ATTRIBUTES:
            if attribute in tag.attrs:
                del tag[attribute]


def _canonicalize_divs(soup: BeautifulSoup) -> None:
    # Document order (outer before inner) so unwrapping the email renderer's outer
    # document wrapper lifts inner paragraph <div>s to where they'll be renamed.
    for div in soup.find_all("div"):
        if _has_verbatim_ancestor(div):
            continue
        if _is_paragraph_div(div):
            div.name = "p"
        else:
            # A structural grouping <div> — the outer document wrapper or a nested grouping
            # div whose non-whitespace children are ALL block-level. (An empty block
            # <div><br></div> holds an inline <br>, so it is a paragraph div and never
            # reaches here.)
            div.unwrap()


def _is_paragraph_div(div: Tag) -> bool:
    # A paragraph div holds ANY inline or bare-text content (mapped to <p>); a
    # structural div's non-whitespace children are ALL block-level (unwrapped).
    for child in div.children:
        if type(child) is NavigableString and child.strip():
            return True
        if isinstance(child, Tag) and child.name not in _BLOCK_LEVEL_TAGS:
            return True
    return False


def _drop_inter_block_whitespace(soup: BeautifulSoup) -> None:
    for text_node in list(soup.find_all(string=True)):
        if type(text_node) is not NavigableString:
            continue
        if text_node.strip():
            continue
        if _has_verbatim_ancestor(text_node):
            continue
        parent = text_node.parent
        if parent is not None and parent.name in _TEXT_BEARING_TAGS:
            continue
        text_node.extract()


def _has_verbatim_ancestor(node: Tag | NavigableString) -> bool:
    return any(parent.name in _VERBATIM_TAGS for parent in node.parents)
