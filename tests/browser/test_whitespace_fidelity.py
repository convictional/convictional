import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from playwright.async_api import Frame

from app.helpers.html import render_email_html
from app.models.collaboration.live import LiveDocument
from app.models.collaboration.mailbox import Mailbox
from app.models.workspaces.email.thread import EmailThread
from config import settings
from config.enums import EmailLabel, EmailMessageType, Integration, Sharing
from tests.helpers.assertions import assert_live_markdown_contains
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_document, create_email_message, create_user

# Browser half of the WYSIWYG whitespace-fidelity contract. Proves the load-bearing visual
# invariant on both authored surfaces: N blank lines occupy N line-heights and a single
# hard break occupies exactly one break — with NO doubling. Doubling happens when a stray
# cosmetic `\n` next to a <br> under `white-space: pre-wrap` renders a visible extra blank
# line. The two headline constructs come from tests/fixtures/markdown_whitespace/cases.json.

_CASES = json.loads((settings.root / "tests" / "fixtures" / "markdown_whitespace" / "cases.json").read_text())


def _case_wire(name: str) -> str:
    for case in _CASES["cases"]:
        if case["name"] == name:
            return case["wire"]
    raise KeyError(name)


# blank_run_three_empty_paragraphs: A + 3 empty paragraphs + B (the "3 blank lines" case).
BLANK_RUN_WIRE = _case_wire("blank_run_three_empty_paragraphs")
# single_hard_break_token: `a<hardbreak>b` — one hard break between two lines.
HARD_BREAK_WIRE = _case_wire("single_hard_break_token")

# A leading single-line paragraph seeded into each surface as the line-height reference.
# Measuring the target block as a multiple of this same-surface unit sidesteps font/CSS
# differences between surfaces (the plan forbids cross-surface pixel comparison).
REFERENCE = "ref"

# Per leaf block: its rendered height, whether it holds a <br>, and its trimmed text —
# enough to classify reference / hard-break / empty blocks and express each height as a
# multiple of the reference line-height.
_IN_APP_MEASURE_JS = """() => {
  const nodes = Array.from(document.querySelectorAll('.markdown-content p'))
  return nodes.map(el => ({
    text: (el.textContent || '').trim(),
    hasBr: !!el.querySelector('br'),
    height: el.getBoundingClientRect().height,
  }))
}"""

# Convictional-composed email paragraphs are <div>; measure leaf divs (skip the outer wrapper div).
_EMAIL_MEASURE_JS = """() => {
  const nodes = Array.from(document.querySelectorAll('div')).filter(d => !d.querySelector('div'))
  return nodes.map(el => ({
    text: (el.textContent || '').trim(),
    hasBr: !!el.querySelector('br'),
    height: el.getBoundingClientRect().height,
  }))
}"""


def _reference_height(blocks: list[dict]) -> float:
    refs = [b["height"] for b in blocks if b["text"] == REFERENCE and b["height"] > 0]
    assert refs, f"no reference line-height block found in {blocks}"
    return refs[0]


def _assert_single_hard_break(blocks: list[dict], surface: str) -> None:
    unit = _reference_height(blocks)
    targets = [b for b in blocks if b["hasBr"] and b["text"]]
    assert len(targets) == 1, f"{surface}: expected one hard-break block, got {targets}"
    ratio = targets[0]["height"] / unit
    # Two text lines separated by one <br> = 2 line-heights. Doubling (cosmetic \n next to
    # the <br>) would render a blank line between them = ~3 line-heights.
    assert 1.6 <= ratio <= 2.4, f"{surface}: hard break spans {ratio:.2f}x line-height (want ~2, doubling would be ~3)"


def _assert_blank_run(blocks: list[dict], surface: str) -> None:
    unit = _reference_height(blocks)
    empties = [b for b in blocks if b["hasBr"] and not b["text"]]
    assert len(empties) == 3, f"{surface}: expected 3 empty-line blocks, got {len(empties)} ({blocks})"
    ratios = [b["height"] / unit for b in empties]
    for ratio in ratios:
        # Each empty block is one blank line. Doubling would make it ~2 line-heights.
        assert 0.6 <= ratio <= 1.5, f"{surface}: empty line spans {ratio:.2f}x line-height (~1 expected, doubling ~2)"
    total = sum(ratios)
    # 3 blank lines = ~3 line-heights total; the doubling regression would be ~6.
    assert 2.4 <= total <= 3.6, f"{surface}: blank run spans {total:.2f}x line-height (want ~3, doubling would be ~6)"


async def _poll_blocks(evaluate) -> list[dict]:
    deadline = time.monotonic() + 10
    blocks: list[dict] = []
    while time.monotonic() < deadline:
        blocks = await evaluate()
        if any(b["text"] == REFERENCE and b["height"] > 0 for b in blocks):
            return blocks
        await asyncio.sleep(0.1)
    return blocks


async def _seed_document(creator, wire: str):
    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )
    # set_initial_content stores the wire as the live document's markdown, which the
    # read-only content endpoint serves and DocumentShow feeds to <Markdown>.
    await LiveDocument.set_initial_content(document.live_document_topic, f"{REFERENCE}\n\n{wire}")
    return document


async def _seed_authored_email(recipient, subject: str, external_thread_id: str, wire: str) -> EmailThread:
    # A RECEIVED message establishes the inbox thread; the authored SENT message (composed
    # via render_email_html) is the latest, so it renders expanded with the `authored` class
    # that scopes email.css's pre-wrap. RECEIVED must render under white-space: normal, so
    # this surface is meaningful only on the SENT body.
    received = await create_email_message(
        external_thread_id=external_thread_id,
        subject=subject,
        sender="Alice <alice@example.com>",
        to=[recipient.email],
        body_plain="hello",
        body_html="<p>hello</p>",
        labels=[EmailLabel.INBOX],
        organization_id=recipient.organization_id,
        creator_id=recipient.id,
        received_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await received.fetch_related("thread")

    body_html = str(render_email_html(f"{REFERENCE}\n\n{wire}"))
    await create_email_message(
        creator_id=recipient.id,
        user_id=recipient.id,
        organization_id=recipient.organization_id,
        thread_id=received.thread_id,
        message_type=EmailMessageType.SENT,
        subject=subject,
        body_html=body_html,
        sent_at=datetime.now(UTC),
    )
    await Mailbox.sync(received.thread)
    return received.thread


async def _open_authored_email_frame(browser_client: BrowserClient, subject: str) -> Frame:
    subject_locator = browser_client.page.locator(f'text="{subject}"')
    await browser_client.expect(subject_locator).to_be_visible()
    await subject_locator.click()

    thread_container = browser_client.test_id_locator("email-thread")
    await browser_client.expect(thread_container).to_be_visible()

    # The body iframe is created imperatively with no id/title; find the one whose <html>
    # carries the `authored` class (Convictional-composed SENT mail) once its srcdoc has parsed.
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        handles = await browser_client.page.locator('[data-testid="email-message-body"] iframe').element_handles()
        for handle in handles:
            frame = await handle.content_frame()
            if frame is None:
                continue
            info = await frame.evaluate(
                "() => ({ cls: document.documentElement.className,"
                " kids: document.body ? document.body.children.length : 0 })"
            )
            if "authored" in info["cls"] and info["kids"] > 0:
                return frame
        await asyncio.sleep(0.1)
    raise AssertionError(f"authored email body iframe never appeared for subject {subject!r}")


@pytest.mark.asyncio
async def test_whitespace_line_height_invariant_per_surface(browser_client: BrowserClient):
    creator = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    viewer = await create_user(
        email="bob@example.com",
        organization_id=creator.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )

    blank_doc = await _seed_document(creator, BLANK_RUN_WIRE)
    hard_break_doc = await _seed_document(creator, HARD_BREAK_WIRE)

    # viewer is an org member but not a collaborator, so DocumentShow renders the read-only
    # <Markdown> view instead of redirecting to the editor.
    blank_thread = await _seed_authored_email(viewer, "Blank Run Fidelity", "thread-blank-run", BLANK_RUN_WIRE)
    hard_break_thread = await _seed_authored_email(viewer, "Hard Break Fidelity", "thread-hard-break", HARD_BREAK_WIRE)
    assert blank_thread.id != hard_break_thread.id

    await browser_client.login("bob@example.com")

    # --- In-app read-only render surface (markdown-content.css pre-wrap + rehype strip) ---
    await browser_client.page.goto(f"{browser_client.base_url}/documents/{blank_doc.id}")
    blocks = await _poll_blocks(lambda: browser_client.page.evaluate(_IN_APP_MEASURE_JS))
    _assert_blank_run(blocks, "in-app blank run")

    await browser_client.page.goto(f"{browser_client.base_url}/documents/{hard_break_doc.id}")
    blocks = await _poll_blocks(lambda: browser_client.page.evaluate(_IN_APP_MEASURE_JS))
    _assert_single_hard_break(blocks, "in-app hard break")

    # --- Authored email iframe surface (email.css pre-wrap scoped to .authored) ---
    await browser_client.page.goto(browser_client.base_url)
    frame = await _open_authored_email_frame(browser_client, "Blank Run Fidelity")
    blocks = await _poll_blocks(lambda: frame.evaluate(_EMAIL_MEASURE_JS))
    _assert_blank_run(blocks, "email blank run")

    await browser_client.page.goto(browser_client.base_url)
    frame = await _open_authored_email_frame(browser_client, "Hard Break Fidelity")
    blocks = await _poll_blocks(lambda: frame.evaluate(_EMAIL_MEASURE_JS))
    _assert_single_hard_break(blocks, "email hard break")


@pytest.mark.asyncio
async def test_editor_to_read_only_render_whitespace(browser_client: BrowserClient):
    # End-to-end: type into the ProseMirror editor, let it serialize to the wire and sync to
    # the server, then open the read-only render and assert both the structure and the
    # no-doubling height invariant. This closes the gap the editor's RTE→wire round-trip and
    # the wire→render parity checks don't jointly guarantee.
    #
    # Shift+Enter now splits into a NEW PARAGRAPH (PR #8904 bound Shift-Enter → splitBlock),
    # so `a` Shift+Enter `b` produces two separate paragraphs rather than an in-paragraph hard
    # break. The blank-line run (three empty paragraphs) is still the doubling-regression guard.
    creator = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    # An org member who isn't a collaborator, so DocumentShow renders the read-only view.
    await create_user(
        email="bob@example.com",
        organization_id=creator.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    document = await create_document(
        creator_id=creator.id,
        organization_id=creator.organization_id,
        sharing=Sharing.ORGANIZATION,
    )

    await browser_client.login("alice@example.com")
    await browser_client.page.goto(f"{browser_client.base_url}/documents/{document.id}/edit")
    editor = browser_client.page.locator('.ProseMirror[contenteditable="true"]').first
    await browser_client.expect(editor).to_be_visible()
    await editor.click()

    # Reference line, then `a` Shift+Enter `b` (now a paragraph split, not a hard break),
    # then A + three empty paragraphs (Enter x4) + B.
    await editor.type(REFERENCE)
    await editor.press("Enter")
    await editor.type("a")
    await editor.press("Shift+Enter")
    await editor.type("b")
    await editor.press("Enter")
    await editor.type("A")
    await editor.press("Enter")
    await editor.press("Enter")
    await editor.press("Enter")
    await editor.press("Enter")
    await editor.type("B")
    await browser_client.expect(editor.get_by_text("B", exact=True)).to_be_visible()

    # Let the Yjs provider persist the serialized markdown to the server before the viewer
    # (a fresh context with no local Yjs state) reads it back. "B" is the last character
    # typed, so the server holding it means the whole edit sequence arrived.
    await browser_client.page.wait_for_function("window.__yIndexeddbSynced === true", timeout=5000)
    await assert_live_markdown_contains(document.get_live_document_markdown, "B")

    reader = await browser_client.new_context()
    await reader.login("bob@example.com")
    await reader.page.goto(f"{reader.base_url}/documents/{document.id}")

    async def evaluate():
        return await reader.page.evaluate(_IN_APP_MEASURE_JS)

    blocks = await _poll_blocks(evaluate)

    # Structure: `a` and `b` are two SEPARATE paragraphs (Shift+Enter = splitBlock, no
    # in-paragraph hard break), so the only <br>s are the three empty <p><br></p> = 3 total.
    br_count = await reader.page.locator(".markdown-content p br").count()
    assert br_count == 3, (
        f"expected 3 <br> (3 empty lines; Shift+Enter now splits paragraphs), got {br_count} ({blocks})"
    )

    # `a` and `b` render as distinct single-line paragraphs — no <br>, each one line-height,
    # no doubling.
    unit = _reference_height(blocks)
    for label in ("a", "b"):
        matches = [b for b in blocks if b["text"] == label]
        assert len(matches) == 1, f"editor round-trip: expected one '{label}' paragraph, got {matches}"
        block = matches[0]
        assert not block["hasBr"], f"editor round-trip: '{label}' paragraph should hold no <br>, got {block}"
        ratio = block["height"] / unit
        assert 0.6 <= ratio <= 1.5, (
            f"editor round-trip: '{label}' paragraph spans {ratio:.2f}x line-height (want ~1, doubling would be ~2)"
        )

    _assert_blank_run(blocks, "editor round-trip blank run")
