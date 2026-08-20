import pytest

from app.models.collaboration.mailbox import Mailbox
from config.enums import EmailLabel, Integration
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_document, create_email_message, create_user

# Reads the live geometry of the reveal nav and the sticky header in one shot.
# --nav-reveal-offset is the contract useRevealNavOnScroll publishes: the nav's
# visible height when shown, "0px" when hidden.
SNAPSHOT_JS = """
() => {
  const nav = document.querySelector('[data-nav-sticky-wrapper]');
  const card = document.querySelector('.sticky-header-card');
  const spacer = document.querySelector('.sticky-header-spacer');
  const cardRect = card.getBoundingClientRect();
  const spacerRect = spacer.getBoundingClientRect();
  const wrapper = document.querySelector('.page-content');
  return {
    navBottom: nav.getBoundingClientRect().bottom,
    offset: getComputedStyle(document.documentElement).getPropertyValue('--nav-reveal-offset').trim(),
    cardTop: cardRect.top,
    spacerTop: spacerRect.top,
    spacerBottom: spacerRect.bottom,
    spacerHeight: spacerRect.height,
    wrapperPadTop: wrapper ? getComputedStyle(wrapper).paddingTop : null,
  };
}
"""


async def _scroll_to(client: BrowserClient, y: int) -> None:
    await client.page.evaluate(f"window.scrollTo(0, {y})")
    # Let the scroll handler's rAF and the top-transition settle.
    await client.page.wait_for_timeout(200)


async def _assert_reveal_and_sticky(client: BrowserClient, context: str) -> None:
    page = client.page
    # The reveal controller lives in the React nav island; the inline `top` it writes
    # on acquire is the proof it has bound to this page's wrapper and published an
    # offset to assert on.
    await client.expect(page.locator(".sticky-header-card")).to_be_visible()
    await page.wait_for_function(
        "() => { const el = document.querySelector('[data-nav-sticky-wrapper]');"
        " return el !== null && el.style.top !== ''; }"
    )

    # At rest: nav shown, and the card sits below it with the spacer strip between.
    await _scroll_to(client, 0)
    rest = await page.evaluate(SNAPSHOT_JS)
    assert rest["offset"] != "0px", f"{context}: nav should be shown at rest, offset={rest['offset']}"
    assert rest["spacerHeight"] >= 16, f"{context}: spacer strip missing at rest ({rest['spacerHeight']}px)"
    assert rest["cardTop"] >= rest["navBottom"] - 1, f"{context}: card should sit below the nav at rest"
    # Sticky-header pages opt out of the content wrapper's top gap (.page-content
    # :has(.sticky-header) in main.css) — the spacer provides it instead, so the
    # wrapper padding must be zero to avoid a double gap.
    assert rest["wrapperPadTop"] == "0px", (
        f"{context}: sticky page should zero the wrapper top gap, got {rest['wrapperPadTop']}"
    )

    # Scroll down far enough to fully hide the nav. Two steps per attempt: the first
    # primes the scroll-direction baseline, the second registers as a downward move.
    # The gesture is retried because the controller resets that baseline every time it
    # re-acquires the wrapper (htmx:afterSettle), which swallows the next sample as a
    # fresh prime. A real drag fires dozens of scroll events and loses one
    # imperceptibly; scrollTo fires exactly one, so a reset costs the whole gesture.
    down = await page.evaluate(SNAPSHOT_JS)
    for _ in range(4):
        if down["offset"] == "0px":
            break
        await _scroll_to(client, 150)
        await _scroll_to(client, 800)
        down = await page.evaluate(SNAPSHOT_JS)
    assert down["offset"] == "0px", f"{context}: nav should hide on scroll down, offset={down['offset']}"
    # With the nav hidden the card must NOT be flush against the viewport top: the
    # bg-base-100 spacer strip stays on-screen above it so scrolling content never
    # shows through.
    assert down["cardTop"] >= 12, f"{context}: sticky card is flush against the viewport top ({down['cardTop']}px)"
    assert down["spacerTop"] <= 2, f"{context}: spacer strip pushed off the top ({down['spacerTop']}px)"
    assert down["spacerBottom"] >= 12, f"{context}: spacer strip not visible above the pinned card"

    # Scroll up (relative to wherever we actually landed — scrollTo past the max
    # is clamped, so an absolute target could be a no-op): the nav quick-reveals.
    current_y = await page.evaluate("window.scrollY")
    await _scroll_to(client, max(0, int(current_y) - 120))
    up = await page.evaluate(SNAPSHOT_JS)
    assert up["offset"] != "0px", f"{context}: nav should reveal on scroll up, offset={up['offset']}"


@pytest.mark.asyncio
async def test_reveal_nav_and_sticky_header_across_layouts(browser_client: BrowserClient):
    """The quick-reveal nav hides on scroll-down / reveals on scroll-up, and the
    sticky header keeps its spacer strip (never flush) in every scroll state.
    Covers the three chrome contexts that render the same header markup
    differently: a block-flow Jinja page (inbox), a flex-wrapped Jinja show page
    (email thread), and the TanStack Router SPA shell (documents index) — the
    stack we're migrating to."""
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])

    # Enough documents that the SPA-shell index scrolls under a short viewport.
    for i in range(15):
        await create_document(
            title=f"Document {i}",
            organization_id=bob.organization_id,
            creator_id=bob.id,
        )

    # Enough inbox threads that the list scrolls under a short viewport.
    for i in range(12):
        message = await create_email_message(
            external_thread_id=f"thread-{i}",
            subject=f"Subject {i}",
            sender="Alice <alice@example.com>",
            to=[bob.email],
            body_plain="Body",
            body_html="<p>Body</p>",
            labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
            organization_id=bob.organization_id,
            creator_id=bob.id,
        )
        await message.fetch_related("thread")
        await Mailbox.sync(message.thread)

    # A single thread with many messages so its show page (flex layout) scrolls.
    long_thread = None
    for i in range(8):
        message = await create_email_message(
            external_thread_id="long-thread",
            subject="Long Thread",
            sender="Alice <alice@example.com>",
            to=[bob.email],
            body_plain=f"Message {i}. " + ("Lorem ipsum dolor sit amet. " * 12),
            body_html=f"<p>Message {i}. {'Lorem ipsum dolor sit amet. ' * 12}</p>",
            labels=[EmailLabel.INBOX, EmailLabel.UNREAD],
            organization_id=bob.organization_id,
            creator_id=bob.id,
        )
        await message.fetch_related("thread")
        long_thread = message.thread
    assert long_thread is not None
    await Mailbox.sync(long_thread)

    # Short viewport so modest content is enough to scroll. Desktop UA (default)
    # keeps the reveal nav active — it's desktop-only.
    await browser_client.page.set_viewport_size({"width": 1200, "height": 520})

    await browser_client.login("bob@example.com")

    # Block-flow context: the inbox list.
    await _assert_reveal_and_sticky(browser_client, context="inbox (block-flow)")

    # Flex context: the email thread show page wraps its header in `flex flex-col`.
    await browser_client.page.locator('text="Long Thread"').click()
    await browser_client.expect(browser_client.test_id_locator("email-thread")).to_be_visible()
    await _assert_reveal_and_sticky(browser_client, context="email thread (flex)")

    # SPA-shell context: the documents index renders through the TanStack Router
    # shell (AppShell), whose content wrapper is the mirror of the Jinja one.
    await browser_client.page.goto(f"{browser_client.base_url}/documents")
    await _assert_reveal_and_sticky(browser_client, context="documents index (SPA shell)")
