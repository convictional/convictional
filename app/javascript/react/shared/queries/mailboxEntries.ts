import { type InfiniteData, type QueryClient, infiniteQueryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { MailboxEntry, MailboxEntryListResponse, MailboxSort, MailboxView } from "~/react/shared/types"

// The single definition of the inbox list's cache identity and fetching, shared
// by the list hook (useMailboxEntries) and the show-page navigation hook
// (useMailboxEntryNavigation). Same queryKey ⇒ the warm cache the list page
// populated is reused instantly by the show page across a boosted navigation.
// Lives in shared/ (not the mailboxIndex feature) because the MailboxActionBar
// composite reads it, and features/ sit above composites/shared.

// A cached page is the server list response with the local-only `mutatedAt`
// field layered onto entries by optimistic mutations (see useMailboxEntries's
// channel-merge rule). MailboxEntry adds only that optional field, so a raw
// server response (entries: MailboxEntryListItem[]) is assignable as a page.
export interface MailboxEntriesPage extends Omit<MailboxEntryListResponse, "entries"> {
  entries: MailboxEntry[]
}

export type MailboxEntriesData = InfiniteData<MailboxEntriesPage, string | null>

export function mailboxEntriesQueryKey(view: MailboxView, sort: MailboxSort) {
  return ["mailboxEntries", view, sort] as const
}

// Which cached entries a view actually shows — the same predicate gates the list's
// visibleEntries and the show-page nav's navigable set, so archiving (or any
// optimistic toggle) drops an entry from both at once.
export function shouldShowEntry(entry: MailboxEntry, view: MailboxView): boolean {
  switch (view) {
    case "inbox":
    case "assigned_to_me":
      return !entry.is_archived
    // The unread view drops an entry the moment it's read (e.g. an optimistic
    // mark-read): mark_read fires no mailbox_sync broadcast, so the client has to.
    case "unread":
      return !entry.is_archived && entry.is_unread
    case "archived":
    case "snoozed":
      return entry.is_archived
    case "sent":
    case "drafts":
      return true
    default:
      return true
  }
}

export function mailboxEntriesUrl(view: MailboxView, sort: MailboxSort, cursor: string | null): string {
  const params = new URLSearchParams({ view, sort })
  if (cursor) params.set("cursor", cursor)
  return `/api/mailbox_entries?${params.toString()}`
}

export function mailboxEntriesQueryOptions(view: MailboxView, sort: MailboxSort) {
  return infiniteQueryOptions({
    ...channelQueryDefaults,
    queryKey: mailboxEntriesQueryKey(view, sort),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }): Promise<MailboxEntriesPage> =>
      apiFetch<MailboxEntryListResponse>(mailboxEntriesUrl(view, sort, pageParam)),
    getNextPageParam: lastPage => (lastPage.has_more ? lastPage.next_cursor : undefined),
  })
}

// Paginate by appending with setQueryData instead of useInfiniteQuery's
// fetchNextPage (load-bearing). fetchNextPage resolves to
// `[...pagesSnapshottedWhenTheFetchSTARTED, newPage]` — query-core's
// infiniteQueryBehavior reads `state.data` once, up front — so every write that lands
// mid-flight is discarded when the page arrives: an optimistic archive/snooze/mark-read
// (its `mutatedAt` stamp included, which is what the merge rule keys on), a channel
// merge, a page-1 refetch. An archived row would silently come back on screen. Writing
// the page ourselves reads the cache at write time, so concurrent writes survive.
//
// Resolves silently when there's nothing more to load; a failed fetch rejects and
// leaves the list as-is (callers retry on the next intent).
export async function appendNextPage(queryClient: QueryClient, view: MailboxView, sort: MailboxSort): Promise<void> {
  const key = mailboxEntriesQueryKey(view, sort)
  const current = queryClient.getQueryData<MailboxEntriesData>(key)
  // The cursor comes off the cached tail rather than the query's `hasNextPage` —
  // both read the same data, and only the cache is reachable from here.
  const tail = current?.pages[current.pages.length - 1]
  const cursor = tail?.has_more ? tail.next_cursor : null
  if (!current || !cursor) return
  const tailParam = current.pageParams[current.pageParams.length - 1]
  const page = await apiFetch<MailboxEntryListResponse>(mailboxEntriesUrl(view, sort, cursor))
  queryClient.setQueryData<MailboxEntriesData>(key, old => {
    if (!old) return old
    // The tail moved while we were fetching — a page-1 refetch collapsed the list, or a
    // concurrent append already landed. This page no longer follows it, so drop it
    // rather than splicing a hole into the order.
    if (old.pageParams[old.pageParams.length - 1] !== tailParam) return old
    return { pages: [...old.pages, page], pageParams: [...old.pageParams, cursor] }
  })
}
