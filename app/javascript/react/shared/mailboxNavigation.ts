import type { MailboxViewIdentifier } from "~/react/shared/queries/mailboxViewIndex"
import { safeReturnTo } from "~/react/shared/returnTo"
import type { MailboxSort, MailboxView } from "~/react/shared/types"

// Pure URL helpers for the show-page mailbox navigation (prev/next arrows). Kept
// out of useMailboxEntryNavigation (the hook) so features/ can parse the context
// without importing a hook, and so their purity is obvious.

// Prev/next walks either the main mailbox (`/`, optionally `?sort=`) or a focus-mode
// view/sort (`?mailbox_view_id=` / `?mailbox_view_template=`, + `?goal_id=`). The
// secondary lists (unread, archived, sent, drafts, assigned_to_me, snoozed) don't
// present navigation — a return_to pointing at any of them is treated as "no
// context" here, so the arrows stay hidden.
const PATH_TO_VIEW: Record<string, MailboxView> = {
  "/": "inbox",
}

// A boosted show page recovers where it came from by parsing its own `return_to`.
// The two navigable sources have different order backends (the main mailbox's
// paginated list vs. a focus-mode view's TanStack index), so the context is a
// discriminated union the hook branches on.
export type MailboxNavigationContext =
  | {
      kind: "inbox"
      view: MailboxView
      sort: MailboxSort
      // The mailbox list URL (path + query) we resolved this context from. Stamped
      // back onto neighbor hrefs as their `return_to` so the arrows survive each hop.
      returnTo: string
    }
  | {
      kind: "focus"
      identifier: MailboxViewIdentifier
      returnTo: string
    }

// Recover the source list from the show page's own URL. Returns null when the
// entry wasn't opened from a navigable mailbox list (no return_to, an off-site/
// unknown return_to, or a secondary list) — the arrows stay hidden.
export function parseMailboxNavigationContext(search: string): MailboxNavigationContext | null {
  const returnTo = safeReturnTo(new URLSearchParams(search).get("return_to") ?? undefined)
  if (!returnTo) return null

  let listUrl: URL
  try {
    listUrl = new URL(returnTo, "http://local")
  } catch {
    return null
  }

  // Focus-mode params identify a view/sort regardless of path (they ride on `/`).
  const viewId = listUrl.searchParams.get("mailbox_view_id")
  const template = listUrl.searchParams.get("mailbox_view_template")
  if (viewId || template) {
    return { kind: "focus", identifier: { viewId, template, goalId: listUrl.searchParams.get("goal_id") }, returnTo }
  }

  const view = PATH_TO_VIEW[listUrl.pathname]
  if (!view) return null

  const sort: MailboxSort = listUrl.searchParams.get("sort") === "oldest" ? "oldest" : "newest"
  return { kind: "inbox", view, sort, returnTo }
}

// The label between the arrows names where you are — the section title (grouped view)
// or the sort's name (ranked custom sort); `position`/`total` drive the fill and the
// "N of M" tooltip. `name` is null only when the source has no name to show.
export interface MailboxEntryPositionLabel {
  name: string | null
  position: number
  total: number
}

export interface MailboxEntryNavigation {
  // False ⇒ render nothing (entry not reached from a navigable mailbox list).
  visible: boolean
  prevHref: string | null
  nextHref: string | null
  // True while a boundary page / neighbor body is being fetched to resolve the
  // trailing neighbor — the next arrow shows a spinner instead of a hard-disabled state.
  loadingNext: boolean
  // True while a focus-mode view/sort is still being organized. Arrows are disabled
  // with a spinner until the `mailbox_view` channel reports `complete`.
  generating: boolean
  // Focus-mode only (null for the main mailbox — its total is unknown/paginated).
  positionLabel: MailboxEntryPositionLabel | null
  // Resolve the next entry's href for the archive/snooze advance, awaiting a lazy
  // neighbor-body hydration when needed (a focus ranked view pages bodies in, so the
  // synchronous `nextHref` can still be null when the arrows are otherwise live).
  // Returns null only when there is genuinely no navigable next entry (or while
  // generating) — the callers then fall back to the source list.
  resolveNextHref: () => Promise<string | null>
  // Drop the current entry from the shared list cache so it leaves the navigable
  // set (and the list, on back-navigation). Called by the archive/snooze actions
  // before they advance to the resolved next href.
  markCurrentArchived: () => void
  markCurrentSnoozed: (snoozedUntil: string) => void
}

// Shared prev/next assembly for both navigation sources (the main inbox list and a
// focus-mode view). Centralizes three invariants in one place so the two branches
// can't drift apart:
//   • visibility — shown once the current entry is located in the order (index ≥ 0),
//     or, for a source that pages toward a not-yet-loaded entry, while `visibleAtMiss`;
//   • no navigation target while `generating` — the order isn't final, so prev/next
//     resolve to null (this both disables the arrows AND makes the archive/snooze
//     advance fall back to the source list instead of a partial-order neighbor);
//   • the prev/next slot selection off a single `index`.
export function assembleNavigation({
  count,
  index,
  hrefForIndex,
  generating,
  loadingNext,
  positionLabel,
  markCurrentArchived,
  markCurrentSnoozed,
  visibleAtMiss,
}: {
  count: number
  index: number
  hrefForIndex: (i: number) => string | null
  generating: boolean
  loadingNext: boolean
  positionLabel: MailboxEntryPositionLabel | null
  markCurrentArchived: () => void
  markCurrentSnoozed: (snoozedUntil: string) => void
  visibleAtMiss: boolean
}): MailboxEntryNavigation {
  const prevIndex = index > 0 ? index - 1 : -1
  const nextIndex = index >= 0 && index < count - 1 ? index + 1 : -1
  const nextHref = generating || nextIndex < 0 ? null : hrefForIndex(nextIndex)
  return {
    visible: index >= 0 || visibleAtMiss,
    prevHref: generating || prevIndex < 0 ? null : hrefForIndex(prevIndex),
    nextHref,
    loadingNext,
    generating,
    positionLabel,
    // Default: the next href is already known synchronously. The focus branch overrides
    // this to lazily hydrate a not-yet-loaded neighbor body so the triage advance still
    // lands on the next entry instead of falling back to the source list.
    resolveNextHref: async () => nextHref,
    markCurrentArchived,
    markCurrentSnoozed,
  }
}

// Preserve the source-list return_to on a neighbor's href so opening it keeps the
// arrows (and the same "back" target). The raw href already carries the neighbor's
// own `?mailbox_entry_id=` (stamped by the API), so we only add return_to. NB: we
// deliberately don't reuse shared/returnTo's `withReturnTo` (nor its mailbox wrapper
// `entryTargetWithReturnTo`) — those stamp the *current* location (window.location,
// i.e. this show page), which would nest the return_to and break the back chain
// after one hop. Here we stamp the explicitly-passed source list instead.
export function neighborHref(rawHref: string, returnTo: string): string {
  if (rawHref === "#") return rawHref
  try {
    const url = new URL(rawHref, "http://local")
    url.searchParams.set("return_to", returnTo)
    return url.pathname + url.search + url.hash
  } catch {
    return rawHref
  }
}
