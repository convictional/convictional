import { safeReturnTo } from "~/react/shared/returnTo"
import type { BackNavigation } from "~/react/shared/types"

// Canonical client mirror of the server's back_navigation() (app/helpers/url.py):
// map a return_to URL to a labeled "back" target. Each migrated show page passes
// the `fallback` used when return_to is absent or off-site (its own index). Kept
// in one place so every page labels "back" identically instead of re-deriving a
// partial, divergent copy of the rule.
//
// PREFIX_LABELS mirrors the resource entries of the server's BACK_LABELS; keep it
// in sync. A path equal to a prefix, or nested under it (/documents/x), takes that
// label — matching the server's route-path prefix match. The inbox (root path) is
// special-cased below to honor the mailbox custom-view query.
const PREFIX_LABELS: readonly (readonly [string, string])[] = [
  ["/documents", "Back to documents"],
  ["/posts", "Back to posts"],
  ["/goals", "Back to goals"],
  ["/chats", "Back to chats"],
  ["/meetings", "Back to meetings"],
  ["/search", "Back to search"],
]

export function backNavigation(returnTo: string | undefined, fallback: BackNavigation): BackNavigation {
  const safe = safeReturnTo(returnTo)
  if (!safe) return fallback

  const [path, query = ""] = safe.split("?")

  // The inbox lives at the root path; a saved/template view is the same path with
  // a selector query (mirrors the server's mailbox custom-view special case).
  if (path === "/") {
    const params = new URLSearchParams(query)
    const isCustomView = params.has("mailbox_view_template") || params.has("mailbox_view_id")
    return { url: safe, label: isCustomView ? "Back to custom view" : "Back to inbox" }
  }

  const match = PREFIX_LABELS.find(([prefix]) => path === prefix || path.startsWith(prefix + "/"))
  return { url: safe, label: match ? match[1] : "Back" }
}
