import { queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type {
  ActiveMailboxView,
  MailboxViewIndexResponse,
  MailboxViewLayout,
  MailboxViewSummary,
  ViewSection,
} from "~/react/shared/types"

// The single definition of a focus-mode view/sort's index: its structure,
// ordering, and generation status — the parsed GET /api/mailbox_views (index)
// response. The list hook (useMailboxView) is the writer while the mailbox index
// island is mounted — it reconciles the `mailbox_view` channel deltas into this
// cache via setQueryData. A view's index and its entry *bodies* are split into two
// caches (this and the sibling mailboxViewEntries, keyed the same way) because
// they have opposite lifecycles: the order/structure here is eager — the full set
// of ids (up to ~250) is known at once, streamed in or read from cache — while the
// bodies hydrate lazily, a page at a time, because hydrating all of them up front
// is what made returning to a large sort take seconds (see mailboxViewEntries).
// Keeping the full order in its own cache lets the list render section structure
// (and skeleton rows) from the complete ordering without dragging every body in.

// A focus-mode view is identified the same way GET /api/mailbox_views identifies
// one: a saved view id, or a template (+ goal id for the by-goal template).
// Exactly one of viewId/template is set.
export interface MailboxViewIdentifier {
  viewId: string | null
  template: string | null
  goalId: string | null
}

export interface MailboxViewIndexData {
  active: ActiveMailboxView | null
  allViews: MailboxViewSummary[]
  // Grouped structure (LLM sections). Empty on a cache miss (nothing generated yet).
  sections: ViewSection[]
  // The flat navigable order, in section order. The list renders `sections`; the
  // navigation hook walks `entryIds`. Kept in sync with `sections` on every write.
  entryIds: string[]
  generating: boolean
  // response.cached_sections !== null — distinguishes a cache hit (sections known,
  // hydrate by id) from a miss (nothing cached, stream in via the channel). The
  // list hook's entry-body hydration branch keys on this; `sections`/`entryIds`
  // alone can't tell an empty hit from a miss.
  hadCachedSections: boolean
  // True only when the *fetched* index was a mid-generation partial (a cache hit that reported itself
  // still generating). Set once from the response and preserved across channel patches — do NOT
  // re-derive it from `hadCachedSections && generating`, because a settled cache hit that later starts
  // regenerating (a server `regenerating`/`cache_expired` broadcast) flips `generating` true without
  // being a partial. The list hook freezes deltas and reconciles on `complete` only for a true partial.
  hydratedFromPartial: boolean
  layout: MailboxViewLayout | null
  isNotFound: boolean
  hasGoalsForView: boolean
  eligibleEntryCount: number | null
  consideredEntryCount: number | null
}

// A disabled/placeholder identifier: a stable object so an inactive branch's
// (never-enabled) queries have a constant key.
export const EMPTY_MAILBOX_VIEW_IDENTIFIER: MailboxViewIdentifier = { viewId: null, template: null, goalId: null }

// Max quiet time during a generation before a consumer gives up waiting on the
// `mailbox_view` channel and refetches (or errors). Re-armed on each progress event,
// so it's the allowed gap *between* events, not a total deadline — shared by the list
// hook (useMailboxView) and the show-page navigation hook so both bound the wait.
export const GENERATION_STALL_MS = 30_000

export function mailboxViewIndexQueryKey(identifier: MailboxViewIdentifier) {
  return ["mailboxViewIndex", identifier.viewId ?? "", identifier.template ?? "", identifier.goalId ?? ""] as const
}

function mailboxViewIndexUrl(identifier: MailboxViewIdentifier): string {
  const params = new URLSearchParams()
  if (identifier.viewId) params.set("view_id", identifier.viewId)
  if (identifier.template) params.set("template", identifier.template)
  // Only the by_goal template reads goal_id; the server ignores it otherwise.
  if (identifier.goalId) params.set("goal_id", identifier.goalId)
  const query = params.toString()
  return query ? `/api/mailbox_views?${query}` : "/api/mailbox_views"
}

export function mailboxViewIndexFromResponse(response: MailboxViewIndexResponse): MailboxViewIndexData {
  const sections = response.cached_sections ?? []
  const hadCachedSections = response.cached_sections !== null
  return {
    active: response.active,
    allViews: response.all_views,
    sections,
    // Prefer the server's authoritative flat order; fall back to flattening
    // sections (they carry the same ids in the same order).
    entryIds: response.cached_entry_ids.length > 0 ? response.cached_entry_ids : entryIdsFromSections(sections),
    // A cache hit reports its own generating flag (true only for a mid-sort partial). A cache miss
    // with an active view reports generating=false, but the server *will* start generating on
    // subscribe — assert it now so the list shows "Organizing…" immediately instead of flashing an
    // empty state until the first channel delta lands.
    generating: hadCachedSections ? response.generating : response.active !== null && !response.is_not_found,
    hadCachedSections,
    hydratedFromPartial: hadCachedSections && response.generating,
    layout: response.active?.layout ?? null,
    isNotFound: response.is_not_found,
    hasGoalsForView: response.has_goals_for_view,
    eligibleEntryCount: response.eligible_entry_count,
    consideredEntryCount: response.considered_entry_count,
  }
}

// The order is ready to walk once it's either read from cache (hadCachedSections) OR streamed to
// completion this session. A cold-miss view built live from the channel clears `generating` on
// `complete` but never sets hadCachedSections — its initial GET was a miss and the list doesn't
// re-read it after a live stream — so a settled, non-empty order is the only signal that stream's
// result is authoritative. The `!generating` guard keeps a mid-stream partial (populated but not
// final) from counting as navigable.
export function orderReady(data: MailboxViewIndexData | undefined): boolean {
  if (!data) return false
  return data.hadCachedSections || (!data.generating && data.entryIds.length > 0)
}

// The single rule for whether a focus-mode entry is navigable from its view: the view's order
// must be ready (orderReady) AND this entry must sit in it. This is exactly the visibility
// useFocusEntryNavigation renders (it gates the arrow machinery on orderReady, then
// assembleNavigation shows the arrows only at index >= 0). ChatShow's autofocus gate reads it
// too, so the two surfaces can't drift apart. A missing/loading index (undefined) is not
// navigable; callers that must decide before the fetch settles (a cold direct load) handle the
// pending case themselves.
export function focusEntryIsNavigable(data: MailboxViewIndexData | undefined, mailboxEntryId: string): boolean {
  if (!orderReady(data)) return false
  return data?.entryIds.includes(mailboxEntryId) ?? false
}

// A generation the mailbox list kicked off is still streaming: the shared index reports
// `generating` with a partial order already present (entryIds populated from the channel),
// even though nothing is cached yet (a cold miss never flips hadCachedSections until a GET reads
// the completed result). The show page uses this to decide whether to subscribe when opened
// mid-generation (so the server's `complete` reaches it and surfaces the arrows). A cold *direct*
// load of an ungenerated view has no partial, so it stays false — the show page won't subscribe
// and can't kick off a generation on its own. This gates a SUBSCRIBE only, never a refetch: a
// mid-generation GET would clobber a streamed ranked partial (ranked caches nothing until done).
export function focusGenerationInFlight(data: MailboxViewIndexData | undefined): boolean {
  return !!data?.generating && data.entryIds.length > 0
}

export function mailboxViewIndexQueryOptions(identifier: MailboxViewIdentifier) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: mailboxViewIndexQueryKey(identifier),
    queryFn: async (): Promise<MailboxViewIndexData> =>
      mailboxViewIndexFromResponse(await apiFetch<MailboxViewIndexResponse>(mailboxViewIndexUrl(identifier))),
    // `sections` streams in as a *sparse* array during grouped generation — the writer slots a section
    // at its index and leaves untouched slots as holes, which consumers `flatMap` over (holes are
    // skipped; explicit `undefined` would crash them). Query's default structural sharing densifies
    // sparse arrays into explicit `undefined`, so it must be off to preserve the holes verbatim.
    structuralSharing: false,
  })
}

// --- Pure reconciliation of channel deltas into ordered sections ---
// Shared so the list hook and the navigation hook produce identical order
// from the same `mailbox_view` events.

// Sections can arrive sparsely (see slotSection), so skip empty holes rather
// than crashing on them.
export function entryIdsFromSections(sections: ViewSection[]): string[] {
  const ids: string[] = []
  for (const section of sections) {
    if (!section) continue
    for (const id of section.mailbox_entry_ids) ids.push(id)
  }
  return ids
}

// Place a section at its index without disturbing untouched slots. Sections can
// arrive out of order — the server emits an index only once that section has a
// title, so a later index may broadcast before an earlier one. Uses slice() (not
// spread) so untouched slots stay sparse holes; spread would convert them to
// explicit `undefined`, which flatMap/map would then visit and crash on.
export function slotSection(sections: ViewSection[], index: number, section: ViewSection): ViewSection[] {
  const next = sections.slice()
  next[index] = section
  return next
}

// Rebuild the single flat ranked section from the running scores. Ordered by
// score desc, tie-broken by the server's recency ordinal (rank asc) then id — the
// exact (score, rank, id) tuple the server sorts and caches with, so the live
// order matches the cached order and never reshuffles as entries hydrate.
export function rankedSectionFromScores(scores: Map<string, { score: number; rank: number }>): ViewSection[] {
  if (scores.size === 0) return []
  const ids = Array.from(scores.keys()).sort((a, b) => {
    const scoreDiff = (scores.get(b)?.score ?? 0) - (scores.get(a)?.score ?? 0)
    if (scoreDiff !== 0) return scoreDiff
    // Infinity (not 0) for a missing rank: an un-ranked entry sorts to the bottom of its tie group
    // rather than masking the inconsistency by jumping to the front.
    const rankDiff = (scores.get(a)?.rank ?? Infinity) - (scores.get(b)?.rank ?? Infinity)
    if (rankDiff !== 0) return rankDiff
    return a < b ? -1 : 1
  })
  return [{ title: "", description: "", mailbox_entry_ids: ids, goal: null }]
}
