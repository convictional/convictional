import { backNavigation } from "~/react/shared/backNavigation"
import type { BackNavigation } from "~/react/shared/types"

// The "back" target for an email thread, replicating the server's
// back_navigation() client-side (the API request no longer carries the page
// URL's return_to). A safe return_to wins with a derived label; otherwise fall
// back to the inbox — the server's mailbox_index fallback, which resolves to "/".
// backNavigation handles the inbox custom-view label and every resource prefix.
export function emailThreadBackNavigation(returnTo: string | undefined): BackNavigation {
  return backNavigation(returnTo, { url: "/", label: "Back to inbox" })
}
