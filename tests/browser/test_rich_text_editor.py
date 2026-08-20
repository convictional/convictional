import re

import pytest
from playwright.async_api import Locator

from config.enums import Integration
from tests.helpers.assertions import assert_live_markdown_contains
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_document, create_post, create_user

# 1x1 transparent PNG, used to exercise the attachment upload pipeline.
ONE_PX_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


async def open_document_editor(browser_client: BrowserClient, email: str = "alice@example.com") -> Locator:
    user = await create_user(email=email, integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    document = await create_document(creator_id=user.id, organization_id=user.organization_id)
    await browser_client.login(email)
    await browser_client.page.goto(f"{browser_client.base_url}/documents/{document.id}/edit")
    editor = browser_client.page.locator('.ProseMirror[contenteditable="true"]').first
    await browser_client.expect(editor).to_be_visible()
    await editor.click()
    return editor


async def open_editor_with_mention_roster(browser_client: BrowserClient, url: str) -> Locator:
    # Mention candidates come from /api/organization/members. useSuggester snapshots the
    # roster when the `@` match fires and only re-searches on the next suggest change
    # event, so a `@name` typed before that response lands leaves the dropdown empty for
    # good. Tests that reach for the suggester must let the roster arrive first. Arm the
    # wait before navigating: by the time the editor is clicked the response may already
    # have been received, and wait_for_response would then wait for a second one forever.
    page = browser_client.page
    async with page.expect_response("**/api/organization/members"):
        await page.goto(url)
        editor = page.locator('.ProseMirror[contenteditable="true"]').first
        await browser_client.expect(editor).to_be_visible()
        await editor.click()
    return editor


async def paste_text(editor: Locator, text: str):
    # Dispatching a synthetic paste event with only text/plain routes through the
    # clipboard plugin's clipboardTextParser (the markdown re-parse path).
    await editor.click()
    await editor.evaluate(
        """(el, text) => {
            const dt = new DataTransfer()
            dt.setData("text/plain", text)
            el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }))
        }""",
        text,
    )


async def paste_html(editor: Locator, html: str, text: str = ""):
    # Pasting text/html routes through the clipboard plugin's transformPastedHTML
    # (DOM cleanups + the VS Code markdown-in-HTML re-parse path).
    await editor.click()
    await editor.evaluate(
        """(el, { html, text }) => {
            const dt = new DataTransfer()
            dt.setData("text/html", html)
            if (text) dt.setData("text/plain", text)
            el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }))
        }""",
        {"html": html, "text": text},
    )


async def paste_image(editor: Locator):
    # A pasted file item routes through the attachments plugin's handlePaste and
    # the real upload endpoint, then is replaced with an image node.
    await editor.click()
    await editor.evaluate(
        """(el, b64) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0))
            const file = new File([bytes], "pixel.png", { type: "image/png" })
            const dt = new DataTransfer()
            dt.items.add(file)
            el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }))
        }""",
        ONE_PX_PNG_B64,
    )


@pytest.mark.asyncio
async def test_document_text_formatting(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)
    page = browser_client.page

    # Markdown input rules for inline marks (trailing space triggers the rule)
    await editor.type("**bold** ")
    await browser_client.expect(editor.locator("strong")).to_contain_text("bold")

    await editor.type("*italic* ")
    await browser_client.expect(editor.locator("em")).to_contain_text("italic")

    await editor.type("~~strike~~ ")
    await browser_client.expect(editor.locator("del, s")).to_contain_text("strike")

    await editor.type("`mono` ")
    await browser_client.expect(editor.locator("code")).to_contain_text("mono")

    # Link input rule triggers on the closing paren
    await editor.type("[site](https://example.com)")
    link = editor.locator('a[href*="example.com"]')
    await browser_client.expect(link).to_contain_text("site")

    # Emoji shortcode input rule triggers on the closing colon
    await editor.type(" :thumbsup:")
    await browser_client.expect(editor).to_contain_text("👍")

    # Keyboard shortcut marks
    await editor.press("ControlOrMeta+b")
    await editor.type("kbd-bold")
    await editor.press("ControlOrMeta+b")
    await browser_client.expect(editor.locator("strong", has_text="kbd-bold")).to_be_visible()

    # Toolbar button marks (buttons act on mousedown and keep editor focus)
    await page.get_by_role("button", name="Italic", exact=True).click()
    await editor.type("toolbar-italic")
    await page.get_by_role("button", name="Italic", exact=True).click()
    await browser_client.expect(editor.locator("em", has_text="toolbar-italic")).to_be_visible()

    # Undo removes the last input. Redo is asserted on the post composer instead:
    # here the Yjs undo manager races with the collaboration sync echo, which can
    # clear the redo stack and make the assertion flaky.
    await editor.press("ControlOrMeta+z")
    await browser_client.expect(editor.locator("em", has_text="toolbar-italic")).not_to_be_visible()


@pytest.mark.asyncio
async def test_document_block_formatting(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    await editor.type("# Heading one")
    await browser_client.expect(editor.locator("h1")).to_contain_text("Heading one")
    await editor.press("Enter")

    await editor.type("## Heading two")
    await browser_client.expect(editor.locator("h2")).to_contain_text("Heading two")
    await editor.press("Enter")

    await editor.type("- bullet item")
    await browser_client.expect(editor.locator("ul li")).to_contain_text("bullet item")
    # Empty list item + Enter exits the list
    await editor.press("Enter")
    await editor.press("Enter")

    await editor.type("1. numbered item")
    await browser_client.expect(editor.locator("ol li")).to_contain_text("numbered item")
    await editor.press("Enter")
    await editor.press("Enter")

    # Task list: [ ] inside a regular list item converts it to a task item
    await editor.type("- ")
    await editor.type("[ ] todo item")
    await browser_client.expect(editor.locator('li input[type="checkbox"]')).to_be_visible()
    await browser_client.expect(editor.locator('li:has(input[type="checkbox"])')).to_contain_text("todo item")
    await editor.press("Enter")
    await editor.press("Enter")

    await editor.type("> quoted text")
    await browser_client.expect(editor.locator("blockquote")).to_contain_text("quoted text")
    # Tab inside a blockquote inserts a literal tab instead of moving focus (#7939)
    await editor.press("Tab")
    await editor.type("tabbed")
    quote_text = await editor.locator("blockquote").text_content()
    assert quote_text is not None and "quoted text\ttabbed" in quote_text
    # ArrowDown at the end of a trailing blockquote exits it (keymap.ts)
    await editor.press("ArrowDown")

    await editor.type("```")
    await editor.type("const x = 1")
    await browser_client.expect(editor.locator("pre")).to_contain_text("const x = 1")
    # Tab inside a code block also inserts a literal tab (#7939)
    await editor.press("Tab")
    await editor.type("indented")
    pre_text = await editor.locator("pre").text_content()
    assert pre_text is not None and "const x = 1\tindented" in pre_text
    await editor.press("ArrowDown")

    await editor.type("after blocks")
    await browser_client.expect(editor.locator("p", has_text="after blocks")).to_be_visible()


@pytest.mark.asyncio
async def test_document_table(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)
    page = browser_client.page

    # The table button lives inside the grouped toolbar's "Insert" dropdown
    await page.get_by_role("button", name="Insert", exact=True).click()
    await page.get_by_role("button", name="Insert table", exact=True).click()
    await page.get_by_role("button", name="Insert 3×3 table").click()
    await browser_client.expect(editor.locator("table")).to_be_visible()

    # Type in the first cell, Tab to the next, type again
    first_cell = editor.locator("th").first
    await first_cell.click()
    await editor.type("Alpha")
    await editor.press("Tab")
    await editor.type("Beta")

    await browser_client.expect(editor.locator("th").nth(0)).to_contain_text("Alpha")
    await browser_client.expect(editor.locator("th").nth(1)).to_contain_text("Beta")

    # Shift+Tab navigates back to the previous cell, selecting its content,
    # so typing replaces "Alpha"
    await editor.press("Shift+Tab")
    await editor.type("Gamma")
    await browser_client.expect(editor.locator("th").nth(0)).to_contain_text("Gamma")
    await browser_client.expect(editor.locator("th").nth(0)).not_to_contain_text("Alpha")

    # Typing after exiting the table lands in a paragraph, not a cell
    last_cell = editor.locator("td").last
    await last_cell.click()
    await editor.press("ArrowDown")
    await editor.type("below the table")
    await browser_client.expect(editor.locator("p", has_text="below the table")).to_be_visible()


@pytest.mark.asyncio
async def test_document_link_dialog_stays_open_on_input_click(browser_client: BrowserClient):
    # Regression: the Link button lives inside the grouped "Insert" dropdown, but
    # LinkDialog renders in a FloatingPortal at the document root — outside the
    # ToolbarGroup's wrapper ref. Clicking inside the URL input fires the group's
    # click-outside handler, which closes the group and unmounts the dialog, so
    # the user can never focus/type a URL.
    editor = await open_document_editor(browser_client)
    page = browser_client.page

    # Type text and select it. The Insert→Link button's `disabled` prop reads
    # actions.lastSelectionRef, populated by an effect that lags one render behind
    # the selection change, so it takes ≥2 selection transactions in ≥2 SEPARATE
    # React commits before the ref is populated in time. We settle between presses
    # (extra press to tolerate a dropped keypress) because react-prosemirror
    # coalesces rapid selection transactions into one render, leaving the ref stale
    # with no catch-up render. We settle on the render lifecycle rather than a
    # guessed ms delay: two animation frames span a full commit → paint →
    # passive-effect cycle and scale with machine load. The
    # expect(Link).to_be_enabled() gate below (which auto-waits) remains the real
    # correctness check.
    await editor.type("linkme")

    async def settle_render() -> None:
        await page.evaluate(
            "() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))"
        )

    for key in ("Shift+Home", "Shift+End", "Shift+Home"):
        await editor.press(key)
        await settle_render()

    # Open the Insert group, then confirm the Link button is enabled before click.
    await browser_client.expect(page.get_by_role("button", name="Insert", exact=True)).to_be_visible()
    await page.get_by_role("button", name="Insert", exact=True).click()
    await browser_client.expect(page.get_by_role("button", name="Link", exact=True)).to_be_enabled()
    await page.get_by_role("button", name="Link", exact=True).click()

    # The URL input appears in the floating dialog.
    url_input = page.get_by_placeholder("URL")
    await browser_client.expect(url_input).to_be_visible()

    # REGRESSION ASSERTION: clicking inside the input must NOT dismiss the dialog.
    await url_input.click()
    await browser_client.expect(url_input).to_be_visible()

    # The input remains usable: fill it and apply the link.
    await url_input.fill("https://example.com/foo")
    await browser_client.expect(url_input).to_have_value("https://example.com/foo")
    await page.get_by_role("button", name="Apply").click()

    # The selected text is now a link with the entered href.
    await browser_client.expect(editor.locator("a", has_text="linkme")).to_have_attribute(
        "href", "https://example.com/foo"
    )


@pytest.mark.asyncio
async def test_document_markdown_paste(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    # Bare URLs in pasted text get linkified (pasted first, into a plain paragraph)
    await paste_text(editor, "see https://example.com/docs for details")
    await browser_client.expect(editor.locator('a[href="https://example.com/docs"]')).to_be_visible()
    await editor.press("Enter")

    # Bare domains in pasted text also get linkified (to https://)
    await paste_text(editor, "check github.com for the code")
    await browser_client.expect(editor.locator('a[href="https://github.com"]')).to_be_visible()
    await editor.press("Enter")

    markdown = (
        "# Pasted heading\n"
        "\n"
        "Some **bold** and *italic* text.\n"
        "\n"
        "- first bullet\n"
        "- second bullet\n"
        "\n"
        "```\n"
        "print('hello')\n"
        "```\n"
        "\n"
        "---\n"
        "\n"
        "| Name | Score |\n"
        "| ---- | ----- |\n"
        "| Ada  | 100   |\n"
    )
    await paste_text(editor, markdown)

    await browser_client.expect(editor.locator("h1")).to_contain_text("Pasted heading")
    await browser_client.expect(editor.locator("strong")).to_contain_text("bold")
    await browser_client.expect(editor.locator("em")).to_contain_text("italic")
    await browser_client.expect(editor.locator("ul li").first).to_contain_text("first bullet")
    await browser_client.expect(editor.locator("pre")).to_contain_text("print('hello')")
    await browser_client.expect(editor.locator("hr")).to_be_attached()
    await browser_client.expect(editor.locator("table th").first).to_contain_text("Name")
    await browser_client.expect(editor.locator("table td").first).to_contain_text("Ada")


@pytest.mark.asyncio
async def test_nested_ordered_list_marker_styles(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    nested_markdown = "1. one\n    1. two\n        1. three\n            1. four\n"
    await paste_text(editor, nested_markdown)

    # Locate the four nested <ol> elements structurally by ol-descent depth,
    # never by rendered marker text.
    level_1 = editor.locator("> ol").first
    level_2 = editor.locator("ol ol").first
    level_3 = editor.locator("ol ol ol").first
    level_4 = editor.locator("ol ol ol ol").first
    await browser_client.expect(level_4).to_be_attached()

    async def list_style_type(locator: Locator) -> str:
        return await locator.evaluate("el => getComputedStyle(el).listStyleType")

    assert await list_style_type(level_1) == "decimal"
    assert await list_style_type(level_2) == "lower-alpha"
    assert await list_style_type(level_3) == "lower-roman"
    assert await list_style_type(level_4) == "lower-roman"


@pytest.mark.asyncio
async def test_document_google_docs_paste(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    # Replica of a Google Docs clipboard payload: the docs-internal-guid <b>
    # wrapper (which once bolded entire pastes, #7029), font-weight spans,
    # a Google redirect link, and a role="checkbox" checklist item.
    google_docs_html = (
        '<meta charset="utf-8">'
        '<b style="font-weight:normal;" id="docs-internal-guid-abc-123">'
        '<h1 dir="ltr"><span style="font-size:23pt;font-weight:400;">GDoc title</span></h1>'
        '<p dir="ltr"><span style="font-weight:400;">Plain words </span>'
        '<span style="font-weight:700;">heavy words</span>'
        '<span style="font-weight:400;"> and a </span>'
        '<a href="https://www.google.com/url?q=https://example.org/target&amp;sa=D&amp;source=editors&amp;ust=17">'
        "link text</a></p>"
        '<ul><li role="checkbox" aria-checked="false" dir="ltr">'
        '<img src="https://www.gstatic.com/checkbox_unchecked.png" width="16" height="16">'
        '<p dir="ltr"><span style="font-weight:400;">gdocs task</span></p></li></ul>'
        "</b>"
    )
    await paste_html(editor, google_docs_html)

    await browser_client.expect(editor.locator("h1")).to_contain_text("GDoc title")
    # The wrapper <b> must not bold everything; only the 700-weight span is bold
    await browser_client.expect(editor.locator("strong", has_text="heavy words")).to_be_visible()
    await browser_client.expect(editor.locator("strong", has_text="Plain words")).to_have_count(0)
    # Google redirect links are unwrapped to their real destination
    await browser_client.expect(editor.locator('a[href="https://example.org/target"]')).to_contain_text("link text")
    # role="checkbox" checklist items become task list items
    await browser_client.expect(editor.locator('li input[type="checkbox"]')).to_be_visible()
    await browser_client.expect(editor.locator('li:has(input[type="checkbox"])')).to_contain_text("gdocs task")


@pytest.mark.asyncio
async def test_document_vscode_markdown_paste(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    # VS Code puts raw markdown into text/html wrapped in cosmetic styling; the
    # clipboard plugin must detect it and re-parse as markdown (#6093)
    vscode_html = (
        '<div style="color: #d4d4d4;background-color: #1e1e1e;font-family: Menlo, Monaco;font-size: 12px;">'
        "<span>## VS Code heading</span><br>"
        "<span>some **bold** text</span><br>"
        "<span>- a bullet</span>"
        "</div>"
    )
    vscode_text = "## VS Code heading\nsome **bold** text\n- a bullet"
    await paste_html(editor, vscode_html, text=vscode_text)

    await browser_client.expect(editor.locator("h2")).to_contain_text("VS Code heading")
    await browser_client.expect(editor.locator("strong")).to_contain_text("bold")
    await browser_client.expect(editor.locator("ul li")).to_contain_text("a bullet")


@pytest.mark.asyncio
async def test_document_task_list_interactions(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    # Backspace in a just-created (empty) task item converts it back to a
    # paragraph without corrupting the doc (#4471 — upstream rule crashed with
    # a RangeError; any crash here also fails the test via the page-error hook).
    # The empty item means the caret is at offset 0 by construction — keyboard
    # caret repositioning is unreliable under Playwright because each press
    # re-focuses the editor, which resets the DOM selection from ProseMirror's
    # not-yet-synced state.
    await editor.type("- ")
    await editor.type("[ ] ")
    checkbox = editor.locator('li input[type="checkbox"]')
    await browser_client.expect(checkbox).to_be_visible()
    await editor.press("Backspace")
    await browser_client.expect(editor.locator('input[type="checkbox"]')).to_have_count(0)
    await editor.type("back to paragraph")
    await browser_client.expect(editor.locator("p", has_text="back to paragraph")).to_be_visible()

    # Clicking a task item's checkbox toggles the checked state
    await editor.press("Enter")
    await editor.type("- ")
    await editor.type("[ ] toggle me")
    await browser_client.expect(checkbox).to_be_visible()
    await checkbox.click()
    await browser_client.expect(checkbox).to_be_checked()
    await checkbox.click()
    await browser_client.expect(checkbox).not_to_be_checked()


@pytest.mark.asyncio
async def test_document_mention_contexts(browser_client: BrowserClient):
    user = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    await create_user(
        email="bob@example.com",
        name="Bob Builder",
        organization_id=user.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    document = await create_document(creator_id=user.id, organization_id=user.organization_id)
    await browser_client.login("alice@example.com")
    editor = await open_editor_with_mention_roster(
        browser_client, f"{browser_client.base_url}/documents/{document.id}/edit"
    )

    suggestion = browser_client.page.locator("button[data-suggester-item]", has_text="Bob Builder")

    # No suggester inside headings (also guards the @-in-document crash, #7043:
    # a page error would fail the test via the browser_client fixture)
    await editor.type("# Title @Bob")
    await browser_client.page.wait_for_timeout(400)
    await browser_client.expect(suggestion).not_to_be_visible()
    await editor.press("Enter")

    # No suggester inside code blocks
    await editor.type("```")
    await editor.type("@Bob")
    await browser_client.page.wait_for_timeout(400)
    await browser_client.expect(suggestion).not_to_be_visible()
    await editor.press("ArrowDown")

    # Control: the suggester does appear in a plain paragraph, and selecting
    # inserts a mention node
    await editor.type("Hello @Bob")
    await browser_client.expect(suggestion).to_be_visible()
    await suggestion.click()
    await browser_client.expect(editor.locator(".prosemirror-mention-node")).to_contain_text("Bob Builder")


@pytest.mark.asyncio
async def test_document_image_upload(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    await paste_image(editor)

    # Exclude ProseMirror's internal cursor-separator img
    image = editor.locator("img:not(.ProseMirror-separator)")
    await browser_client.expect(image).to_be_visible()
    src = await image.get_attribute("src")
    assert src is not None
    assert "/attachments/" in src
    assert "/download" in src


@pytest.mark.asyncio
async def test_document_copy_paste_cycle(browser_client: BrowserClient):
    editor = await open_document_editor(browser_client)

    await paste_text(editor, "# Cycle heading\n\nCycle **bold** text\n\n- cycle item\n")
    await browser_client.expect(editor.locator("h1")).to_contain_text("Cycle heading")

    # Copy the whole document: ProseMirror serializes the selection into the
    # synthetic copy event's DataTransfer
    await editor.press("ControlOrMeta+a")
    payload = await editor.evaluate(
        """el => {
            const dt = new DataTransfer()
            el.dispatchEvent(new ClipboardEvent("copy", { clipboardData: dt, bubbles: true, cancelable: true }))
            return { html: dt.getData("text/html"), text: dt.getData("text/plain") }
        }"""
    )
    assert "Cycle heading" in payload["text"]

    # Paste back over the still-selected content (no click — that would
    # collapse the selection). The doc must come back identical: duplicated
    # or mangled content here was the copy-paste stutter bug (#4987).
    await editor.evaluate(
        """(el, { html, text }) => {
            const dt = new DataTransfer()
            if (html) dt.setData("text/html", html)
            if (text) dt.setData("text/plain", text)
            el.dispatchEvent(new ClipboardEvent("paste", { clipboardData: dt, bubbles: true, cancelable: true }))
        }""",
        payload,
    )

    await browser_client.expect(editor.locator("h1")).to_have_count(1)
    await browser_client.expect(editor.locator("h1")).to_contain_text("Cycle heading")
    await browser_client.expect(editor.locator("strong")).to_have_count(1)
    await browser_client.expect(editor.locator("ul li")).to_have_count(1)


@pytest.mark.asyncio
async def test_document_persistence_roundtrip(browser_client: BrowserClient):
    user = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    await create_user(
        email="bob@example.com",
        name="Bob Builder",
        organization_id=user.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    document = await create_document(creator_id=user.id, organization_id=user.organization_id)
    await browser_client.login("alice@example.com")
    editor = await open_editor_with_mention_roster(
        browser_client, f"{browser_client.base_url}/documents/{document.id}/edit"
    )

    # Every node and mark type in one document, so any serialize → parse
    # regression ("disappearing markdown") on any of them is caught on reload
    kitchen_sink = (
        "# Roundtrip heading\n"
        "\n"
        "Text with **bold**, *italic*, ~~strike~~, `mono`, and a [link](https://example.com/rt).\n"
        "\n"
        "> a quote\n"
        "\n"
        "- bullet one\n"
        "- [ ] open task\n"
        "- [x] done task\n"
        "\n"
        "1. numbered\n"
        "\n"
        "```\n"
        "code\twith tab\n"
        "```\n"
        "\n"
        "```\n"
        "```\n"
        "\n"
        "---\n"
        "\n"
        "| Head | Cell |\n"
        "| ---- | ---- |\n"
        "| Ada  | 100  |\n"
        "\n"
        "Wrapping up "
    )
    await paste_text(editor, kitchen_sink)
    await browser_client.expect(editor.locator("table")).to_be_visible()

    # Add a mention (not expressible in pasted markdown — needs the suggester).
    # The leading space matters: the @ trigger requires a word boundary.
    await editor.type(" @Bob")
    suggestion = browser_client.page.locator("button[data-suggester-item]", has_text="Bob Builder")
    await browser_client.expect(suggestion).to_be_visible()
    await suggestion.click()
    await browser_client.expect(editor.locator(".prosemirror-mention-node")).to_contain_text("Bob Builder")

    # Wait for the IndexedDB provider to sync, then for the server to hold the mention —
    # the last thing added, and what the fresh context below has to read back.
    await browser_client.page.wait_for_function("window.__yIndexeddbSynced === true", timeout=5000)
    await assert_live_markdown_contains(document.get_live_document_markdown, "@[Bob Builder]")

    # A fresh browser context has no local Yjs state, so the content must come
    # back from the server — exercising serialize → store → parse end to end.
    fresh_browser = await browser_client.new_context()
    await fresh_browser.login("alice@example.com")
    await fresh_browser.page.goto(f"{fresh_browser.base_url}/documents/{document.id}/edit")
    fresh_editor = fresh_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    await fresh_browser.expect(fresh_editor).to_be_visible()

    expect = fresh_browser.expect
    await expect(fresh_editor.locator("h1")).to_contain_text("Roundtrip heading")
    await expect(fresh_editor.locator("strong")).to_contain_text("bold")
    await expect(fresh_editor.locator("em")).to_contain_text("italic")
    await expect(fresh_editor.locator("del, s")).to_contain_text("strike")
    await expect(fresh_editor.locator("code").first).to_contain_text("mono")
    await expect(fresh_editor.locator('a[href="https://example.com/rt"]')).to_contain_text("link")
    await expect(fresh_editor.locator("blockquote")).to_contain_text("a quote")
    await expect(fresh_editor.locator("ul li", has_text="bullet one")).to_be_visible()
    await expect(fresh_editor.locator("ol li")).to_contain_text("numbered")
    await expect(fresh_editor.locator('li input[type="checkbox"]')).to_have_count(2)
    await expect(fresh_editor.locator('li input[type="checkbox"]:checked')).to_have_count(1)
    await expect(fresh_editor.locator("hr")).to_be_attached()
    await expect(fresh_editor.locator("table th").first).to_contain_text("Head")
    await expect(fresh_editor.locator("table td").first).to_contain_text("Ada")
    await expect(fresh_editor.locator(".prosemirror-mention-node")).to_contain_text("Bob Builder")
    # An empty code block must survive serialization (#6178 — empty text nodes
    # crashed serialization before EmptyContentSafeCodeBlockExtension)
    await expect(fresh_editor.locator("pre")).to_have_count(2)
    # Tabs inside code blocks must survive the round-trip (#7939)
    pre_text = await fresh_editor.locator("pre").first.text_content()
    assert pre_text is not None and "code\twith tab" in pre_text


@pytest.mark.asyncio
async def test_post_comment_mentions_and_submit(browser_client: BrowserClient):
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    await create_user(
        email="bob@example.com",
        name="Bob Builder",
        organization_id=alice.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    post = await create_post(creator_id=alice.id, organization_id=alice.organization_id)

    await browser_client.login("alice@example.com")
    editor = await open_editor_with_mention_roster(browser_client, f"{browser_client.base_url}/posts/{post.id}")

    await editor.type("Comment with **bold** ")

    # Mention: @-trigger opens the suggester, selecting inserts a mention node
    await editor.type("and a mention @Bob")
    suggestion = browser_client.page.locator("button[data-suggester-item]", has_text="Bob Builder")
    await browser_client.expect(suggestion).to_be_visible()
    await suggestion.click()
    await browser_client.expect(editor.locator(".prosemirror-mention-node")).to_contain_text("Bob Builder")

    # The post-show composer submits via a text "Comment" button that only
    # renders once the editor is focused/expanded (PostCommentComposer.tsx).
    await browser_client.page.locator("#post").get_by_role("button", name="Comment", exact=True).click()

    # The rendered comment proves the markdown serialize → POST → render roundtrip
    await browser_client.expect(editor).not_to_contain_text("Comment with")
    comment = browser_client.page.locator("strong", has_text="bold").last
    await browser_client.expect(comment).to_be_visible()
    # Rendered comments re-emit mentions as span[data-name] (see Markdown.tsx)
    mention = browser_client.page.locator('span[data-name="Bob Builder"]').last
    await browser_client.expect(mention).to_contain_text("@Bob Builder")

    # Mentions must also trigger when editing an existing comment (#7704 — the
    # regression was mentions working on create but not in edit forms)
    await browser_client.page.locator('button[aria-label="Comment actions"]').last.click()
    await browser_client.page.get_by_role("button", name="Edit").click()
    # The edit form's editor precedes the bottom composer in the DOM
    edit_editor = browser_client.page.locator('.ProseMirror[contenteditable="true"]').first
    await browser_client.expect(edit_editor).to_contain_text("Comment with")
    # Click at the text start — a center click can land on the trailing mention
    # atom, which leaves a node selection that swallows typing
    await edit_editor.click(position={"x": 10, "y": 10})
    await edit_editor.press("ControlOrMeta+a")
    await edit_editor.type("Edited with mention @Bob")
    await browser_client.expect(suggestion).to_be_visible()
    await suggestion.click()
    await browser_client.expect(edit_editor.locator(".prosemirror-mention-node")).to_contain_text("Bob Builder")
    await browser_client.page.get_by_role("button", name="Save").click()

    edited_comment = browser_client.page.locator("text=Edited with mention").last
    await browser_client.expect(edited_comment).to_be_visible()
    await browser_client.expect(browser_client.page.locator('span[data-name="Bob Builder"]')).to_have_count(1)


# --- Regression guards: the three tests below were written TDD-style against
# --- bugs fixed in this branch, and encode the previously broken behavior.


@pytest.mark.asyncio
async def test_post_comment_undo_redo(browser_client: BrowserClient):
    # Regression: Mod+z was bound to prosemirror-history's undo in the shared
    # keymap, but the React Editor never registered the history() plugin, so
    # undo/redo silently no-op'd in every non-collaborative editor. Fixed by
    # registering history() unless a feature already provides undo/redo.
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    post = await create_post(creator_id=alice.id, organization_id=alice.organization_id)

    await browser_client.login("alice@example.com")
    await browser_client.page.goto(f"{browser_client.base_url}/posts/{post.id}")

    editor = browser_client.page.locator('.ProseMirror[contenteditable="true"]').first
    await browser_client.expect(editor).to_be_visible()
    await editor.click()

    await editor.type("undo-canary")
    await browser_client.expect(editor).to_contain_text("undo-canary")

    await editor.press("ControlOrMeta+z")
    await browser_client.expect(editor).not_to_contain_text("undo-canary")

    await editor.press("ControlOrMeta+Shift+z")
    await browser_client.expect(editor).to_contain_text("undo-canary")


@pytest.mark.asyncio
async def test_document_redo_after_undo(browser_client: BrowserClient):
    # Regression: on collaborative editors, undoing all content empties the Yjs
    # fragment to zero nodes; ProseMirror schema-fills an empty paragraph and
    # y-prosemirror writes it back as a tracked edit, which cleared the redo
    # stack so redo right after undo restored nothing. Fixed by dropping that
    # schema-fill write from the UndoManager when an undo/redo empties the
    # fragment. The explicit waits make the sync race deterministic.
    editor = await open_document_editor(browser_client)

    await editor.type("redo-canary")
    await browser_client.expect(editor).to_contain_text("redo-canary")
    await browser_client.page.wait_for_function("window.__yIndexeddbSynced === true", timeout=5000)
    await browser_client.page.wait_for_timeout(500)

    await editor.press("ControlOrMeta+z")
    await browser_client.expect(editor).not_to_contain_text("redo-canary")
    # Give the undo's own sync echo time to arrive before redoing
    await browser_client.page.wait_for_timeout(500)

    await editor.press("ControlOrMeta+Shift+z")
    await browser_client.expect(editor).to_contain_text("redo-canary")


@pytest.mark.asyncio
async def test_document_typing_over_selected_mention(browser_client: BrowserClient):
    # Regression: the mention atom was selectable:false, so clicking it (e.g. at
    # the end of a line that ends in a mention) created neither a NodeSelection
    # nor a caret — typing was silently dropped instead of replacing it. Fixed by
    # making mentions selectable, which yields a NodeSelection that typing replaces.
    user = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    await create_user(
        email="bob@example.com",
        name="Bob Builder",
        organization_id=user.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    document = await create_document(creator_id=user.id, organization_id=user.organization_id)
    await browser_client.login("alice@example.com")
    editor = await open_editor_with_mention_roster(
        browser_client, f"{browser_client.base_url}/documents/{document.id}/edit"
    )

    await editor.type("ping @Bob")
    suggestion = browser_client.page.locator("button[data-suggester-item]", has_text="Bob Builder")
    await browser_client.expect(suggestion).to_be_visible()
    await suggestion.click()
    mention = editor.locator(".prosemirror-mention-node")
    await browser_client.expect(mention).to_contain_text("Bob Builder")

    await mention.click()
    # prosemirror-view tags the DOM node a NodeSelection covers, so this waits for
    # the selection the fix produces rather than for a fixed beat.
    await browser_client.expect(mention).to_have_class(re.compile(r"ProseMirror-selectednode"))
    await editor.type("replaced")
    await browser_client.expect(mention).to_have_count(0)
    await browser_client.expect(editor).to_contain_text("replaced")
