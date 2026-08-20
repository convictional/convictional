from tests.helpers.whitespace_parity import normalize_whitespace_html

# Directly exercises normalize_whitespace_html with adversarial inputs. The parity gate
# (test_whitespace_parity.py) only ever feeds it already-canonical inputs, so the
# normalizer's core properties — which <div>s become <p> vs. get unwrapped, what
# whitespace survives, entity/<br> unification — go unpinned there. These tests pin them.


def test_inline_only_paragraph_div_maps_to_p():
    # An email paragraph whose only child is a single inline element (no bare text node)
    # must map to <p>, not be unwrapped (which would drop the paragraph boundary and
    # diverge from react-markdown's <p>-wrapped output).
    assert normalize_whitespace_html("<div><div><strong>bold</strong></div></div>") == "<p><strong>bold</strong></p>"
    assert normalize_whitespace_html('<div><div><a href="/x">a</a></div></div>') == '<p><a href="/x">a</a></p>'
    assert normalize_whitespace_html("<div><div><code>x</code></div></div>") == "<p><code>x</code></p>"


def test_cosmetic_newline_next_to_br_is_preserved_and_discriminated():
    # A stray \n adjacent to a <br> inside a text-bearing block is significant: pre-wrap
    # would render it as a visible extra break. It must survive normalization so the parity
    # gate catches a renderer that reintroduces it — i.e. it must NOT normalize to the same
    # form as the tight <br>.
    assert normalize_whitespace_html("<div><div>a<br>\nb</div></div>") == "<p>a<br>\nb</p>"
    assert normalize_whitespace_html("<div><div>a<br>\nb</div></div>") != "<p>a<br>b</p>"


def test_soft_break_between_inline_siblings_is_not_welded():
    # A standalone soft-break newline between two inline siblings is authored content; the
    # normalizer must keep it verbatim rather than weld the spans into <em>foo</em><em>bar</em>.
    assert (
        normalize_whitespace_html("<div><div><em>foo</em>\n<em>bar</em></div></div>")
        == "<p><em>foo</em>\n<em>bar</em></p>"
    )


def test_structural_wrapper_of_block_children_is_unwrapped():
    # A <div> whose non-whitespace children are all block-level is a structural wrapper and
    # is unwrapped; the inner paragraph <div>s each map to <p>.
    assert normalize_whitespace_html("<div><div>A</div><div>B</div></div>") == "<p>A</p><p>B</p>"


def test_empty_block_is_preserved_as_wrapped_paragraph():
    # An empty block <div><br></div> holds an inline <br>, so it is a paragraph div (never
    # unwrapped) and maps to the canonical wrapped empty block <p><br></p>.
    assert normalize_whitespace_html("<div><div><br></div></div>") == "<p><br></p>"


def test_pre_code_content_is_verbatim_exempt():
    # <pre>/<code> content is exempt from all rules: presentational attributes are stripped,
    # but every interior space run and newline is preserved exactly.
    source = '<div><pre style="x"><code>a   b\n\n\n    indent\n</code></pre></div>'
    assert normalize_whitespace_html(source) == "<pre><code>a   b\n\n\n    indent\n</code></pre>"


def test_entity_nbsp_and_br_unification():
    # &nbsp; decodes to raw U+00A0 (never re-encoded), and <br/> unifies to <br>.
    assert normalize_whitespace_html("<div><div>a&nbsp;&nbsp;b</div></div>") == "<p>a  b</p>"
    assert normalize_whitespace_html("<p>a<br/>b</p>") == "<p>a<br>b</p>"


def test_inter_block_whitespace_is_dropped():
    # Whitespace-only text nodes directly between block siblings are pretty-print artifacts
    # and are removed.
    assert normalize_whitespace_html("<p>A</p>\n<p>B</p>") == "<p>A</p><p>B</p>"
