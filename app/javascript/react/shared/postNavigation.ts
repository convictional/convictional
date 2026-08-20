import { safeReturnTo } from "~/react/shared/returnTo"
import type { BackNavigation } from "~/react/shared/types"

// The "back" target for a post view or draft editor, replicating the old server
// logic client-side (the API request no longer carries the page URL's return_to).
// A safe return_to wins; otherwise fall back to the origin index — the inbox when
// the post was opened from a mailbox entry (mailbox_index resolves to "/"), else
// the posts index. Only the posts index gets a specific label; any other
// return_to target (e.g. another post) gets a generic "Back", mirroring
// documentBackNavigation. Shared by postShow and postDraftEditor (features can't
// import each other), matching documentBackNavigation's home in shared/.
export function postBackNavigation(returnTo: string | undefined, mailboxEntryId: string | undefined): BackNavigation {
  const safe = safeReturnTo(returnTo)
  if (safe) {
    const isPostsIndex = safe === "/posts" || safe.startsWith("/posts?")
    return { url: safe, label: isPostsIndex ? "Back to posts" : "Back" }
  }
  return mailboxEntryId ? { url: "/", label: "Back to inbox" } : { url: "/posts", label: "Back to posts" }
}

// The search params that carry a post's back + mailbox context across a client
// navigation to a sibling post route (the show⇄edit redirect pair). Write-side
// mirror of the backAndMailboxSearch validator that reads them back off the URL;
// return_to passes through the open-redirect guard first.
export function postNavigationSearch(returnTo: string | undefined, mailboxEntryId: string | undefined) {
  const safe = safeReturnTo(returnTo)
  return {
    ...(safe ? { return_to: safe } : {}),
    ...(mailboxEntryId ? { mailbox_entry_id: mailboxEntryId } : {}),
  }
}
