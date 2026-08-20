import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useStallWatchdog } from "~/react/shared/hooks/useStallWatchdog"
import {
  type MailboxEntryNavigation,
  type MailboxEntryPositionLabel,
  type MailboxNavigationContext,
  assembleNavigation,
  neighborHref,
  parseMailboxNavigationContext,
} from "~/react/shared/mailboxNavigation"
import {
  type MailboxEntriesData,
  appendNextPage,
  mailboxEntriesQueryKey,
  mailboxEntriesQueryOptions,
  shouldShowEntry,
} from "~/react/shared/queries/mailboxEntries"
import {
  type MailboxViewEntriesData,
  mailboxViewEntriesQueryKey,
  useViewEntries,
} from "~/react/shared/queries/mailboxViewEntries"
import {
  EMPTY_MAILBOX_VIEW_IDENTIFIER,
  GENERATION_STALL_MS,
  type MailboxViewIdentifier,
  type MailboxViewIndexData,
  focusGenerationInFlight,
  mailboxViewIndexQueryKey,
  mailboxViewIndexQueryOptions,
  orderReady,
} from "~/react/shared/queries/mailboxViewIndex"
import type { MailboxEntry, MailboxViewPayload } from "~/react/shared/types"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

// The navigation result shape and its shared prev/next assembly live in the pure
// mailboxNavigation module; re-exported here for the existing consumers.
export type { MailboxEntryNavigation, MailboxEntryPositionLabel }

// A cold direct load whose entry sits on a later page walks forward one page at a
// time until the entry surfaces (index === -1 below). Cap that look-ahead so an
// entry that isn't in this view at all (e.g. archived away) can't cascade a request
// per page to the end of a large mailbox — after this many pages we stop and leave
// the arrows disabled. The trailing-neighbor fetch (atLoadedEnd) is unaffected.
const MAX_COLD_LOOKAHEAD_PAGES = 5

const NO_OP = () => {}
const HIDDEN: MailboxEntryNavigation = {
  visible: false,
  prevHref: null,
  nextHref: null,
  loadingNext: false,
  generating: false,
  positionLabel: null,
  resolveNextHref: async () => null,
  markCurrentArchived: NO_OP,
  markCurrentSnoozed: NO_OP,
}

// mailboxEntryId is "" when the host action bar renders on a surface without an
// entry (nav feature off) — the hook then no-ops (no query, HIDDEN) so it can be
// called unconditionally from MailboxActionBar. Both branch hooks always run (React
// forbids conditional hooks); each gates its own queries and the active context wins.
export function useMailboxEntryNavigation({ mailboxEntryId }: { mailboxEntryId: string }): MailboxEntryNavigation {
  // Parse once per mount: a boosted navigation to a neighbor remounts this island,
  // so re-reading window.location each navigation is exactly right.
  const context = useMemo(() => parseMailboxNavigationContext(window.location.search), [])

  const inbox = useInboxEntryNavigation(context, mailboxEntryId)
  const focus = useFocusEntryNavigation(context, mailboxEntryId)

  if (mailboxEntryId === "" || context === null) return HIDDEN
  return context.kind === "inbox" ? inbox : focus
}

function useInboxEntryNavigation(
  context: MailboxNavigationContext | null,
  mailboxEntryId: string
): MailboxEntryNavigation {
  const inboxContext = context?.kind === "inbox" ? context : null
  const hasContext = inboxContext !== null && mailboxEntryId !== ""
  const queryClient = useQueryClient()

  const view = inboxContext?.view ?? "inbox"
  const sort = inboxContext?.sort ?? "newest"

  const { data, hasNextPage } = useInfiniteQuery({
    ...mailboxEntriesQueryOptions(view, sort),
    enabled: hasContext,
  })

  // Navigate over the same set the list shows — archived (and otherwise hidden)
  // entries are skipped, so archiving one removes it from the walk.
  const entries = useMemo(() => {
    const all = data?.pages.flatMap(page => page.entries) ?? []
    return inboxContext ? all.filter(entry => shouldShowEntry(entry, inboxContext.view)) : all
  }, [data, inboxContext])
  const index = entries.findIndex(entry => entry.id === mailboxEntryId)

  const patchCurrent = useCallback(
    (patch: Partial<MailboxEntry>) => {
      if (!inboxContext) return
      queryClient.setQueryData<MailboxEntriesData>(mailboxEntriesQueryKey(view, sort), old => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map(page => ({
            ...page,
            entries: page.entries.map(entry => (entry.id === mailboxEntryId ? { ...entry, ...patch } : entry)),
          })),
        }
      })
    },
    [queryClient, inboxContext, view, sort, mailboxEntryId]
  )

  const markCurrentArchived = useCallback(() => patchCurrent({ is_archived: true }), [patchCurrent])
  // Snooze sets is_archived too (useMailboxMutations), so the inbox predicate drops
  // it from the walk; carry the snooze fields so the cached entry stays accurate.
  const markCurrentSnoozed = useCallback(
    (snoozedUntil: string) => patchCurrent({ is_archived: true, is_snoozed: true, snoozed_until: snoozedUntil }),
    [patchCurrent]
  )

  // Self is the last loaded entry (or not yet loaded) but more pages exist: pull
  // the next page so the trailing neighbor — or self, on a cold direct load whose
  // entry sits on a later page — resolves.
  const atLoadedEnd = index === entries.length - 1
  // index === -1 is the cold-load case (entry on a later, not-yet-loaded page);
  // walk forward but only up to the look-ahead cap so a not-in-view entry can't
  // page to the end of the mailbox.
  const pagesLoaded = data?.pages.length ?? 0
  const withinLookahead = pagesLoaded < MAX_COLD_LOOKAHEAD_PAGES
  const shouldFetchNext = hasContext && hasNextPage && (atLoadedEnd || (index === -1 && withinLookahead))
  // Appended by hand rather than via fetchNextPage so archive/snooze's patchCurrent (or a
  // list-side optimistic mutation) can't be clobbered by a page landing mid-flight — see
  // appendNextPage.
  //
  // The walk steps off `pagesLoaded`, and dedups against the page count it last asked for,
  // rather than off an in-flight flag: a page that resolves before its own "started
  // fetching" render commits collapses such a flag back to its old value, leaving the
  // effect's deps unchanged so React skips it and the walk stalls a page short. The
  // requested count only ever moves forward, so each page is asked for exactly once no
  // matter how the fetch and the render interleave. A failed page stops the walk (the
  // count stays ahead of what landed), leaving the arrows where they are rather than
  // retrying in a loop.
  const requestedPages = useRef(0)
  useEffect(() => {
    if (!shouldFetchNext || requestedPages.current > pagesLoaded) return
    requestedPages.current = pagesLoaded + 1
    void appendNextPage(queryClient, view, sort).catch(() => {})
  }, [shouldFetchNext, pagesLoaded, queryClient, view, sort])

  if (!hasContext || inboxContext === null) {
    return { ...HIDDEN, markCurrentArchived, markCurrentSnoozed }
  }

  return assembleNavigation({
    count: entries.length,
    index,
    hrefForIndex: i => neighborHref(entries[i].href, inboxContext.returnTo),
    generating: false,
    // Only the trailing edge shows a spinner; a missing prev is a hard end. index === -1 is
    // the cold-load case (paging forward), which shows no spinner until the entry surfaces.
    loadingNext: shouldFetchNext && index !== -1,
    positionLabel: null,
    markCurrentArchived,
    markCurrentSnoozed,
    // Stay visible while paging toward a not-yet-loaded entry (index === -1).
    visibleAtMiss: true,
  })
}

function useFocusEntryNavigation(
  context: MailboxNavigationContext | null,
  mailboxEntryId: string
): MailboxEntryNavigation {
  const focusContext = context?.kind === "focus" ? context : null
  const returnTo = focusContext?.returnTo ?? ""
  const queryClient = useQueryClient()
  const { user } = useCurrentUser()

  // Stable identifier so the query keys and cache patches don't churn each render.
  const rawIdentifier = focusContext?.identifier
  const identifier = useMemo<MailboxViewIdentifier>(
    () =>
      rawIdentifier
        ? { viewId: rawIdentifier.viewId, template: rawIdentifier.template, goalId: rawIdentifier.goalId }
        : EMPTY_MAILBOX_VIEW_IDENTIFIER,
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key off the identifier's fields, not its unstable object identity
    [rawIdentifier?.viewId, rawIdentifier?.template, rawIdentifier?.goalId]
  )
  const enabled = focusContext !== null && mailboxEntryId !== ""

  // The order/sections/generating come from the shared focus-mode index cache — warm
  // from the list across a boosted nav, or fetched cold. We never process channel
  // deltas here (that reconciliation belongs to useMailboxView); we only refetch this
  // authoritative index once generation completes.
  const { data } = useQuery({ ...mailboxViewIndexQueryOptions(identifier), enabled })

  const generating = data?.generating ?? false
  // hasOrder gates the arrow machinery (subscribe/neighbors/watchdog) — looser than the
  // rendered visibility, which also needs the entry in the order (index >= 0). Their
  // conjunction is `focusEntryIsNavigable`, the same rule ChatShow's autofocus gate reads.
  const hasOrder = orderReady(data)
  // The list hides archived entries but leaves them in the order, so walk only that same visible set.
  // An id whose body we haven't hydrated can't have been archived from a row, so it counts as visible
  // — unlike isVisibleViewRow, which rejects it because it decides what renders. Mirrors the inbox
  // branch, which filters its walk via shouldShowEntry.
  const bodies = queryClient.getQueryData<MailboxViewEntriesData>(mailboxViewEntriesQueryKey(identifier))?.byId
  const isVisible = useCallback((id: string) => !bodies?.[id]?.is_archived, [bodies])
  const entryIds = useMemo(() => (data?.entryIds ?? []).filter(isVisible), [data?.entryIds, isVisible])
  const index = entryIds.indexOf(mailboxEntryId)
  const nextId = index >= 0 && index < entryIds.length - 1 ? entryIds[index + 1] : null

  // Neighbor bodies (for their hrefs) hydrate lazily into the shared entries cache; a
  // ranked sort only hydrates a page at a time, so a neighbor may be absent. Resolve
  // just the immediate neighbors (≤ 2 ids), fetching any misses into the shared cache.
  const prevId = index > 0 ? entryIds[index - 1] : null
  const {
    entryFor,
    loading: neighborsLoading,
    ensure,
  } = useViewEntries(identifier, [prevId, nextId], enabled && hasOrder)
  const hrefFor = (id: string | null): string | null => {
    const entry = entryFor(id)
    return entry ? neighborHref(entry.href, returnTo) : null
  }

  const channelId = data?.active?.channel_id ?? null
  const userId = user?.id ?? null
  // Subscribe when there's a cached order OR a generation the list started is still streaming a
  // partial (focusGenerationInFlight). The latter is how a show page opened mid-generation
  // receives `complete` — the server re-announces it on (re)subscribe — and surfaces its arrows
  // once the order settles (the `complete` handler below refetches; safe because complete ⇒ done,
  // never a mid-generation clobber). A cold *direct* load has no partial, so it never wants to
  // subscribe and can't kick off a generation on its own.
  const wantsSubscription =
    enabled && (hasOrder || focusGenerationInFlight(data)) && channelId !== null && userId !== null
  // Latch it: a `regenerating`/`cache_expired` refetch transiently empties the order (a ranked view
  // caches nothing mid-generation), which would otherwise drop `wantsSubscription` to false and
  // unsubscribe us right before the new generation's `complete` — stranding the arrows forever.
  // Post-clobber state is indistinguishable from a cold direct load by data alone, so we remember
  // we already subscribed (a guarded in-render setState, applied in the same commit). The island
  // remounts per entry, so the latch resets naturally.
  const [everSubscribed, setEverSubscribed] = useState(false)
  if (wantsSubscription && !everSubscribed) setEverSubscribed(true)
  const subscribing = everSubscribed && enabled && channelId !== null && userId !== null

  // Backstop a generation that never signals `complete` — a crashed task or dropped connection that
  // leaves the index stuck at generating:true. Re-armed on each channel event (the handler below),
  // NOT on cache writes: this hook doesn't reconcile progress deltas into the index (that belongs to
  // useMailboxView), so a healthy but slow stream re-arms through its own events and only a genuinely
  // silent channel trips it. On a real stall, force generating→false so the arrows enable over
  // whatever order is cached rather than spinning forever — and do NOT refetch, since a
  // mid-generation GET would clobber a streamed ranked partial.
  const { reset: resetStallWatchdog } = useStallWatchdog({
    enabled: enabled && hasOrder && generating,
    stallMs: GENERATION_STALL_MS,
    onStall: useCallback(() => {
      queryClient.setQueryData<MailboxViewIndexData>(mailboxViewIndexQueryKey(identifier), prev =>
        prev ? { ...prev, generating: false } : prev
      )
    }, [queryClient, identifier]),
  })

  useChannel(
    subscribing ? { stream: ChannelStream.MAILBOX_VIEW, params: { view_id: channelId, user_id: userId } } : null,
    ChannelEventResource.MAILBOX_VIEW,
    useCallback(
      (_action, payload) => {
        resetStallWatchdog()
        const type = (payload as MailboxViewPayload).type
        if (type === "complete" || type === "error" || type === "regenerating" || type === "cache_expired") {
          void queryClient.invalidateQueries({ queryKey: mailboxViewIndexQueryKey(identifier) })
        }
      },
      [queryClient, identifier, resetStallWatchdog]
    )
  )

  const dropFromIndex = useCallback(() => {
    queryClient.setQueryData<MailboxViewIndexData>(mailboxViewIndexQueryKey(identifier), old => {
      if (!old) return old
      return {
        ...old,
        entryIds: old.entryIds.filter(id => id !== mailboxEntryId),
        sections: old.sections.map(section =>
          section
            ? { ...section, mailbox_entry_ids: section.mailbox_entry_ids.filter(id => id !== mailboxEntryId) }
            : section
        ),
      }
    })
  }, [queryClient, identifier, mailboxEntryId])

  if (!enabled || focusContext === null || !hasOrder || data === undefined) {
    return { ...HIDDEN, markCurrentArchived: dropFromIndex, markCurrentSnoozed: dropFromIndex }
  }

  const navigation = assembleNavigation({
    count: entryIds.length,
    index,
    hrefForIndex: i => hrefFor(entryIds[i]),
    generating,
    // Soft spinner only while the neighbor body is still being fetched; once the lookup
    // settles (even if it omitted the id) the spinner clears instead of hanging forever.
    loadingNext: !generating && nextId !== null && hrefFor(nextId) === null && neighborsLoading,
    positionLabel: positionLabelFor(data, mailboxEntryId, isVisible),
    markCurrentArchived: dropFromIndex,
    markCurrentSnoozed: dropFromIndex,
    // A focus view knows its whole order, so an entry not in it has no navigation:
    // hide (unlike the paging inbox) rather than show a dead prev/next cluster.
    visibleAtMiss: false,
  })

  return {
    ...navigation,
    // A ranked view pages neighbor bodies in, so the next href may not be resolved yet when archive/
    // snooze fires. Hydrate it on demand (into the shared cache) so the advance lands on the next
    // entry instead of bouncing to the source list; null (fall back to the list) only when there is
    // genuinely no navigable next entry or the order isn't final.
    resolveNextHref: async () => {
      if (navigation.nextHref) return navigation.nextHref
      if (generating || nextId === null) return null
      // A failed hydration must not surface as an archive/snooze error — the mutation
      // already succeeded. Fall back to null so the caller lands on the source list.
      try {
        const entry = await ensure(nextId)
        return entry ? neighborHref(entry.href, returnTo) : null
      } catch {
        return null
      }
    },
  }
}

// Position/total count only visible (non-archived) entries so the label and fill match the
// rendered list, which hides archived rows. `isVisible` is the same predicate the walk uses.
function positionLabelFor(
  data: MailboxViewIndexData,
  mailboxEntryId: string,
  isVisible: (id: string) => boolean
): MailboxEntryPositionLabel | null {
  if (data.layout === "grouped") {
    for (const section of data.sections) {
      if (!section) continue
      const visible = section.mailbox_entry_ids.filter(isVisible)
      const position = visible.indexOf(mailboxEntryId)
      if (position >= 0) {
        return { name: section.title, position: position + 1, total: visible.length }
      }
    }
    return null
  }
  // Ranked sort (single flat, title-less section): position within the whole sort,
  // labeled with the sort's name (the active view's title).
  const visible = data.entryIds.filter(isVisible)
  const position = visible.indexOf(mailboxEntryId)
  if (position < 0) return null
  return { name: data.active?.title ?? null, position: position + 1, total: visible.length }
}
