import pytest

from app.models.collaboration.content import IndexMetadata, SearchableData
from app.models.workspaces.goals import GoalAlignment
from config.enums import ContentCategory, ContentType, Integration, Sharing, SignalStrength
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_content, create_goal, create_user


@pytest.mark.asyncio
async def test_goal_alignments_react_flow(browser_client: BrowserClient):
    user = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    goal = await create_goal(organization_id=user.organization_id, creator_id=user.id, title="Revenue Growth")
    org = await goal.organization

    # An existing manual alignment so a card renders. Created with a creator so it
    # is not a job-created alignment, which would establish a scoring cutoff and
    # could exclude the searchable content below from the add form.
    aligned = await create_content(organization_id=user.organization_id, title="Q1 Sales Report")
    await GoalAlignment.create(
        goal=goal,
        content=aligned,
        content_indexed_at=aligned.last_indexed_at,
        organization=org,
        signal=SignalStrength.STRONG,
        alignment_score=0.9,
        description="Already aligned",
        created_by_id=user.id,
    )

    # Indexed, searchable content the add form can find. Indexing with empty index_content
    # syncs the lookup tsvector (which matches on title) without generating OpenAI embeddings.
    searchable = await create_content(organization=org, title="Quarterly Sales Review", content_type=ContentType.POST)
    await searchable.indexer.index(
        SearchableData("Quarterly Sales Review", "", "https://example.com/sales", "Jane Doe"),
        IndexMetadata(ContentCategory.DOCUMENT, ContentType.POST, Sharing.ORGANIZATION),
    )

    await browser_client.login("alice@example.com")
    page = browser_client.page

    # Index page: the circle-pack island mounts (D3 injects an <svg>) and the goal card renders.
    await page.goto(f"{browser_client.base_url}/goal_alignments")
    index_root = page.locator("#react-goal-alignments-index")
    await browser_client.expect(index_root.locator("svg")).to_be_visible()
    goal_link = index_root.get_by_role("link", name="Revenue Growth")
    await browser_client.expect(goal_link).to_be_visible()

    # Navigate index -> show by clicking the goal card.
    await goal_link.click()
    await page.wait_for_url(f"**/goals/{goal.id}/alignments")

    # Show page: the timeline island mounts and the existing alignment card renders.
    show_root = page.locator("#react-goal-alignments-show")
    await browser_client.expect(show_root.locator("svg")).to_be_visible()
    await browser_client.expect(show_root.get_by_role("link", name="Q1 Sales Report")).to_be_visible()

    # Pin the existing alignment; the pinned state persists across a reload.
    await page.get_by_role("button", name="Pin", exact=True).click()
    await browser_client.expect(page.get_by_role("button", name="Unpin", exact=True)).to_be_visible()
    await page.reload()
    await browser_client.expect(page.get_by_role("button", name="Unpin", exact=True)).to_be_visible()

    # Add a new alignment via the search form.
    await page.get_by_role("button", name="Add aligned content").click()
    await page.get_by_placeholder("Search for a post or meeting...").fill("Sales Review")
    result = page.get_by_text("Quarterly Sales Review")
    await browser_client.expect(result).to_be_visible()
    await result.click()
    await page.get_by_placeholder("Let us know how this content aligns with the goal").fill("Manually added")
    await page.get_by_role("button", name="Save").click()
    new_card_link = show_root.get_by_role("link", name="Quarterly Sales Review")
    await browser_client.expect(new_card_link).to_be_visible()

    # Delete the new alignment via the confirmation dialog; the card is removed.
    new_card = show_root.locator(".card").filter(has_text="Quarterly Sales Review")
    await new_card.get_by_role("button", name="Remove", exact=True).click()
    await browser_client.test_id_locator("confirmation-dialog-confirm").click()
    await browser_client.expect(new_card_link).not_to_be_visible()
