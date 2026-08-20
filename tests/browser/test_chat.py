import pytest

from config.enums import Integration
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_chat, create_chat_message, create_collaborator, create_user

# CHAT_MESSAGES_PER_PAGE is 50, so 120 messages span three pages. The newest 50
# (070-119) load first; scrolling to the top paginates in the next-oldest page.
MESSAGE_COUNT = 120


def message_text(index: int) -> str:
    return f"Message number {index:03d}"


@pytest.mark.asyncio
async def test_scroll_up_pagination_keeps_position(browser_client: BrowserClient):
    """Loading older messages on scroll-up must not jump the viewport.

    Document scroll anchoring is disabled (useDisableDocumentScrollAnchor), so the
    message list compensates manually when a page of older messages is prepended.
    Without that compensation, scrollY stays fixed while the prepended content
    pushes everything down, throwing the user up by a full page.
    """
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    other = await create_user(email="alice@example.com", organization_id=bob.organization_id)
    chat = await create_chat(organization_id=bob.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)

    # Sequential creation gives each message a strictly increasing created_at, so
    # cursor pagination orders them deterministically.
    for i in range(MESSAGE_COUNT):
        await create_chat_message(chat_id=chat.id, user_id=other.id, content=message_text(i))

    await browser_client.login("bob@example.com")
    await browser_client.page.goto(f"{browser_client.base_url}/chats/{chat.id}")

    # The list pins to the bottom on load: the newest message is on screen.
    await browser_client.expect(
        browser_client.page.get_by_text(message_text(MESSAGE_COUNT - 1), exact=True)
    ).to_be_visible()

    # Warm-up pagination: jumping to the top loads page two (020-069) and, on
    # desktop, slides the auto-hiding nav into view. We measure across the *next*
    # pagination so that nav reveal isn't conflated with the prepend shift.
    await browser_client.page.evaluate("window.scrollTo(0, 0)")
    await browser_client.page.get_by_text(message_text(50), exact=True).wait_for(state="attached")

    # 020 is now the oldest loaded message; track it across the page-three prepend.
    reference = browser_client.page.get_by_text(message_text(20), exact=True)

    # Back to the top to load page three (000-019). The nav is already revealed,
    # so any movement of the reference is the prepend alone. Capture its viewport
    # offset before the prepend lands (the fetch resolves asynchronously).
    await browser_client.page.evaluate("window.scrollTo(0, 0)")
    top_before = await reference.evaluate("el => el.getBoundingClientRect().top")

    # A page-three message attaching confirms the prepend happened.
    await browser_client.page.get_by_text(message_text(5), exact=True).wait_for(state="attached")

    top_after = await reference.evaluate("el => el.getBoundingClientRect().top")

    # With compensation the reference stays put; without it, it is shoved down by
    # the height of the prepended page (hundreds of pixels).
    assert abs(top_after - top_before) < 40, f"Reference message jumped on pagination: {top_before}px -> {top_after}px"


@pytest.mark.asyncio
async def test_opening_chat_from_index_is_a_soft_navigation(browser_client: BrowserClient):
    """Opening a chat from the chats index must be a boosted (soft) navigation,
    not a full-document reload. A hard navigation strands the prior JS realm: its
    in-flight fetches reject with 'Failed to fetch' and the unhandled rejection
    microtask can't drain before teardown, pinning the whole realm (~11 MB of
    duplicated code/shapes) — stacking toward an OOM across opens (#8744).
    boostedNavigate keeps one realm; we prove it by marking the window and
    asserting the marker survives the navigation (a hard reload would wipe it).
    """
    bob = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    other = await create_user(email="alice@example.com", organization_id=bob.organization_id)
    chat = await create_chat(organization_id=bob.organization_id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=bob.id)
    await create_collaborator(workspace_id=chat.workspace_id, user_id=other.id)
    await create_chat_message(chat_id=chat.id, user_id=other.id, content="Hello Bob")

    page = browser_client.page
    await browser_client.login("bob@example.com")
    await page.goto(f"{browser_client.base_url}/chats")

    chat_link = page.locator(f'a[href^="/chats/{chat.id}"]')
    await browser_client.expect(chat_link).to_be_visible()

    # Mark the current realm; a hard navigation creates a new realm and wipes it.
    await page.evaluate("() => { window.__realmMarker = 'alive' }")

    await chat_link.click()

    await browser_client.expect(page.locator("#chat-show")).to_be_visible()
    await page.wait_for_function(f"() => window.location.pathname === '/chats/{chat.id}'")

    marker = await page.evaluate("() => window.__realmMarker")
    assert marker == "alive", "opening a chat should be a boosted navigation, not a hard reload"
