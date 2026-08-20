import pytest

from tests.helpers.browser import BrowserClient

# End-to-end onboarding landings: these exercise the routing + island mount + real
# signals that the component tests mock away (the class of wiring bug that shows an
# empty inbox or a stale prompt instead of the first-run surface).


@pytest.mark.asyncio
async def test_new_user_lands_on_getting_started_focus(browser_client: BrowserClient):
    # A brand-new user (fresh org, nothing connected) lands on the client-rendered
    # "Getting started" focus with its connect rows, not a bare empty inbox.
    await browser_client.login("founder@onboarding-focus.example.com")
    page = browser_client.page
    await browser_client.expect(page.get_by_text("Create your profile")).to_be_visible()
    await browser_client.expect(page.get_by_text("Connect your email")).to_be_visible()
    await browser_client.expect(page.get_by_text("Connect your calendar")).to_be_visible()


@pytest.mark.asyncio
async def test_empty_chats_shows_first_run(browser_client: BrowserClient):
    # No groups yet (new orgs seed none) → the chat first-run surface.
    await browser_client.login("founder@onboarding-chats.example.com")
    page = browser_client.page
    await page.goto(f"{browser_client.base_url}/chats", wait_until="domcontentloaded")
    await browser_client.expect(page.get_by_text("Get your team started")).to_be_visible()


@pytest.mark.asyncio
async def test_empty_posts_shows_first_run_composer(browser_client: BrowserClient):
    # No posts yet → the first-run composer (its title field is present regardless
    # of the admin/non-admin builder branch).
    await browser_client.login("founder@onboarding-posts.example.com")
    page = browser_client.page
    await page.goto(f"{browser_client.base_url}/posts", wait_until="domcontentloaded")
    await browser_client.expect(page.get_by_label("Post title")).to_be_visible()
