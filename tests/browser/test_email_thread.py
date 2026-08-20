import asyncio
import io
import time
from datetime import UTC, datetime, timedelta

import pytest

from app.models.collaboration.mailbox import Mailbox, MailboxEntry
from app.models.workspaces.email.thread import EmailAttachment
from config.enums import EmailLabel, Integration
from infra.storage import store_file
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_email_message, create_user

# A subresource on this host is intercepted and left hanging (never fulfilled),
# standing in for the real HubSpot tracking pixel that pinned the iframe at 60px
# until the browser abandoned it ~30s later.
HANGING_HOST = "https://tracking.example.com"

# Enough paragraphs that the parsed body is clearly taller than the 60px
# placeholder without relying on the hanging image having any layout size.
_TALL_PARAGRAPHS = "".join(f"<p>Line {i} of the email body.</p>" for i in range(40))

HANGING_IMAGE_BODY_HTML = f'<img src="{HANGING_HOST}/pixel.gif">{_TALL_PARAGRAPHS}'
FAST_PATH_BODY_HTML = _TALL_PARAGRAPHS

# The iframe starts at 60px and sizes to content once the body parses. A grown
# height well above the placeholder proves it sized on parse.
MIN_SIZED_HEIGHT = 200
# Well under the old ~30s+ window the hanging subresource used to impose.
BOUNDED_WAIT_SECONDS = 6


async def _open_thread_and_measure_body_height(browser_client: BrowserClient, subject: str) -> float:
    subject_locator = browser_client.page.locator(f'text="{subject}"')
    await browser_client.expect(subject_locator).to_be_visible()
    await subject_locator.click()

    thread_container = browser_client.test_id_locator("email-thread")
    await browser_client.expect(thread_container).to_be_visible()

    # The EmailMessageBody iframe is created imperatively with no id/name/title;
    # it is the single <iframe> inside the email-body container div.
    body_container = thread_container.locator('[data-testid="email-message-body"]').first
    iframe_element = body_container.locator("iframe").first
    await browser_client.expect(iframe_element).to_be_attached()

    # Poll the rendered height directly rather than waiting on load/networkidle:
    # with a hanging subresource those never settle, and the whole point is that
    # sizing no longer depends on them.
    deadline = time.monotonic() + BOUNDED_WAIT_SECONDS
    height = 0.0
    while time.monotonic() < deadline:
        height = await iframe_element.evaluate("el => el.getBoundingClientRect().height")
        if height >= MIN_SIZED_HEIGHT:
            return height
        await asyncio.sleep(0.1)
    return height


@pytest.mark.asyncio
async def test_email_body_sizes_on_parse_despite_hanging_subresource(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    message = await create_email_message(
        external_thread_id="thread-hanging",
        subject="Hanging Subresource",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="body",
        body_html=HANGING_IMAGE_BODY_HTML,
        labels=[EmailLabel.INBOX],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await message.fetch_related("thread")
    await Mailbox.sync(message.thread)

    # Never fulfill/continue/abort — the request stays pending, so the iframe's
    # `load` event never fires within the test window. A redirect loop would fail
    # fast (ERR_TOO_MANY_REDIRECTS) and let `load` fire, so the test would pass
    # even against the old buggy code; hanging is what actually reproduces the bug.
    async def hang(route):
        await asyncio.sleep(BOUNDED_WAIT_SECONDS * 10)

    await browser_client.page.route(f"{HANGING_HOST}/**", hang)

    await browser_client.login("bob@example.com")

    height = await _open_thread_and_measure_body_height(browser_client, "Hanging Subresource")
    assert height >= MIN_SIZED_HEIGHT, (
        f"iframe stayed collapsed at {height}px while a subresource hung; "
        "it should size to content on parse, not on load"
    )


@pytest.mark.asyncio
async def test_email_body_sizes_on_parse_fast_path(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    message = await create_email_message(
        external_thread_id="thread-fast",
        subject="Fast Path",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="body",
        body_html=FAST_PATH_BODY_HTML,
        labels=[EmailLabel.INBOX],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await message.fetch_related("thread")
    await Mailbox.sync(message.thread)

    await browser_client.login("bob@example.com")

    height = await _open_thread_and_measure_body_height(browser_client, "Fast Path")
    assert height >= MIN_SIZED_HEIGHT, f"iframe did not reach content height on the normal fast path ({height}px)"


@pytest.mark.asyncio
async def test_read_history_collapses_and_keeps_subject_in_view(browser_client: BrowserClient):
    # A long, fully-read thread must load with its subject in view: the read history
    # compacts into the Gmail-style collapsed group instead of auto-scrolling down to
    # the newest message (#8838). This is the regression people would notice first, so
    # it earns a browser test even though the compaction logic is unit-tested.
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])

    base = datetime.now(UTC) - timedelta(hours=12)
    messages = []
    for index in range(6):
        # One external_thread_id keeps all six messages on a single thread, oldest first.
        is_last = index == 5
        messages.append(
            await create_email_message(
                external_thread_id="thread-read-collapse",
                subject="Q3 Launch Logistics",
                sender="Alice <alice@example.com>",
                to=[bob.email],
                # The newest (expanded) message gets a tall plain-text body — plain text
                # renders synchronously (no iframe), so the thread reliably overflows the
                # short viewport below and a regressed auto-scroll would move the subject
                # out of view. Older messages stay collapsed, so their bodies never render.
                body_plain=("The newest message body line.\n" * 60) if is_last else f"Message {index} body.",
                body_html="" if is_last else f"<p>Message {index} body.</p>",
                received_at=base + timedelta(minutes=index),
                labels=[EmailLabel.INBOX],
                organization_id=bob.organization_id,
                creator_id=bob.id,
            )
        )
    await messages[-1].fetch_related("thread")
    thread = messages[-1].thread
    await Mailbox.sync(thread)

    # Mark the whole thread read so it loads as fully-read history: only the newest
    # message stays expanded and the five before it compact behind the count bar.
    entry = await MailboxEntry.get(owner_id=bob.id, resource_gid=thread.global_id)
    await entry.mark_as_read()

    # A short viewport guarantees the expanded newest message overflows it, so a
    # regressed scroll-to-newest would visibly push the subject off screen.
    await browser_client.page.set_viewport_size({"width": 900, "height": 600})
    await browser_client.login("bob@example.com")

    subject_row = browser_client.page.locator('text="Q3 Launch Logistics"').first
    await browser_client.expect(subject_row).to_be_visible()
    await subject_row.click()

    thread_container = browser_client.test_id_locator("email-thread")
    await browser_client.expect(thread_container).to_be_visible()

    # The read run compacted: the count bar renders and sits at the top, in view.
    bar = browser_client.test_id_locator("collapsed-group-bar")
    await browser_client.expect(bar).to_be_visible()
    await browser_client.expect(bar).to_contain_text("emails")
    await browser_client.expect(bar).to_be_in_viewport()

    # The subject stayed visible — the scroll-to-newest jump was suppressed.
    title = thread_container.locator("h1", has_text="Q3 Launch Logistics")
    await browser_client.expect(title).to_be_in_viewport()


@pytest.mark.asyncio
async def test_email_attachment_long_name_does_not_overflow_on_mobile(browser_client: BrowserClient):
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])

    # A long filename with no spaces to break on, so it overflows unless truncated.
    long_filename = ("Q3_Financial_Report_" * 8) + "final.pdf"
    file_ref = await store_file(content=io.BytesIO(b"data"), filename=long_filename, content_type="application/pdf")

    message = await create_email_message(
        external_thread_id="thread-attachment-overflow",
        subject="Attachment Overflow",
        sender="Alice <alice@example.com>",
        to=[bob.email],
        body_plain="See attached.",
        body_html="<p>See attached.</p>",
        labels=[EmailLabel.INBOX],
        organization_id=bob.organization_id,
        creator_id=bob.id,
    )
    await EmailAttachment.create(
        email_message_id=message.id,
        thread_id=message.thread_id,
        file=file_ref,
        is_inline=False,
    )
    await message.fetch_related("thread")
    await Mailbox.sync(message.thread)

    # Mobile viewport must be set before opening the thread so the attachment row lays out narrow.
    await browser_client.page.set_viewport_size({"width": 375, "height": 800})

    await browser_client.login("bob@example.com")

    subject_locator = browser_client.page.locator('text="Attachment Overflow"')
    await browser_client.expect(subject_locator).to_be_visible()
    await subject_locator.click()

    thread_container = browser_client.test_id_locator("email-thread")
    await browser_client.expect(thread_container).to_be_visible()

    attachment = browser_client.test_id_locator("email-attachment").first
    await browser_client.expect(attachment).to_be_visible()

    # +1 absorbs sub-pixel rounding between scrollWidth and clientWidth.
    scroll_width, client_width = await attachment.evaluate("el => [el.scrollWidth, el.clientWidth]")
    assert scroll_width <= client_width + 1, (
        f"attachment row overflows horizontally: scrollWidth={scroll_width} > clientWidth={client_width}"
    )

    # Truncation is visual only — the full filename remains in the DOM.
    await browser_client.expect(attachment).to_contain_text(long_filename)
