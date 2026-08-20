import pytest

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from config.enums import EmailLabel, Integration
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_email_message, create_user

# Pure ordered-in-ordered nesting (never <ol> inside <ul>), no inline
# list-style-type, simulating received external mail so email.css rules govern
# the markers.
NESTED_OL_BODY_HTML = "<ol><li>one<ol><li>two<ol><li>three<ol><li>four</li></ol></li></ol></li></ol></li></ol>"


@pytest.mark.asyncio
async def test_archiving_thread(browser_client: BrowserClient):
    # Create threads
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    project_update_message = await create_email_message(
        external_thread_id="thread-1",
        subject="Project Update",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="Hi Bob, here's the project update.",
        body_html="<p>Hi Bob, here's the project update.</p>",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await project_update_message.fetch_related("thread")
    project_update = project_update_message.thread

    meeting_message = await create_email_message(
        external_thread_id="thread-2",
        subject="Meeting Request",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="Can we schedule a meeting?",
        body_html="<p>Can we schedule a meeting?</p>",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await meeting_message.fetch_related("thread")
    meeting = meeting_message.thread

    budget_message = await create_email_message(
        external_thread_id="thread-3",
        subject="Budget Review",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="Please review the budget.",
        body_html="<p>Please review the budget.</p>",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await budget_message.fetch_related("thread")
    budget = budget_message.thread

    await Mailbox.sync(project_update)
    await Mailbox.sync(meeting)
    await Mailbox.sync(budget)

    # Login as Bob
    await browser_client.login("bob@example.com")

    # Verify threads appear in the React inbox
    project_update_subject = browser_client.page.locator('text="Project Update"')
    await browser_client.expect(project_update_subject).to_be_visible()
    meeting_subject = browser_client.page.locator('text="Meeting Request"')
    await browser_client.expect(meeting_subject).to_be_visible()
    budget_subject = browser_client.page.locator('text="Budget Review"')
    await browser_client.expect(budget_subject).to_be_visible()

    # View thread and verify we're on the thread page
    await project_update_subject.click()
    thread_container = browser_client.test_id_locator("email-thread")
    await browser_client.expect(thread_container).to_be_visible()

    # Mark thread as archived via the React action bar
    archive_button = thread_container.locator("button[aria-label='Archive']")
    await archive_button.click()

    # Validate we're back on the inbox page without the archived thread
    await browser_client.page.wait_for_url("**/", wait_until="domcontentloaded")
    await browser_client.expect(project_update_subject).not_to_be_visible()
    await browser_client.expect(meeting_subject).to_be_visible()
    await browser_client.expect(budget_subject).to_be_visible()


@pytest.mark.asyncio
async def test_marking_thread_read_unread(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    meeting_message = await create_email_message(
        external_thread_id="thread-1",
        subject="Meeting Request",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="Can we schedule a meeting?",
        body_html="<p>Can we schedule a meeting?</p>",
        labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await meeting_message.fetch_related("thread")
    meeting = meeting_message.thread

    await Mailbox.sync(meeting)
    meeting_entry = await MailboxEntry.get(owner_id=bob.id, resource_gid=meeting.global_id)

    await browser_client.login("bob@example.com")

    meeting_subject = browser_client.page.locator('text="Meeting Request"')
    await browser_client.expect(meeting_subject).to_be_visible()

    # Open the thread show page and mark as read from the React action bar
    await meeting_subject.click()
    thread_container = browser_client.test_id_locator("email-thread")
    await browser_client.expect(thread_container).to_be_visible()
    mark_read_button = thread_container.locator("button[aria-label='Mark read']")
    await browser_client.expect(mark_read_button).to_be_visible()
    await mark_read_button.click()

    # Wait for the mark-read POST to settle before navigating back, otherwise
    # the click could race the in-flight request.
    await browser_client.page.wait_for_load_state("networkidle")

    # Navigate back to the React inbox via the action bar back link
    back_button = browser_client.test_id_locator("back-button")
    await back_button.click()

    await browser_client.page.wait_for_url("**/", wait_until="domcontentloaded")
    # React rows are keyed by MailboxEntry id, not the underlying resource id.
    meeting_row = browser_client.test_id_locator(f"mailbox-entry-{meeting_entry.id}")
    await browser_client.expect(meeting_row).to_have_attribute("data-is-unread", "false")

    # Mark unread from the hover bar in the React island
    await meeting_row.hover()
    mark_unread_button = meeting_row.locator("button[data-action='mark-unread']")
    await browser_client.expect(mark_unread_button).to_be_visible()
    await mark_unread_button.click()

    await browser_client.expect(meeting_row).to_have_attribute("data-is-unread", "true")


@pytest.mark.asyncio
async def test_archiving_surfaces_hover_actions_on_next_row(browser_client: BrowserClient):
    # #8878: archiving a row from the inbox left the next row (which slides up
    # under the stationary cursor) with no visible hover buttons, because the
    # browser re-fires neither :hover nor mouseenter for a pointer that didn't
    # move. Archive the top row without moving the mouse afterward and assert the
    # row now under the cursor reveals its actions.
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    for index in range(1, 3):
        message = await create_email_message(
            external_thread_id=f"thread-{index}",
            subject=f"Thread {index}",
            sender="Alice <alice@example.com>",
            to=[bob.email],
            body_plain=f"Body {index}",
            body_html=f"<p>Body {index}</p>",
            labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
            organization_id=bob.organization_id,
            creator_id=bob.id,
        )
        await message.fetch_related("thread")
        await Mailbox.sync(message.thread)

    await browser_client.login("bob@example.com")

    rows = browser_client.page.locator("[data-thread-id]")
    await browser_client.expect(rows).to_have_count(2)

    # Pin both rows to concrete ids so the locators don't re-resolve to a
    # different (remounting) row once the list reflows after the archive.
    top_row_id = await rows.first.get_attribute("data-thread-id")
    next_row_id = await rows.nth(1).get_attribute("data-thread-id")

    # Park the real cursor over the middle of the top row and keep it there.
    top_row = browser_client.page.locator(f'[data-thread-id="{top_row_id}"]')
    top_box = await top_row.bounding_box()
    assert top_box is not None
    cursor_x = top_box["x"] + top_box["width"] / 2
    cursor_y = top_box["y"] + top_box["height"] / 2
    await browser_client.page.mouse.move(cursor_x, cursor_y)

    top_archive = top_row.locator("button[data-action='archive']")
    await browser_client.expect(top_archive).to_be_visible()
    # Archive via a synthetic click so the cursor never moves — reproducing the
    # exact bug condition (a stationary pointer while the list reflows beneath it).
    await top_archive.dispatch_event("click")

    # No hover/move here on purpose — the second row has slid up under the
    # motionless cursor and must reveal its own actions.
    next_row = browser_client.page.locator(f'[data-thread-id="{next_row_id}"]')
    next_archive = next_row.locator("button[data-action='archive']")
    await browser_client.expect(next_archive).to_be_visible()


@pytest.mark.asyncio
async def test_email_body_nested_ordered_list_marker_styles(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    message = await create_email_message(
        external_thread_id="thread-1",
        subject="Nested List",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="one two three four",
        body_html=NESTED_OL_BODY_HTML,
        labels=[EmailLabel.INBOX],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await message.fetch_related("thread")
    thread = message.thread

    await Mailbox.sync(thread)

    await browser_client.login("bob@example.com")

    subject = browser_client.page.locator('text="Nested List"')
    await browser_client.expect(subject).to_be_visible()
    await subject.click()

    thread_container = browser_client.test_id_locator("email-thread")
    await browser_client.expect(thread_container).to_be_visible()

    # The EmailMessageBody iframe is created imperatively with no id/name/title;
    # it is the single <iframe> inside the email-body container div.
    body_container = thread_container.locator("div.bg-base-50").first
    iframe_element = body_container.locator("iframe").first
    await browser_client.expect(iframe_element).to_be_attached()
    # The body auto-sizes on load; wait for it before reading computed styles.
    await iframe_element.evaluate(
        """el => new Promise(resolve => {
            if (el.contentDocument && el.contentDocument.readyState === "complete") resolve()
            else el.addEventListener("load", () => resolve(), { once: true })
        })"""
    )

    frame = iframe_element.content_frame

    # Locate levels structurally by ol-descent depth, not by marker text.
    level_1 = frame.locator("body > ol").first
    level_2 = frame.locator("ol ol").first
    level_3 = frame.locator("ol ol ol").first
    level_4 = frame.locator("ol ol ol ol").first
    await browser_client.expect(level_4).to_be_attached()

    async def list_style_type(locator) -> str:
        return await locator.evaluate("el => getComputedStyle(el).listStyleType")

    assert await list_style_type(level_1) == "decimal"
    assert await list_style_type(level_2) == "lower-alpha"
    assert await list_style_type(level_3) == "lower-roman"
    assert await list_style_type(level_4) == "lower-roman"
