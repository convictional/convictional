import asyncio
from uuid import UUID

import pytest

from app.models.collaboration.mailbox import MailboxEntry
from app.models.collaboration.workspace import SubscriptionPreference
from app.models.workspaces.posts import Post
from config.enums import Integration, SubscriptionLevel
from infra.db import GlobalID
from tests.helpers.browser import BrowserClient
from tests.helpers.factories import create_collaborator, create_post, create_user


async def _poll_entry(owner_id: UUID, resource_gid: GlobalID, *, unread: bool, timeout: float = 10.0) -> MailboxEntry:
    """Poll the shared test DB until the owner's entry reaches the desired unread
    state. The SyncMailboxJob (unread side) and the client's mark_read (read side)
    both run asynchronously in the server process, so we wait for the end state
    rather than assume an ordering."""
    deadline = asyncio.get_event_loop().time() + timeout
    entry = None
    while asyncio.get_event_loop().time() < deadline:
        entry = await MailboxEntry.get_or_none(owner_id=owner_id, resource_gid=resource_gid)
        if entry is not None and entry.is_unread == unread:
            return entry
        await asyncio.sleep(0.25)
    raise AssertionError(f"MailboxEntry for {owner_id} never reached is_unread={unread} (last: {entry!r})")


# Two browser sessions plus polling for the async SyncMailboxJob to settle push
# this past the default 15s budget.
@pytest.mark.timeout(90)
@pytest.mark.asyncio
async def test_post_marked_read_on_live_comment(browser_client: BrowserClient):
    # Regression (#8816): a post open while a live comment arrives must not be
    # left unread in the inbox. The server re-applies UNREAD on every incoming
    # comment, so the open post island must re-clear it via mark_read.
    alice = await create_user(
        email="alice@example.com", integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR]
    )
    bob = await create_user(
        email="bob@example.com",
        organization_id=alice.organization_id,
        integrations=[Integration.GMAIL, Integration.RECALL_AI_CALENDAR],
    )
    post = await create_post(creator_id=bob.id, organization_id=alice.organization_id, title="Lunch plans")
    await post.fetch_related("workspace")
    # Alice is a collaborating ALL-subscriber, so comments by others land in her
    # inbox as unread through the real POST_COMMENTED → SyncMailboxJob path.
    await create_collaborator(workspace_id=post.workspace_id, user_id=alice.id)
    await SubscriptionPreference.update_for(alice.id, {Post.record_type: SubscriptionLevel.ALL})

    alice_browser = await browser_client.new_context()
    await alice_browser.login("alice@example.com")
    bob_browser = await browser_client.new_context()
    await bob_browser.login("bob@example.com")

    # Bob's first comment puts the post in Alice's inbox as unread.
    await bob_browser.page.goto(f"{bob_browser.base_url}/posts/{post.id}")
    bob_editor = bob_browser.page.locator('#post .ProseMirror[contenteditable="true"]').first
    await bob_browser.expect(bob_editor).to_be_visible()
    await bob_editor.click()
    await bob_editor.type("Kicking off the discussion.")
    # The post-show composer's submit is a text button reading "Comment" (no aria-label);
    # it only renders once the editor is focused, which the click above satisfies.
    await bob_browser.page.locator("#post").get_by_role("button", name="Comment", exact=True).click()
    await bob_browser.expect(bob_browser.page.get_by_text("Kicking off the discussion.")).to_be_visible()

    entry = await _poll_entry(alice.id, post.global_id, unread=True)

    # Alice opens the post the way the inbox links to it — with mailbox_entry_id in
    # the URL, so the show endpoint resolves her entry and the header renders the
    # MailboxActionBar whose auto-mark-read clears the unread label.
    await alice_browser.page.goto(f"{alice_browser.base_url}/posts/{post.id}?mailbox_entry_id={entry.id}")
    await alice_browser.expect(alice_browser.page.get_by_text("Kicking off the discussion.")).to_be_visible()
    await _poll_entry(alice.id, post.global_id, unread=False)

    # Bob comments while Alice has the post open. The on-open auto-mark-read already
    # settled above, so the only mark_read after this point is the one the live comment
    # triggers — assert the island re-issues it and the entry stays read.
    mark_read_path = f"/api/mailbox_entries/{entry.id}/mark_read"

    def is_live_mark_read(request) -> bool:
        return request.method == "POST" and mark_read_path in request.url

    async with alice_browser.page.expect_request(is_live_mark_read):
        await bob_editor.click()
        await bob_editor.type("One more thought.")
        await bob_browser.page.locator("#post").get_by_role("button", name="Comment", exact=True).click()
        await alice_browser.expect(alice_browser.page.get_by_text("One more thought.")).to_be_visible()

    # The persisted end state must settle read, not just the request having fired.
    await _poll_entry(alice.id, post.global_id, unread=False)
