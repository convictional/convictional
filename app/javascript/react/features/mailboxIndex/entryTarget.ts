import { withReturnTo } from "~/react/shared/returnTo"
import { splitHref } from "~/react/shared/urls"

// TanStack matches `to` against route paths and won't parse a query baked into
// it, so an entry href's params (the API's mailbox_entry_id, plus the return_to
// we stamp) have to travel separately.
export interface EntryTarget {
  to: string
  search: Record<string, string>
}

// Entry show pages (post, email, chat, goal) derive their "back" link from a
// `return_to` query param, resolved server-side by back_navigation() in
// app/helpers/url.py. The API builds entry hrefs without it, so opening an
// entry from the inbox would drop the current view and the back button would
// fall back to the posts index. Stamp the current inbox URL onto the href so
// back-navigation returns to the exact view the user came from.
//
// Null for the "#" the API emits when an entry has no destination (e.g. a goal
// update whose goal is gone — see api/mailbox_entries.py): there's nowhere to
// navigate, so callers leave those rows as dead links.
export function entryTargetWithReturnTo(href: string): EntryTarget | null {
  if (href === "#") return null
  // Entry hrefs carry no hash (the return_to value is percent-encoded), so
  // splitHref's pathname/search split is all we need here.
  const { pathname, search } = splitHref(withReturnTo(href))
  return { to: pathname, search }
}
