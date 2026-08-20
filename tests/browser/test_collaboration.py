import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.models.collaboration.mailbox import Mailbox
from app.models.collaboration.workspace import Visit, WorkspaceMixin
from app.models.workspaces.meetings import MeetingAttendee
from config import settings
from config.enums import EmailLabel, Integration, MeetingAttendeeStatus, Sharing
from tests.helpers.assertions import assert_live_markdown_contains
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import (
    create_collaborator,
    create_document,
    create_email_message,
    create_meeting,
    create_post,
    create_user,
)

# The comment highlights in the document editor, and the text they cover.
_HIGHLIGHT_STATE_JS = """
() => {
  const editor = document.querySelector('.ProseMirror[contenteditable="true"]')
  const spans = editor ? editor.querySelectorAll('.inline-comment-highlight') : []
  return {
    ids: Array.from(new Set(Array.from(spans, s => s.getAttribute('data-comment-id')))),
    text: Array.from(spans, s => s.textContent).join(""),
  }
}
"""


async def _assert_one_highlight_covering(client: BrowserClient, text: str) -> None:
    """Assert one logical comment highlight (a single comment id) still covers `text`.

    A single highlight range renders as several adjacent spans whenever something splits
    it: y-prosemirror rebuilds paragraphs from Yjs items, and a peer's remote-cursor
    widget inside the range breaks the run in two. Counting spans therefore tracks where
    the peer's caret happens to sit, not whether the highlight survived."""
    deadline = asyncio.get_running_loop().time() + settings.browser_test_default_timeout / 1000
    state: dict = {}
    while asyncio.get_running_loop().time() < deadline:
        state = await client.page.evaluate(_HIGHLIGHT_STATE_JS)
        if len(state["ids"]) == 1 and text in state["text"]:
            return
        await asyncio.sleep(0.1)
    raise AssertionError(f"expected one comment highlight covering {text!r}, got {state}")


@pytest.mark.asyncio
async def test_thread_collaboration(browser_client: BrowserClient):
    # Setup data
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    bob = await create_user(
        email="bob@example.com",
        organization_id=alice.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    message = await create_email_message(
        external_thread_id="thread-1",
        subject="Project Update",
        sender="Charlie <charlie@example.com>",
        to=[bob.email],
        body_plain="Hi Bob, here's the project update.",
        body_html="<p>Hi Bob, here's the project update.</p>",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await message.fetch_related("thread")
    thread = message.thread
    await Mailbox.sync(thread)

    # Login as both users in separate browsers
    bobs_browser = await browser_client.new_context()
    await bobs_browser.login("bob@example.com")
    alice_browser = await browser_client.new_context()
    await alice_browser.login("alice@example.com")

    # Bob opens the thread
    mailbox_entry = bobs_browser.page.locator('text="Project Update"')
    await bobs_browser.expect(mailbox_entry).to_be_visible()
    await mailbox_entry.click()
    thread_container = bobs_browser.test_id_locator("email-thread")
    await bobs_browser.expect(thread_container).to_be_visible()

    # Bob adds Alice as a collaborator
    collaborators_dropdown = bobs_browser.test_id_locator("workspace-collaborators")
    await bobs_browser.expect(collaborators_dropdown).to_be_visible()
    await collaborators_dropdown.click()
    add_alice_button = bobs_browser.test_id_locator(f"add-collaborator-{alice.id}").locator("button")
    await bobs_browser.expect(add_alice_button).to_be_visible()
    await add_alice_button.click()
    collaborators = bobs_browser.test_id_locator("current-collaborators")
    await bobs_browser.expect(collaborators).to_be_visible()
    await bobs_browser.expect(collaborators).to_contain_text("alice@example.com")

    # Per-collaborator view state renders in each row. Alice was just added and has never
    # opened the thread, so her Visit-backed state deterministically reads "Not viewed yet".
    view_states = bobs_browser.test_id_locator("collaborator-view-state")
    await bobs_browser.expect(view_states.first).to_be_visible()
    await bobs_browser.expect(collaborators).to_contain_text("Not viewed yet")

    # Alice sees the thread appear in her inbox
    await Mailbox.sync(thread)  # Force sync due to backend debounce
    await alice_browser.page.reload()  # Force refresh due to backend debounce
    alice_mailbox_entry = alice_browser.page.locator('text="Project Update"')
    await alice_browser.expect(alice_mailbox_entry).to_be_visible()
    await alice_mailbox_entry.click()
    alice_thread_container = alice_browser.test_id_locator("email-thread")
    await alice_browser.expect(alice_thread_container).to_be_visible()

    # Alice leaves a comment
    comment_input = alice_browser.test_id_locator("comment-form").locator('.ProseMirror[contenteditable="true"]')
    await alice_browser.expect(comment_input).to_be_visible()
    await comment_input.type("This is interesting Bob.")
    submit_button = alice_browser.test_id_locator("comment-form").locator("button[aria-label='Send']")
    await alice_browser.expect(submit_button).to_be_visible()
    await submit_button.click()
    comment = alice_thread_container.locator('text="This is interesting Bob."').first
    await alice_browser.expect(comment).to_be_visible()

    # Bob sees Alice's comment appear in real-time
    comment = thread_container.locator('text="This is interesting Bob."').first
    await bobs_browser.expect(comment).to_be_visible()

    # Bob starts a draft reply
    reply_button = bobs_browser.page.get_by_role("button", name="Reply").first
    await bobs_browser.expect(reply_button).to_be_visible()
    await reply_button.click()

    bob_editor = bobs_browser.test_id_locator("body-editor").locator('.ProseMirror[contenteditable="true"]')
    await bobs_browser.expect(bob_editor).to_be_visible()
    await bobs_browser.expect(bob_editor).to_have_attribute("contenteditable", "true")

    # Bob writes in the draft
    await bob_editor.click()
    await bob_editor.type("Hi Charlie, thanks for the update.")

    # Alice should see the draft appear and see Bob's content (collaborative editing)
    alice_editor = alice_browser.test_id_locator("body-editor").locator('.ProseMirror[contenteditable="true"]')
    await alice_browser.expect(alice_editor).to_be_visible()
    await alice_browser.expect(alice_editor).to_contain_text("Hi Charlie, thanks for the update.")

    # Alice writes in the draft
    await alice_editor.click()
    await alice_editor.type(" I agree with this approach.")

    # Bob should see Alice's updates (tests bidirectional sync)
    await bobs_browser.expect(bob_editor).to_contain_text("I agree with this approach.")


@pytest.mark.asyncio
async def test_meeting_agenda_collaboration(browser_client: BrowserClient):
    # Setup data
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    bob = await create_user(
        email="bob@example.com",
        organization_id=alice.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    meeting = await create_meeting(
        title="Q1 Planning Meeting",
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        scheduled_end_at=datetime.now(UTC) + timedelta(days=1, hours=1),
        attendees=[
            MeetingAttendee(name=alice.email, user_id=alice.id, status=MeetingAttendeeStatus.ACCEPTED),
            MeetingAttendee(name=bob.email, user_id=bob.id, status=MeetingAttendeeStatus.ACCEPTED),
        ],
        organization_id=alice.organization_id,
        creator_id=alice.id,
    )

    # Login as both users in separate browsers
    alice_browser = await browser_client.new_context()
    await alice_browser.login("alice@example.com")
    bob_browser = await browser_client.new_context()
    await bob_browser.login("bob@example.com")

    # Navigate to the meeting page
    await alice_browser.page.goto(f"{alice_browser.base_url}/meetings/{meeting.id}")
    await bob_browser.page.goto(f"{bob_browser.base_url}/meetings/{meeting.id}")

    # Click on the Agenda tab to ensure it's active
    alice_agenda_tab = alice_browser.page.get_by_role("tab", name="Agenda")
    await alice_browser.expect(alice_agenda_tab).to_be_visible()
    await alice_agenda_tab.click()

    bob_agenda_tab = bob_browser.page.get_by_role("tab", name="Agenda")
    await bob_browser.expect(bob_agenda_tab).to_be_visible()
    await bob_agenda_tab.click()

    # Locate the agenda editors
    alice_editor = alice_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    bob_editor = bob_browser.page.locator('.ProseMirror[contenteditable="true"]').first

    await alice_browser.expect(alice_editor).to_be_visible()
    await bob_browser.expect(bob_editor).to_be_visible()

    # Alice types in the agenda
    await alice_editor.click()
    await alice_editor.type("Meeting objectives for Q1:")

    # Bob should see Alice's content (real-time sync)
    await bob_browser.expect(bob_editor).to_contain_text("Meeting objectives for Q1:")

    # Bob adds to the agenda
    await bob_editor.click()
    await bob_editor.type(" Launch new product feature")

    # Alice should see Bob's updates (bidirectional sync)
    await alice_browser.expect(alice_editor).to_contain_text("Launch new product feature")

    # Both users should see the complete combined content
    await alice_browser.expect(alice_editor).to_contain_text("Meeting objectives for Q1: Launch new product feature")
    await bob_browser.expect(bob_editor).to_contain_text("Meeting objectives for Q1: Launch new product feature")


@pytest.mark.asyncio
async def test_meeting_agenda_offline_persistence(browser_client: BrowserClient):
    user = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    meeting = await create_meeting(
        title="Offline Persistence Meeting",
        scheduled_at=datetime.now(UTC) + timedelta(days=1),
        scheduled_end_at=datetime.now(UTC) + timedelta(days=1, hours=1),
        attendees=[
            MeetingAttendee(name=user.email, user_id=user.id, status=MeetingAttendeeStatus.ACCEPTED),
        ],
        organization_id=user.organization_id,
        creator_id=user.id,
    )

    await browser_client.login("alice@example.com")

    # Navigate to the meeting and open the Agenda tab
    await browser_client.page.goto(f"{browser_client.base_url}/meetings/{meeting.id}")
    agenda_tab = browser_client.page.get_by_role("tab", name="Agenda")
    await browser_client.expect(agenda_tab).to_be_visible()
    await agenda_tab.click()

    editor = browser_client.page.locator('.ProseMirror[contenteditable="true"]').first
    await browser_client.expect(editor).to_be_visible()

    # Add an agenda item while online and wait for it to sync
    await editor.click()
    await editor.type("Online agenda item")
    await browser_client.expect(editor).to_contain_text("Online agenda item")

    # Wait for the IndexedDB provider to sync, then for the server to actually hold the
    # item: it is what has to survive the offline edit and reload below.
    await browser_client.page.wait_for_function("window.__yIndexeddbSynced === true", timeout=5000)
    await assert_live_markdown_contains(meeting.get_agenda_markdown, "Online agenda item")

    # Go offline, which disconnects the WebSocket
    await browser_client.page.context.set_offline(True)

    # Add another agenda item while offline
    await editor.type(" Offline agenda item")
    await browser_client.expect(editor).to_contain_text("Offline agenda item")

    # Fence any pending IndexedDB writes before reloading. Opening a read
    # transaction on the same store guarantees prior writes have committed.
    await browser_client.page.evaluate("""async () => {
        const dbs = await indexedDB.databases();
        if (!dbs.length) return;
        return new Promise(resolve => {
            const req = indexedDB.open(dbs[0].name);
            req.onsuccess = (e) => {
                const db = e.target.result;
                const tx = db.transaction('updates', 'readonly');
                tx.oncomplete = () => { db.close(); resolve(); };
                tx.objectStore('updates').count();
            };
            req.onerror = () => resolve();
        });
    }""")

    # Go back online and reload, destroying the in-memory Y.Doc
    await browser_client.page.context.set_offline(False)
    await browser_client.page.reload(wait_until="domcontentloaded")

    # Navigate back to the Agenda tab
    agenda_tab = browser_client.page.get_by_role("tab", name="Agenda")
    await browser_client.expect(agenda_tab).to_be_visible()
    await agenda_tab.click()

    editor = browser_client.page.locator('.ProseMirror[contenteditable="true"]').first
    await browser_client.expect(editor).to_be_visible()

    # Both the online and offline edits should be present after reload
    await browser_client.expect(editor).to_contain_text("Online agenda item")
    await browser_client.expect(editor).to_contain_text("Offline agenda item")

    # Verify the offline edit actually synced to the server (not just IndexedDB)
    # by opening a fresh browser context with no local state
    fresh_browser = await browser_client.new_context()
    await fresh_browser.login("alice@example.com")
    await fresh_browser.page.goto(f"{fresh_browser.base_url}/meetings/{meeting.id}")
    agenda_tab = fresh_browser.page.get_by_role("tab", name="Agenda")
    await fresh_browser.expect(agenda_tab).to_be_visible()
    await agenda_tab.click()

    fresh_editor = fresh_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    await fresh_browser.expect(fresh_editor).to_be_visible()
    await fresh_browser.expect(fresh_editor).to_contain_text("Online agenda item")
    await fresh_browser.expect(fresh_editor).to_contain_text("Offline agenda item")


@pytest.mark.asyncio
async def test_comment_highlight_survives_concurrent_peer(browser_client: BrowserClient):
    # Regression: document comments break when two users are in the doc at once.
    #
    # Opening the comment card applies a "pending" comment mark to the shared Yjs
    # doc *before* the comment is saved (CommentSystem.addMarkAtSelection). That
    # mark is part of the ProseMirror doc, so ySyncPlugin broadcasts it to the
    # other peer. On the peer, useCommentMarks sees a comment mark with no backing
    # thread; after its 500ms confirming refetch finds no comment (the author is
    # still composing), cleanupOrphanMarks treats it as a cross-doc-paste orphan
    # and removes it — and because that removal is a ProseMirror transaction, Yjs
    # broadcasts the deletion back, stripping the highlight from the *author's*
    # editor mid-composition. The comment then has no text anchor and is lost.
    #
    # The single-tab protection (pendingCommentId) can't help: it is local to the
    # author's tab, and the peer has no signal that the mark is a live, unsaved
    # pending mark rather than a genuine orphan. See
    # docs/plans/2026-07-06-001-fix-document-comment-highlight-multiuser-plan.md.
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    bob = await create_user(
        email="bob@example.com",
        organization_id=alice.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    document = await create_document(
        creator_id=alice.id, organization_id=alice.organization_id, sharing=Sharing.ORGANIZATION
    )
    # Both users edit the document, so both are collaborators with the live editor.
    await document.fetch_related("workspace")
    await document.collaboration.add(bob, alice)

    # Alice opens the document and types the text she will comment on.
    alice_browser = await browser_client.new_context()
    await alice_browser.login("alice@example.com")
    await alice_browser.page.goto(f"{alice_browser.base_url}/documents/{document.id}/edit")
    alice_editor = alice_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    await alice_browser.expect(alice_editor).to_be_visible()
    await alice_editor.click()
    await alice_editor.type("The quick brown fox jumps over the lazy dog.")

    # Bob opens the same document and must see Alice's text — this proves both
    # peers are connected and synced before the comment is created.
    bob_browser = await browser_client.new_context()
    await bob_browser.login("bob@example.com")
    await bob_browser.page.goto(f"{bob_browser.base_url}/documents/{document.id}/edit")
    bob_editor = bob_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    await bob_browser.expect(bob_editor).to_be_visible()
    await bob_browser.expect(bob_editor).to_contain_text("The quick brown fox")

    # Alice opens a comment on the current block. The gutter's "Add comment" button
    # adds a local-only pending decoration — it never enters the shared Yjs doc,
    # so Bob cannot see it and cannot trigger orphan cleanup on it.
    await alice_editor.click()
    add_comment_button = alice_browser.page.locator('button[title="Add comment"]')
    await alice_browser.expect(add_comment_button).to_be_visible()
    await add_comment_button.click()

    comment_form = alice_browser.page.locator("[data-comment-form]")
    await alice_browser.expect(comment_form).to_be_visible()
    await _assert_one_highlight_covering(alice_browser, "lazy dog")

    # Alice takes a moment to compose (as any user would), and Bob's editor is watched
    # across that window rather than slept through. The destroy chain starts the instant
    # the mark reaches the shared doc, where Bob renders a highlight for it; only then
    # does his 500ms confirming refetch strip it and broadcast the removal back. Sleeping
    # and checking Alice at the end lets a slow machine hide the regression, because the
    # damage may not have completed yet — watching Bob catches the leak itself.
    for _ in range(10):
        await bob_browser.expect(bob_editor.locator(".inline-comment-highlight")).to_have_count(0)
        await _assert_one_highlight_covering(alice_browser, "lazy dog")
        await alice_browser.page.wait_for_timeout(250)

    # And the comment must save with its anchor intact.
    comment_field = comment_form.locator('.ProseMirror[contenteditable="true"]')
    await comment_field.click()
    await comment_field.type("Needs more detail here.")
    await comment_form.get_by_role("button", name="Comment", exact=True).click()

    await _assert_one_highlight_covering(alice_browser, "lazy dog")
    await _assert_one_highlight_covering(bob_browser, "lazy dog")


@pytest.mark.asyncio
async def test_comment_highlight_survives_concurrent_peer_edit(browser_client: BrowserClient):
    # Regression: while Alice is composing a comment, Bob typing *anywhere* in the
    # doc would orphan Alice's comment.
    #
    # The pending highlight is a local-only decoration (kept out of the Yjs doc so
    # peers can't strip it). But y-prosemirror applies every remote change by
    # replacing the whole document (sync-plugin `_typeChanged`), and mapping a
    # decoration through that replace-all drops it. So Bob's keystroke, arriving as
    # a remote change, wiped Alice's highlight — and the subsequent save had no
    # anchor. The fix anchors the pending highlight to a Yjs relative position and
    # recomputes it on remote changes (as y-prosemirror's yCursorPlugin does).
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    bob = await create_user(
        email="bob@example.com",
        organization_id=alice.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    document = await create_document(
        creator_id=alice.id, organization_id=alice.organization_id, sharing=Sharing.ORGANIZATION
    )
    await document.fetch_related("workspace")
    await document.collaboration.add(bob, alice)

    alice_browser = await browser_client.new_context()
    await alice_browser.login("alice@example.com")
    await alice_browser.page.goto(f"{alice_browser.base_url}/documents/{document.id}/edit")
    alice_editor = alice_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    await alice_browser.expect(alice_editor).to_be_visible()
    await alice_editor.click()
    await alice_editor.type("The quick brown fox jumps over the lazy dog.")

    bob_browser = await browser_client.new_context()
    await bob_browser.login("bob@example.com")
    await bob_browser.page.goto(f"{bob_browser.base_url}/documents/{document.id}/edit")
    bob_editor = bob_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    await bob_browser.expect(bob_editor).to_be_visible()
    await bob_browser.expect(bob_editor).to_contain_text("The quick brown fox")

    # Alice opens a comment on her text; the pending highlight appears.
    await alice_editor.click()
    add_comment_button = alice_browser.page.locator('button[title="Add comment"]')
    await alice_browser.expect(add_comment_button).to_be_visible()
    await add_comment_button.click()
    comment_form = alice_browser.page.locator("[data-comment-form]")
    await alice_browser.expect(comment_form).to_be_visible()
    await _assert_one_highlight_covering(alice_browser, "lazy dog")

    # Bob types at the start of the doc — a remote change that shifts Alice's
    # highlighted text and triggers y-prosemirror's whole-document replace on her
    # editor. Waiting for the text to appear on Alice's side proves it landed.
    await bob_editor.click()
    await bob_browser.page.keyboard.press("Home")
    await bob_editor.type("BOB EDIT ")
    await alice_browser.expect(alice_editor).to_contain_text("BOB EDIT")

    # The highlight must survive Bob's remote edit...
    await _assert_one_highlight_covering(alice_browser, "lazy dog")

    # ...and the comment must save with its anchor intact for both peers.
    comment_field = comment_form.locator('.ProseMirror[contenteditable="true"]')
    await comment_field.click()
    await comment_field.type("Anchored to the fox.")
    await comment_form.get_by_role("button", name="Comment", exact=True).click()

    await _assert_one_highlight_covering(alice_browser, "lazy dog")
    await _assert_one_highlight_covering(bob_browser, "lazy dog")


@pytest.mark.asyncio
async def test_editing_a_comment_keeps_the_caret_where_it_is_placed(browser_client: BrowserClient):
    # Regression (#8826): the caret must stay where it's placed when editing an existing
    # comment. Only pre-existing text exposes the bug — empty new-comment/reply fields
    # already have the caret at the start.
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    document = await create_document(
        creator_id=alice.id, organization_id=alice.organization_id, sharing=Sharing.ORGANIZATION
    )

    alice_browser = await browser_client.new_context()
    await alice_browser.login("alice@example.com")
    await alice_browser.page.goto(f"{alice_browser.base_url}/documents/{document.id}/edit")
    editor = alice_browser.page.locator('.ProseMirror[contenteditable="true"]').first
    await alice_browser.expect(editor).to_be_visible()
    await editor.click()
    await editor.type("The quick brown fox jumps over the lazy dog.")

    # Add a comment on the current block via the gutter "Add comment" button.
    await editor.click()
    add_comment_button = alice_browser.page.locator('button[title="Add comment"]')
    await alice_browser.expect(add_comment_button).to_be_visible()
    await add_comment_button.click()

    comment_form = alice_browser.page.locator("[data-comment-form]")
    await alice_browser.expect(comment_form).to_be_visible()
    comment_field = comment_form.locator('.ProseMirror[contenteditable="true"]')
    await comment_field.click()
    await comment_field.type("aaaaaaaa bbbbbbbb cccccccc")
    await comment_form.get_by_role("button", name="Comment", exact=True).click()

    # Saving closes the card; re-open it by clicking the highlight, then Edit.
    highlight = editor.locator(".inline-comment-highlight").first
    await alice_browser.expect(highlight).to_be_visible()
    await highlight.click()

    active_card = alice_browser.page.locator("[data-comment-cards] [data-for-comment-id]")
    await alice_browser.expect(active_card).to_be_visible()
    await active_card.get_by_text("more_horiz").click()
    await alice_browser.page.get_by_role("button", name="Edit").click()

    edit_field = active_card.locator('.ProseMirror[contenteditable="true"]')
    await alice_browser.expect(edit_field).to_contain_text("aaaaaaaa bbbbbbbb cccccccc")

    # Move the DOM selection into the middle of the text directly: headless Chromium's
    # synthetic clicks don't place the caret positionally inside a ProseMirror
    # contenteditable, but this fires the same `selectionchange` a click would. Wait two
    # frames so the buggy reassertion (react-prosemirror's next-frame commit) can fire
    # before we type.
    await alice_browser.page.evaluate("""async () => {
      const field = document.querySelector('[data-for-comment-id] .ProseMirror[contenteditable="true"]');
      field.focus();
      const paragraph = field.querySelector('p') || field;
      const textNode = paragraph.firstChild;
      const range = document.createRange();
      range.setStart(textNode, 15);
      range.collapse(true);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    }""")
    await alice_browser.page.keyboard.type("ZZ")

    # The marker lands at the caret (offset 15); the bug would snap to the start and
    # prepend it ("ZZaaaaaaaa bbbbbbbb cccccccc").
    await alice_browser.expect(edit_field).to_have_text("aaaaaaaa bbbbbbZZbb cccccccc")

    # And the edit persists with the marker in place after saving.
    await active_card.get_by_role("button", name="Save").click()
    await alice_browser.expect(active_card).to_contain_text("aaaaaaaa bbbbbbZZbb cccccccc")


async def _seed_view_state_resource(kind: str, viewer, viewed, unviewed) -> str:
    """Create a resource of `kind` owned by `viewer` with `viewed`/`unviewed` as
    collaborators, seed a Visit for `viewed`, and return the URL of the page whose
    header carries the collaborators dropdown. One branch per workspace that surfaces
    the view-state UX: meeting show, document editor, post draft editor, and shared
    email thread — all uniformly Visit-backed via the shared /visits endpoint."""
    org_id = viewer.organization_id
    resource: WorkspaceMixin
    if kind == "meeting":
        resource = await create_meeting(
            title="View State Meeting",
            scheduled_at=datetime.now(UTC) + timedelta(days=1),
            scheduled_end_at=datetime.now(UTC) + timedelta(days=1, hours=1),
            attendees=[MeetingAttendee(name=viewer.email, user_id=viewer.id, status=MeetingAttendeeStatus.ACCEPTED)],
            organization_id=org_id,
            creator_id=viewer.id,
        )
        url = f"/meetings/{resource.id}"
    elif kind == "document":
        resource = await create_document(creator_id=viewer.id, organization_id=org_id, sharing=Sharing.ORGANIZATION)
        url = f"/documents/{resource.id}/edit"
    elif kind == "post_draft":
        resource = await create_post(creator_id=viewer.id, organization_id=org_id, published_at=None)
        url = f"/posts/{resource.id}/edit"
    elif kind == "email_thread":
        message = await create_email_message(
            subject="Shared Thread View State",
            to=[viewer.email],
            organization_id=org_id,
            creator_id=viewer.id,
            labels=[EmailLabel.INBOX],
        )
        await message.fetch_related("thread")
        resource = message.thread
        await Mailbox.sync(resource)
        # The viewer opens the thread by URL, so they must be a collaborator to pass the
        # access check (org sharing off for a private inbox thread). Adding is idempotent.
        await resource.fetch_related("workspace")
        await resource.collaboration.add(viewer, viewer)
        url = f"/email_threads/{resource.id}"
    else:
        raise ValueError(f"Unknown resource kind: {kind}")

    await resource.fetch_related("workspace")
    workspace_id = resource.workspace_id
    await create_collaborator(workspace_id=workspace_id, user_id=viewed.id, name=viewed.display_name)
    await create_collaborator(workspace_id=workspace_id, user_id=unviewed.id, name=unviewed.display_name)
    # A recorded Visit is the uniform view-state source for every resource, email threads
    # included (they record visits via the shared /visits endpoint).
    await Visit.record(user_id=viewed.id, workspace_id=workspace_id)
    return url


@pytest.mark.parametrize("kind", ["meeting", "document", "post_draft", "email_thread"])
@pytest.mark.asyncio
async def test_collaborator_view_state_indicator(browser_client: BrowserClient, kind: str):
    # Every workspace that surfaces the collaborators dropdown must render per-collaborator
    # view state: a "Viewed …" line for someone with a Visit, and a "Not viewed yet" line
    # for a collaborator who has never opened the resource.
    viewer = await create_user(
        email="viewer@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    viewed = await create_user(
        email="viewed@example.com",
        organization_id=viewer.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    unviewed = await create_user(
        email="unviewed@example.com",
        organization_id=viewer.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )

    url = await _seed_view_state_resource(kind, viewer, viewed, unviewed)

    await browser_client.login("viewer@example.com")
    await browser_client.page.goto(f"{browser_client.base_url}{url}")

    dropdown = browser_client.test_id_locator("workspace-collaborators")
    await browser_client.expect(dropdown).to_be_visible()
    await dropdown.click()

    collaborators = browser_client.test_id_locator("current-collaborators")
    await browser_client.expect(collaborators).to_be_visible()

    # Both view states render in the list: the seeded Visit reads "Viewed", and the
    # collaborator with no Visit reads "Not viewed yet".
    indicators = collaborators.locator('[data-test-id="collaborator-view-state"]')
    await browser_client.expect(indicators.first).to_be_visible()
    await browser_client.expect(collaborators).to_contain_text("Viewed")
    await browser_client.expect(collaborators).to_contain_text("Not viewed yet")
