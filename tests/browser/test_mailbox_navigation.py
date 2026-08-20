import pytest

from app.models.collaboration.mailbox import Mailbox
from config.enums import EmailLabel, Integration
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_email_message, create_user


async def _thread(bob, index: int):
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
    return message.thread


@pytest.mark.asyncio
async def test_prev_next_arrows_walk_the_inbox(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    for index in range(1, 4):
        await _thread(bob, index)

    await browser_client.login("bob@example.com")
    page = browser_client.page

    # data-thread-id is the MailboxEntry id, which the show URL carries as
    # ?mailbox_entry_id= — match on that rather than the /email_threads/<id> path.
    rows = page.locator("[data-thread-id]")
    await browser_client.expect(rows).to_have_count(3)
    first_id = await rows.first.get_attribute("data-thread-id")
    second_id = await rows.nth(1).get_attribute("data-thread-id")

    # Open the top entry from the inbox: its href carries return_to=/, so the
    # arrows appear. The first entry has no previous neighbor.
    await page.locator(f'[data-thread-id="{first_id}"]').click()
    await page.wait_for_url(f"**mailbox_entry_id={first_id}**", wait_until="domcontentloaded")
    prev_button = page.locator("button[aria-label='Previous']")
    next_button = page.locator("button[aria-label='Next']")
    await browser_client.expect(next_button).to_be_enabled()
    await browser_client.expect(prev_button).to_be_disabled()

    # Arrow to the next entry; the previous arrow is now live.
    await next_button.click()
    await page.wait_for_url(f"**mailbox_entry_id={second_id}**", wait_until="domcontentloaded")
    await browser_client.expect(page.locator("button[aria-label='Previous']")).to_be_enabled()

    # Arrow back to the entry we started on.
    await page.locator("button[aria-label='Previous']").click()
    await page.wait_for_url(f"**mailbox_entry_id={first_id}**", wait_until="domcontentloaded")


@pytest.mark.asyncio
async def test_snooze_advances_to_the_next_entry(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    for index in range(1, 4):
        await _thread(bob, index)

    await browser_client.login("bob@example.com")
    page = browser_client.page

    rows = page.locator("[data-thread-id]")
    await browser_client.expect(rows).to_have_count(3)
    first_id = await rows.first.get_attribute("data-thread-id")
    second_id = await rows.nth(1).get_attribute("data-thread-id")

    # Open the top entry, then snooze it: like archive, snooze advances to the next
    # entry (the one the next arrow points at), not back to the inbox.
    await page.locator(f'[data-thread-id="{first_id}"]').click()
    await page.wait_for_url(f"**mailbox_entry_id={first_id}**", wait_until="domcontentloaded")
    await page.locator("button[aria-label='Snooze']").click()
    await page.get_by_role("menuitem", name="Two hours from now").click()
    await page.wait_for_url(f"**mailbox_entry_id={second_id}**", wait_until="domcontentloaded")


@pytest.mark.asyncio
async def test_no_arrows_without_a_mailbox_return_to(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    thread = await _thread(bob, 1)

    await browser_client.login("bob@example.com")
    page = browser_client.page

    # Reach the entry directly (a shared link / notification) — no mailbox
    # return_to, so the navigation arrows must not render.
    await page.goto(f"{browser_client.base_url}/email_threads/{thread.id}", wait_until="domcontentloaded")
    await browser_client.expect(browser_client.test_id_locator("email-thread")).to_be_visible()
    await browser_client.expect(page.locator("button[aria-label='Next']")).to_have_count(0)
    await browser_client.expect(page.locator("button[aria-label='Previous']")).to_have_count(0)
