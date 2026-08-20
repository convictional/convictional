from app.helpers.markdown import (
    TailwindRenderer,
    content_citation_element,
    render_markdown,
)


def test_heading():
    renderer = TailwindRenderer()
    for level in range(1, 7):
        text = "Test Heading"
        result = renderer.heading(text, level)
        assert result == f"<h{level}>Test Heading</h{level}>"


def test_paragraph():
    renderer = TailwindRenderer()
    text = "Test paragraph."
    expected_html = "<p>Test paragraph.</p>"
    assert renderer.paragraph(text) == expected_html


def test_block_quote():
    renderer = TailwindRenderer()
    text = "Test block quote."
    expected_html = "<blockquote>Test block quote.</blockquote>"
    assert renderer.block_quote(text) == expected_html


def test_list():
    renderer = TailwindRenderer()
    text = "<li>Item 1</li><li>Item 2</li>"
    for ordered in (True, False):
        tag = "ol" if ordered else "ul"
        list_class = "list-decimal" if ordered else "list-disc"
        expected_html = f'<{tag} class="{list_class} pl-5">{text}</{tag}>'
        assert renderer.list(text, ordered) == expected_html


def test_list_item():
    renderer = TailwindRenderer()
    text = "List item"
    expected_html = "<li>List item</li>"
    assert renderer.list_item(text) == expected_html


def test_list_always_emits_disc_or_decimal():
    # Task items carry their own `list-none` on the <li>, so the parent <ul> can stay
    # `list-disc` regardless of children. This lets mixed lists (task + regular items)
    # render correctly: regular items keep their bullets, task items suppress only their
    # own marker via the inline class.
    renderer = TailwindRenderer()
    task_li = '<li class="!my-1 list-none relative"><input>Task</li>'

    assert renderer.list(task_li, False) == f'<ul class="list-disc pl-5">{task_li}</ul>'
    assert renderer.list("<li>Item</li>", False) == '<ul class="list-disc pl-5"><li>Item</li></ul>'
    assert renderer.list(task_li, True) == f'<ol class="list-decimal pl-5">{task_li}</ol>'
    assert renderer.list("<li>Item</li>", True) == '<ol class="list-decimal pl-5"><li>Item</li></ol>'


def test_task_list_item_unchecked():
    renderer = TailwindRenderer()
    expected_html = (
        '<li class="!my-1 list-none relative">'
        '<input class="task-checkbox absolute -left-5 top-1" type="checkbox" disabled>'
        "Buy milk</li>"
    )
    assert renderer.task_list_item("Buy milk", False) == expected_html


def test_task_list_item_checked():
    renderer = TailwindRenderer()
    expected_html = (
        '<li class="!my-1 list-none relative">'
        '<input class="task-checkbox absolute -left-5 top-1" type="checkbox" checked disabled>'
        "Done item</li>"
    )
    assert renderer.task_list_item("Done item", True) == expected_html


def test_task_list_item_paragraph_wrapped():
    text = "- [ ] First item\n\n- [x] Second item\n"
    result = render_markdown(text)
    assert 'class="!my-1 list-none relative"' in result
    assert "task-checkbox" in result


def test_table_cell_regular():
    renderer = TailwindRenderer()
    expected_html = '  <td class="border border-base-300 p-1.5">Content</td>\n'
    assert renderer.table_cell("Content", align=None, head=False) == expected_html


def test_table_cell_header():
    renderer = TailwindRenderer()
    expected_html = '  <th class="border border-base-300 p-1.5 font-semibold bg-base-200/50 text-left">Header</th>\n'
    assert renderer.table_cell("Header", align=None, head=True) == expected_html


def test_table_cell_aligned():
    renderer = TailwindRenderer()
    assert renderer.table_cell("Right", align="right", head=False) == (
        '  <td class="border border-base-300 p-1.5 text-right">Right</td>\n'
    )
    assert renderer.table_cell("Center", align="center", head=False) == (
        '  <td class="border border-base-300 p-1.5 text-center">Center</td>\n'
    )
    # Header cell with alignment: per-cell alignment replaces the default text-left.
    assert renderer.table_cell("Right", align="right", head=True) == (
        '  <th class="border border-base-300 p-1.5 font-semibold bg-base-200/50 text-right">Right</th>\n'
    )


def test_table_cell_empty():
    renderer = TailwindRenderer()
    expected_html = '  <td class="border border-base-300 p-1.5"></td>\n'
    assert renderer.table_cell("", align=None, head=False) == expected_html


def test_table():
    renderer = TailwindRenderer()
    expected_html = '<table class="w-full border-collapse table-fixed">\n<thead><tr><th>A</th></tr></thead></table>\n'
    assert renderer.table("<thead><tr><th>A</th></tr></thead>") == expected_html


def test_render_markdown_task_list():
    text = "- [ ] Unchecked item\n- [x] Checked item\n"
    result = render_markdown(text)
    # Parent <ul> always uses list-disc; per-item list-none on each task <li> suppresses bullets.
    assert '<ul class="list-disc pl-5">' in result
    assert 'class="!my-1 list-none relative"' in result
    assert '<input class="task-checkbox absolute -left-5 top-1" type="checkbox" disabled>' in result
    assert '<input class="task-checkbox absolute -left-5 top-1" type="checkbox" checked disabled>' in result


def test_render_markdown_table():
    text = "| Header 1 | Header 2 |\n| -------- | -------- |\n| Cell 1   | Cell 2   |\n"
    result = render_markdown(text)
    assert '<table class="w-full border-collapse table-fixed">' in result
    assert 'class="border border-base-300 p-1.5 font-semibold bg-base-200/50 text-left"' in result
    assert 'class="border border-base-300 p-1.5"' in result
    assert "table-zebra" not in result


def test_render_markdown_regular_list_unaffected():
    text = "- Item one\n- Item two\n"
    result = render_markdown(text)
    assert '<ul class="list-disc pl-5">' in result


def test_render_markdown_nested_task_in_regular_list():
    text = "- Regular item\n  - [ ] Nested task\n"
    result = render_markdown(text)
    # Outer regular list has list-disc; inner task items have per-li list-none.
    assert '<ul class="list-disc pl-5">' in result
    assert 'class="!my-1 list-none relative"' in result


def test_render_markdown_mixed_list_renders_both_markers():
    # Mixed lists (task item first, then a regular item, or vice versa) now render
    # correctly: the parent <ul> stays list-disc and each task <li> suppresses only its
    # own marker via list-none. Regular siblings keep their bullets.
    text = "- [ ] Task first\n- Regular second\n"
    result = render_markdown(text)
    assert '<ul class="list-disc pl-5">' in result
    assert 'class="!my-1 list-none relative"' in result  # task item suppresses its marker
    assert "Regular second" in result


def test_link():
    renderer = TailwindRenderer()
    text = "Example"
    url = "https://example.com"
    title = "Example Homepage"
    expected_html = (
        '<a href="https://example.com" class="link" title="Example Homepage" '
        'target="_blank" rel="noopener noreferrer">Example</a>'
    )
    assert renderer.link(text, url, title) == expected_html

    # Without title, no title attribute should appear
    assert "title=" not in renderer.link("Example", "https://example.com")


def test_link_blocks_dangerous_protocols():
    renderer = TailwindRenderer()
    assert renderer.link("click", "javascript:alert(1)") == (
        '<a href="#harmful-link" class="link" target="_blank" rel="noopener noreferrer">click</a>'
    )
    assert renderer.link("click", "data:text/html,<script>alert(1)</script>") == (
        '<a href="#harmful-link" class="link" target="_blank" rel="noopener noreferrer">click</a>'
    )
    assert renderer.link("click", "vbscript:MsgBox") == (
        '<a href="#harmful-link" class="link" target="_blank" rel="noopener noreferrer">click</a>'
    )


def test_link_blocks_dangerous_protocols_in_markdown():
    result = render_markdown("[click](javascript:alert(1))")
    assert "javascript:" not in result
    assert "#harmful-link" in result


def test_render_markdown():
    text = "# Heading\n\nThis is a paragraph."
    result = render_markdown(text).strip()
    assert result.startswith("<h1>")
    assert "Heading</h1>" in result
    assert "<p>This is a paragraph.</p>" in result


def test_rendering_mentions():
    text = "Hello @[Alice Clams], @[Bob Clams]"
    expected_html = (
        '<p>Hello <span class="text-info-content">@Alice Clams</span>, '
        '<span class="text-info-content">@Bob Clams</span></p>'
    )
    assert render_markdown(text).strip() == expected_html.strip()


def test_rendering_break():
    text = """Howdy

<br />

Neighborino"""

    expected_html = "<p>Howdy</p><p><br /></p><p>Neighborino</p>"
    assert render_markdown(text).strip() == expected_html.strip()


def test_rendering_html():
    text = """I am talking about a <li>"""
    expected_html = "<p>I am talking about a &lt;li&gt;</p>"
    assert render_markdown(text).strip() == expected_html.strip()


def test_rendering_escape_codes():
    text = """Sometimes things get a little weird, like this:&#x20;&#x20;
"""
    expected_html = "<p>Sometimes things get a little weird, like this:&#x20;&#x20;</p>"
    assert render_markdown(text).strip() == expected_html.strip()


def test_rendering_with_citations():
    test = """**This is content with inline citations**[^content:6d627c61-a1bb-46df-bb5e-c16679f6f623]"""
    expected_html = (
        "<p><strong>This is content with inline citations</strong>"
        f"{content_citation_element('6d627c61-a1bb-46df-bb5e-c16679f6f623')}</p>"
    )
    assert render_markdown(test).strip() == expected_html.strip()


def test_hardbreak():
    test = """Line one.  \nLine two."""

    expected_html = "<p>Line one.<br />\nLine two.</p>"
    assert render_markdown(test).strip() == expected_html.strip()
