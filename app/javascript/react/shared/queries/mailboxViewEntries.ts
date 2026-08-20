import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { MailboxEntry, MailboxEntryLookupResponse } from "~/react/shared/types"

import type { MailboxViewIdentifier } from "./mailboxViewIndex"

// The entry *bodies* for a focus-mode view, keyed the same way as the index cache
// (mailboxViewIndex) so a view has one index query and one bodies query. Split from
// the index because the two have opposite lifecycles: the index holds the full
// order eagerly (all ids at once), while bodies hydrate lazily, a page at a time —
// folding them together would force hydrating every body just to hold the full
// order, the exact regression the pagination below fixes. The list hook
// (useMailboxView) is the only reader of this one.
//
// The queryFn hydrates the *first page* of a cache hit — that's what makes the
// list hook's `loading` gate on bodies (query.isLoading) without a flash. Every
// other write (scroll-in more pages, streamed cache-miss deltas, bfcache read-state
// refresh, optimistic mutations) lands via setQueryData, mirroring how
// useMailboxEntries reconciles its channel merges.

// Cache-hit hydration page size. A view's cache holds every considered candidate (up to 250), and
// hydrating them all in one lookup is what made returning to a large custom sort take seconds. We
// hydrate a page at a time instead, matching the inbox's default page size
// (settings.pagination_default_per_page) so first paint costs the same regardless of view size. The
// value is duplicated here because the server constant isn't importable from the client; keep the two
// aligned. Remaining ids hydrate on scroll via the list's LoadMoreSentinel.
export const VIEW_HYDRATION_PAGE_SIZE = 30

export interface MailboxViewEntriesData {
  byId: Record<string, MailboxEntry>
  // How many of the index's entryIds have been hydrated so far — the paginated cursor for a ranked
  // cache hit. Full-hydration loads (grouped / mid-generation partials) set it to the whole set;
  // streamed cache misses leave it at 0 (they have no cursor — entries push in via the channel).
  hydratedCount: number
}

// Archived rows vanish immediately because the next regeneration excludes them anyway; snooze
// archives too, so both are covered. An unhydrated body is rejected — nothing can render from one —
// which is the opposite of useMailboxEntryNavigation's walk over the same field, where an unhydrated
// id counts as present so a paginated sort still finds its neighbors. Don't unify the two.
export function isVisibleViewRow(entry: MailboxEntry | undefined): entry is MailboxEntry {
  return entry !== undefined && !entry.is_archived
}

export function mailboxViewEntriesQueryKey(identifier: MailboxViewIdentifier) {
  return ["mailboxViewEntries", identifier.viewId ?? "", identifier.template ?? "", identifier.goalId ?? ""] as const
}

export function mailboxViewEntriesLookupUrl(ids: Iterable<string>): string {
  const params = new URLSearchParams()
  for (const id of ids) params.append("ids", id)
  return `/api/mailbox_entries/lookup?${params.toString()}`
}

function entriesToMap(entries: MailboxEntry[]): Record<string, MailboxEntry> {
  const byId: Record<string, MailboxEntry> = {}
  for (const entry of entries) byId[entry.id] = entry
  return byId
}

// Shared by the query's first-page hydration and the out-of-band loadMore / streaming / reconcile
// paths so all build the store identically.
export async function fetchViewEntries(ids: string[]): Promise<Record<string, MailboxEntry>> {
  if (ids.length === 0) return {}
  const response = await apiFetch<MailboxEntryLookupResponse>(mailboxViewEntriesLookupUrl(ids))
  return entriesToMap(response.entries as MailboxEntry[])
}

// Resolve a small set of entry bodies (e.g. the prev/next neighbors the navigation arrows link to)
// from the shared bodies cache, fetching any misses and merging them back so later hops — and the
// list on back-navigation — reuse them. This is the read-through path for a handful of ids, distinct
// from the list's paginated cursor (loadMoreEntries): it leaves `hydratedCount` untouched. `loading`
// reflects the real fetch state, so a settled lookup (even one that omitted an id) stops the spinner
// rather than leaving it stuck on a never-resolving href.
export function useViewEntries(
  identifier: MailboxViewIdentifier,
  ids: (string | null)[],
  enabled: boolean
): {
  entryFor: (id: string | null) => MailboxEntry | undefined
  loading: boolean
  ensure: (id: string) => Promise<MailboxEntry | undefined>
} {
  const queryClient = useQueryClient()
  const cached = queryClient.getQueryData<MailboxViewEntriesData>(mailboxViewEntriesQueryKey(identifier))?.byId
  const missing = ids.filter((id): id is string => id !== null && !cached?.[id])

  const mergeBodies = useCallback(
    (byId: Record<string, MailboxEntry>) => {
      // Merge into the shared bodies cache (cursor untouched) so the next hop and the list reuse it.
      queryClient.setQueryData<MailboxViewEntriesData>(mailboxViewEntriesQueryKey(identifier), prev => ({
        byId: { ...(prev?.byId ?? {}), ...byId },
        hydratedCount: prev?.hydratedCount ?? 0,
      }))
    },
    [queryClient, identifier]
  )

  const query = useQuery({
    queryKey: [...mailboxViewEntriesQueryKey(identifier), "lookup", missing.join(",")] as const,
    queryFn: async () => {
      const byId = await fetchViewEntries(missing)
      mergeBodies(byId)
      return byId
    },
    enabled: enabled && missing.length > 0,
  })

  const entryFor = (id: string | null): MailboxEntry | undefined =>
    id === null ? undefined : (cached?.[id] ?? query.data?.[id])

  // Imperative single-id hydration for the archive/snooze advance, which fires outside the render
  // that would otherwise wait for the reactive query above: return the cached body, else fetch it
  // (and merge) so the advance can build the neighbor href even mid-fetch.
  const ensure = useCallback(
    async (id: string): Promise<MailboxEntry | undefined> => {
      const existing = queryClient.getQueryData<MailboxViewEntriesData>(mailboxViewEntriesQueryKey(identifier))
        ?.byId?.[id]
      if (existing) return existing
      const byId = await fetchViewEntries([id])
      mergeBodies(byId)
      return byId[id]
    },
    [queryClient, identifier, mergeBodies]
  )

  return { entryFor, loading: query.isFetching, ensure }
}

// `paginate` is true only for a settled ranked sort (one flat list matching the flat id order): only
// its first page is hydrated up front, the rest on scroll. Grouped views and mid-generation partials
// hydrate every id at once (their sections index into the flat list, so a partial page would render
// whole sections falsely empty).
export function mailboxViewEntriesQueryOptions(
  identifier: MailboxViewIdentifier,
  { entryIds, paginate }: { entryIds: string[]; paginate: boolean }
) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: mailboxViewEntriesQueryKey(identifier),
    queryFn: async (): Promise<MailboxViewEntriesData> => {
      const firstPage = paginate ? entryIds.slice(0, VIEW_HYDRATION_PAGE_SIZE) : entryIds
      return { byId: await fetchViewEntries(firstPage), hydratedCount: firstPage.length }
    },
  })
}
