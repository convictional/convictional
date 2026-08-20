import pytest

from config.enums import Integration
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_goal, create_user


@pytest.mark.asyncio
async def test_opening_goal_from_index_is_a_soft_navigation(browser_client: BrowserClient):
    """Opening a goal from the goals index must be a client-side (soft) navigation,
    not a full-document reload. A hard navigation strands the prior JS realm (its
    in-flight fetches reject with 'Failed to fetch' and pin the realm via a stuck
    microtask), stacking toward an OOM across opens (#8744). Both paths are SPA
    routes and the row renders a typed <Link>, so the shell keeps one realm; we
    prove it by marking the window and asserting the marker survives the
    navigation (a hard reload would wipe it).
    """
    user = await create_user(email="bob@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR])
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, title="Revenue Growth")

    page = browser_client.page
    await browser_client.login("bob@example.com")
    await page.goto(f"{browser_client.base_url}/goals")

    goal_link = page.locator(f'a[href="/goals/{goal.id}"]').first
    await browser_client.expect(goal_link).to_be_visible()

    # Mark the current realm; a hard navigation creates a new realm and wipes it.
    await page.evaluate("() => { window.__realmMarker = 'alive' }")

    await goal_link.click()

    await page.wait_for_function(f"() => window.location.pathname === '/goals/{goal.id}'")

    marker = await page.evaluate("() => window.__realmMarker")
    assert marker == "alive", "opening a goal should be a boosted navigation, not a hard reload"
