import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { getChannelsClient } from "~/channels/client"
import { apiFetch, errorMessage as toErrorMessage } from "~/react/shared/apiFetch"
import { useBoundaryNavigate } from "~/react/shared/hooks/useBoundaryNavigate"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useStallWatchdog } from "~/react/shared/hooks/useStallWatchdog"
import {
  type MailboxViewEntriesData,
  VIEW_HYDRATION_PAGE_SIZE,
  fetchViewEntries,
  mailboxViewEntriesLookupUrl,
  mailboxViewEntriesQueryKey,
  mailboxViewEntriesQueryOptions,
} from "~/react/shared/queries/mailboxViewEntries"
import {
  GENERATION_STALL_MS,
  type MailboxViewIndexData,
  type MailboxViewIdentifier,
  entryIdsFromSections,
  mailboxViewIndexQueryKey,
  mailboxViewIndexQueryOptions,
  rankedSectionFromScores,
  slotSection,
} from "~/react/shared/queries/mailboxViewIndex"
import { showFlash } from "~/shared/flash"
import { type ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

import { localMutationWins } from "../optimisticMerge"
import type {
  ActiveMailboxView,
  MailboxEntry,
  MailboxEntryLookupResponse,
  MailboxSyncPayload,
  MailboxViewLayout,
  MailboxViewMutationResponse,
  MailboxViewPayload,
  MailboxViewSummary,
  ViewSection,
} from "../types"
import { type MailboxMutations, useMailboxMutations } from "./useMailboxMutations"

// Stable empty defaults so a data-less render doesn't hand consumers a fresh identity each time.
const EMPTY_ENTRIES: Record<string, MailboxEntry> = {}
const EMPTY_SECTIONS: ViewSection[] = []
const EMPTY_VIEWS: MailboxViewSummary[] = []
const EMPTY_IDS: string[] = []

export interface UseMailboxViewOptions {
  initialViewId: string | null
  initialTemplate: string | null
  // The target goal for the "by_goal" ranked sort. The server bakes it into the active view's
  // channel_id, so it only needs to reach the initial index request — the channel round-trips
  // it from there.
  initialGoalId: string | null
  // The current user's id — forms the mailbox_view / mailbox_sync topic identity. From the
  // current-user bootstrap (useCurrentUser); both streams subscribe by topic, unsigned.
  userId: string | null
}

export interface UseMailboxViewResult {
  loading: boolean
  active: ActiveMailboxView | null
  allViews: MailboxViewSummary[]
  sections: ViewSection[]
  // Entries referenced by the active view's sections. Empty until the entries-by-id
  // fetch completes; sections are rendered immediately and rows hydrate as data arrives.
  entriesById: Record<string, MailboxEntry>
  // Cache-hit hydration is paginated: `hasMoreEntries` is true while cached ids remain
  // unhydrated, `loadMoreEntries` hydrates the next page (driven by the list's sentinel),
  // and `loadingMoreEntries` gates the sentinel spinner + concurrent calls.
  hasMoreEntries: boolean
  loadingMoreEntries: boolean
  loadMoreEntries: () => Promise<void>
  isGenerating: boolean
  isNotFound: boolean
  hasGoalsForView: boolean
  errorMessage: string | null
  // Every organized item actioned away — the view is a wall of empty sections.
  isCleared: boolean
  newMessagesCount: number
  // Coverage transparency: organized vs. eligible inbox counts; both null when no view is active.
  eligibleEntryCount: number | null
  consideredEntryCount: number | null
  // Optimistic mutations against the view's entriesById store, so archive /
  // mark-read / snooze on a section row updates the rendered entry immediately.
  mutations: MailboxMutations
  // Mutations — each navigates after success to mirror the form-post HTML routes.
  createView: (params: { view_request: string; title?: string; layout?: MailboxViewLayout }) => Promise<void>
  updateView: (
    viewId: string,
    params: { view_request?: string; title?: string; layout?: MailboxViewLayout }
  ) => Promise<void>
  refreshView: (viewId: string) => Promise<void>
  deleteView: (viewId: string) => Promise<void>
}

export function useMailboxView({
  initialViewId,
  initialTemplate,
  initialGoalId,
  userId,
}: UseMailboxViewOptions): UseMailboxViewResult {
  const queryClient = useQueryClient()
  // The create/update responses hand back a server-built redirect URL rather than a
  // route + params, so navigation goes through the helper that owns the
  // href-string -> client-route split instead of re-deriving the target here.
  const boundaryNavigate = useBoundaryNavigate()

  // A focus-mode view is two shared queries keyed on its identity, following the inbox list's
  // single-query pattern (useMailboxEntries / mailboxEntries.ts): `index` holds the
  // structure/ordering/generation status (the parsed /api/mailbox_views index response) and `entries`
  // holds the entry bodies the list renders. They're split because the order is eager (the full id set
  // at once) while bodies hydrate lazily a page at a time — see mailboxViewIndex/mailboxViewEntries.
  // Both are driven by useQuery so a view switch is just a key change (a full remount here), `loading`
  // derives from the query states, and the mailbox_view channel deltas reconcile in via setQueryData —
  // the same posture useMailboxEntries takes for its mailbox_sync merges.
  const identifier = useMemo<MailboxViewIdentifier>(
    () => ({ viewId: initialViewId, template: initialTemplate, goalId: initialGoalId }),
    [initialViewId, initialTemplate, initialGoalId]
  )
  const indexKey = useMemo(() => mailboxViewIndexQueryKey(identifier), [identifier])
  const entriesKey = useMemo(() => mailboxViewEntriesQueryKey(identifier), [identifier])
  const hasActiveView = initialViewId !== null || initialTemplate !== null

  const index = useQuery(mailboxViewIndexQueryOptions(identifier))
  const data = index.data

  const active = data?.active ?? null
  const allViews = data?.allViews ?? EMPTY_VIEWS
  const sections = data?.sections ?? EMPTY_SECTIONS
  const isGenerating = data?.generating ?? false
  const isNotFound = data?.isNotFound ?? false
  const hasGoalsForView = data?.hasGoalsForView ?? true
  const eligibleEntryCount = data?.eligibleEntryCount ?? null
  const consideredEntryCount = data?.consideredEntryCount ?? null
  const entryIds = data?.entryIds ?? EMPTY_IDS
  const hadCachedSections = data?.hadCachedSections ?? false
  const layout = data?.layout ?? null

  // Paginate only a settled ranked sort — its one flat list matches the flat id order. Grouped
  // sections index into that list, and a mid-generation partial reconciles on `complete`, so both
  // hydrate in full up front with the sentinel hidden.
  const paginateBodies = hadCachedSections && !isGenerating && layout === "ranked"

  // The bodies query's queryFn hydrates the first page of a cache hit — so `loading` gates on the
  // rows being ready, not just the index landing. It's enabled only for a cache hit; a cache miss
  // streams entries in via the channel (setQueryData), and the query stays cold. Its `enabled`/`data`
  // are read off the index query, which resolves first, so entryIds are settled when it fetches.
  const entries = useQuery({
    ...mailboxViewEntriesQueryOptions(identifier, { entryIds, paginate: paginateBodies }),
    enabled: hadCachedSections,
  })
  const entriesById = entries.data?.byId ?? EMPTY_ENTRIES
  const hydratedCount = entries.data?.hydratedCount ?? 0

  // Skeleton until the first paint is ready: the index load, plus (on a cache hit) the first page of
  // bodies. Both are query states read on the same render, so there's no window where the skeleton is
  // gone but the rows aren't in yet. A cache miss doesn't gate on bodies — it renders the empty list
  // with the "Organizing…" spinner (isGenerating) while entries stream in.
  const loading = hasActiveView && (index.isLoading || (hadCachedSections && entries.isLoading))
  const hasMoreEntries = paginateBodies && hydratedCount < entryIds.length

  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [newMessagesCount, setNewMessagesCount] = useState(0)
  const [loadingMoreEntries, setLoadingMoreEntries] = useState(false)

  // An unhydrated body must never read as actioned, so `?.` leaves it falsy. Bodies arrive a page at a
  // time, so requiring the whole order to resolve is also what covers the initial loading window.
  // Skipped mid-generation and behind an error — both already replace or hide these rows.
  const isCleared =
    !isGenerating && errorMessage === null && entryIds.length > 0 && entryIds.every(id => entriesById[id]?.is_archived)

  const applyToIndex = useCallback(
    (updater: (prev: MailboxViewIndexData) => MailboxViewIndexData) => {
      queryClient.setQueryData<MailboxViewIndexData>(indexKey, prev => (prev ? updater(prev) : prev))
    },
    [queryClient, indexKey]
  )

  const applyToEntries = useCallback(
    (updater: (prev: MailboxViewEntriesData) => MailboxViewEntriesData) => {
      queryClient.setQueryData<MailboxViewEntriesData>(entriesKey, prev =>
        updater(prev ?? { byId: {}, hydratedCount: 0 })
      )
    },
    [queryClient, entriesKey]
  )

  // A regeneration (manual refresh or mid-stream retry) is in flight. We keep the prior
  // sections rendered until the first fresh section arrives, rather than blanking the whole
  // view to a loading state. Plain ref, not state: it gates how the next `section` event is
  // applied, not what renders.
  const awaitingFreshGenerationRef = useRef<boolean>(false)

  // True when the *fetched* index was a partial cache hit (a refresh landed mid-generation): its
  // channel deltas are frozen and we reconcile on `complete`. Read straight from the index data
  // (set once at fetch time, preserved across patches) — NOT re-derived as `hadCachedSections &&
  // isGenerating`, which would also fire for a settled cache hit that later starts regenerating via a
  // channel event, needlessly freezing its live deltas and reconciling (re-hydrating bodies) on
  // `complete`. Mirrored to a ref so the channel handlers can read it without being re-created.
  const hydratedFromPartial = data?.hydratedFromPartial ?? false
  const hydratedFromPartialRef = useRef(false)
  hydratedFromPartialRef.current = hydratedFromPartial

  // Mirror the rendered generating flag so the `complete` handler can distinguish a settled view
  // that received a redundant `complete` on (re)subscribe (no-op) from one that's actually
  // generating. Read via ref so the handler needn't depend on it.
  const isGeneratingRef = useRef(isGenerating)
  isGeneratingRef.current = isGenerating

  // Whether this hook instance has received any order-bearing stream delta (section / score) since
  // mount. On `complete` it tells a live generation this session streamed to completion — whose
  // on-screen order is already the full, authoritative one — from a generation that finished while
  // we were unmounted: a boosted hop away and back remounts against a stale generating cache holding
  // only a *partial* order (the prior session's stream stopped short), and the server re-announces
  // `complete` on resubscribe with no deltas following. The former just clears generating; the
  // latter must reconcile to pull the full cached order. Reset on mount / view switch.
  const sawLiveStreamRef = useRef(false)

  // In-flight lookup dedup for streamed cache-miss deltas: two deltas can name the same id before the
  // first fetch resolves. Persisted hydration is tracked by the bodies cache itself (an id already in
  // `byId` isn't refetched); this only guards the concurrent-in-flight window.
  const inFlightIdsRef = useRef<Set<string>>(new Set())

  // Ranked sorts stream a score per candidate (`entry_scored`) plus a batched sentinel tail
  // (`entries_scored`). We keep the running score and the server's recency ordinal (`rank`) per
  // candidate here and rebuild one flat section ordered by them (rankedSectionFromScores). Cache hits
  // bypass this entirely — they arrive as `cached_sections` already in the server's authoritative order.
  const rankedScoresRef = useRef<Map<string, { score: number; rank: number }>>(new Map())

  // Bumped whenever the hydration target changes (view switch, regeneration, reconcile). A page /
  // streamed fetch captures the id at dispatch and drops its result if the ref has moved on — so a
  // fetch from a superseded target can't merge stale entries or advance the cursor against the wrong
  // order. Mirrors the request-id guard in refreshVisibleEntries / usePaginatedList.
  const hydrationRequestIdRef = useRef(0)

  // Refs mirroring render values so loadMoreEntries stays referentially stable — a callback whose
  // identity changed on every load toggle would churn LoadMoreSentinel's IntersectionObserver.
  const entryIdsRef = useRef<string[]>(entryIds)
  entryIdsRef.current = entryIds
  const hydratedCountRef = useRef(hydratedCount)
  hydratedCountRef.current = hydratedCount
  const loadingMoreRef = useRef(false)
  loadingMoreRef.current = loadingMoreEntries

  // Guards refreshVisibleEntries against out-of-order responses when two refreshes overlap
  // (e.g. a bfcache restore landing alongside a WS reconnect). Mirrors useMailboxEntries' fetchPage.
  const refreshRequestIdRef = useRef(0)

  // Merge a set of ids into the bodies store. `requestId` is the hydration target the caller
  // dispatched against; if it moves on before the response lands (view switch, regeneration,
  // reconcile) the result is dropped as stale. Dedups against the bodies cache (already hydrated) and
  // the in-flight set. Returns "ok" when entries merged, "failed" when the fetch errored (ids
  // released so the page can be retried), or "stale".
  const mergeEntries = useCallback(
    async (ids: string[], requestId: number): Promise<"ok" | "failed" | "stale"> => {
      const current = queryClient.getQueryData<MailboxViewEntriesData>(entriesKey)
      const fresh = ids.filter(id => !current?.byId[id] && !inFlightIdsRef.current.has(id))
      if (fresh.length === 0) return "ok"
      for (const id of fresh) inFlightIdsRef.current.add(id)
      try {
        const byId = await fetchViewEntries(fresh)
        for (const id of fresh) inFlightIdsRef.current.delete(id)
        if (hydrationRequestIdRef.current !== requestId) return "stale"
        applyToEntries(prev => ({ ...prev, byId: { ...prev.byId, ...byId } }))
        return "ok"
      } catch {
        for (const id of fresh) inFlightIdsRef.current.delete(id)
        return hydrationRequestIdRef.current === requestId ? "failed" : "stale"
      }
    },
    [queryClient, entriesKey, applyToEntries]
  )

  // Streaming hydration for cache misses: entries arrive via the section/score deltas rather than a
  // known id list, so just merge each batch through the shared fetcher (dedup + stale-guard inside).
  const fetchMissingEntries = useCallback(
    (ids: string[]) => {
      void mergeEntries(ids, hydrationRequestIdRef.current)
    },
    [mergeEntries]
  )

  const loadMoreEntries = useCallback(async () => {
    const all = entryIdsRef.current
    const start = hydratedCountRef.current
    if (loadingMoreRef.current || start >= all.length) return
    const requestId = hydrationRequestIdRef.current
    const end = Math.min(start + VIEW_HYDRATION_PAGE_SIZE, all.length)
    setLoadingMoreEntries(true)
    const result = await mergeEntries(all.slice(start, end), requestId)
    // Only advance the cursor when this page is still for the current view and it actually landed.
    if (hydrationRequestIdRef.current === requestId && result === "ok") {
      applyToEntries(prev => ({ ...prev, hydratedCount: end }))
    }
    setLoadingMoreEntries(false)
  }, [mergeEntries, applyToEntries])

  // Re-pull read/archived state for the currently-visible entries. The view hydrates its bodies once
  // on load and, unlike the inbox list, has no live entry-level sync. So after opening an entry (its
  // show page marks it read) and returning via the bfcache, the row would still look unread.
  // mark_as_read broadcasts no mailbox_sync, so a server push won't cover it — re-lookup instead.
  // Preserves any entry whose optimistic mutation is newer than this fetch.
  const refreshVisibleEntries = useCallback(async () => {
    // Only entries actually hydrated so far are on screen, so refresh just those — the keys of the
    // bodies store, not every cached id.
    const ids = Object.keys(queryClient.getQueryData<MailboxViewEntriesData>(entriesKey)?.byId ?? {})
    if (ids.length === 0) return
    const thisRequest = ++refreshRequestIdRef.current
    try {
      const response = await apiFetch<MailboxEntryLookupResponse>(mailboxViewEntriesLookupUrl(ids))
      // A later refresh superseded this one — drop the stale response.
      if (refreshRequestIdRef.current !== thisRequest) return
      applyToEntries(prev => {
        const byId = { ...prev.byId }
        const nowMs = Date.now()
        for (const entry of response.entries) {
          if (localMutationWins(byId[entry.id], nowMs)) continue
          byId[entry.id] = entry as MailboxEntry
        }
        return { ...prev, byId }
      })
    } catch {
      // Leave the current entries in place if the refresh fails.
    }
  }, [queryClient, entriesKey, applyToEntries])

  // Reconcile the partial order to the authoritative one: refetch the index (the cache now holds the
  // final ordering) and re-hydrate bodies from it. Out-of-band (like useMailboxEntries' page-1
  // refetch) — the visible partial stays on screen until this lands, so the list isn't blanked. Held
  // in a ref so the watchdog and `complete` handler can trigger it without taking it as a dependency.
  const reconcile = useCallback(async () => {
    const requestId = ++hydrationRequestIdRef.current
    rankedScoresRef.current = new Map()
    inFlightIdsRef.current = new Set()
    try {
      const fresh = await queryClient.fetchQuery({ ...mailboxViewIndexQueryOptions(identifier), staleTime: 0 })
      if (hydrationRequestIdRef.current !== requestId) return
      setErrorMessage(null)
      if (fresh.hadCachedSections) {
        const paginate = !fresh.generating && fresh.layout === "ranked"
        const firstPage = paginate ? fresh.entryIds.slice(0, VIEW_HYDRATION_PAGE_SIZE) : fresh.entryIds
        const byId = await fetchViewEntries(firstPage)
        if (hydrationRequestIdRef.current !== requestId) return
        queryClient.setQueryData<MailboxViewEntriesData>(entriesKey, { byId, hydratedCount: firstPage.length })
      }
    } catch (e) {
      setErrorMessage(toErrorMessage(e, "Failed to load view."))
    }
  }, [queryClient, identifier, entriesKey])
  const reconcileRef = useRef(reconcile)
  reconcileRef.current = reconcile

  // Reset the per-view streaming working state whenever the identity changes (mount / view switch).
  // Bumping the request id also strands any in-flight page from a previous target.
  useEffect(() => {
    hydrationRequestIdRef.current += 1
    inFlightIdsRef.current = new Set()
    rankedScoresRef.current = new Map()
    awaitingFreshGenerationRef.current = false
    sawLiveStreamRef.current = false
  }, [entriesKey])

  // A fresh generation is starting — the server has dropped its cached ordering and will
  // restream. Marking the next `section` event as a fresh-set boundary instead of blanking
  // here avoids the "all sections show Nothing in this category" empty-view symptom; the
  // current list stays rendered until the first fresh delta replaces it. Ranked: the server
  // clears its scored set and restreams, so drop ours too. Bumping the request id strands any
  // in-flight page so a late response can't write into the regenerated view.
  const beginRegeneration = useCallback(() => {
    awaitingFreshGenerationRef.current = true
    rankedScoresRef.current = new Map()
    inFlightIdsRef.current = new Set()
    hydrationRequestIdRef.current += 1
    // A new attempt is starting; drop any stale error so it can't outlive a successful retry.
    setErrorMessage(null)
    applyToIndex(prev => ({ ...prev, generating: true }))
  }, [applyToIndex])

  // Generation watchdog: if a generating view produces no events for GENERATION_STALL_MS, surface an
  // error instead of spinning on "Organizing…" forever (a server-side generation that fails without
  // broadcasting — crashed task, dropped connection — would otherwise hang indefinitely). Armed while
  // generating; the channel handler resets it on each delta (below), so a slow-but-streaming
  // generation keeps pushing the deadline out. A settled generation whose `complete` was missed
  // recovers via the channel instead (the server re-announces `complete` on (re)subscribe, including
  // reconnect), so reaching the timeout means generation genuinely stalled.
  const { reset: resetGenerationWatchdog } = useStallWatchdog({
    enabled: hasActiveView && isGenerating,
    stallMs: GENERATION_STALL_MS,
    onStall: useCallback(() => {
      applyToIndex(prev => ({ ...prev, generating: false }))
      setErrorMessage(prev => prev ?? "This is taking longer than expected. Refresh to try again.")
    }, [applyToIndex]),
  })

  // bfcache restore (browser back from an opened entry) hands the island back with stale state,
  // and a websocket reconnect means updates may have been missed while disconnected — refresh the
  // visible entries' read/archived state in both cases. Mirrors useMailboxEntries' reconnect refetch.
  useEffect(() => {
    const onPageShow = (event: PageTransitionEvent) => {
      if (event.persisted) refreshVisibleEntries()
    }
    window.addEventListener("pageshow", onPageShow)
    const client = getChannelsClient()
    client?.on("reconnected", refreshVisibleEntries)
    return () => {
      window.removeEventListener("pageshow", onPageShow)
      client?.off("reconnected", refreshVisibleEntries)
    }
  }, [refreshVisibleEntries])

  const handleChannelMessage = useCallback(
    (_action: ChannelEventAction, channelData: Record<string, unknown>) => {
      // Any event means the channel is alive — push the stall watchdog's deadline out (no-ops unless
      // a generation is in flight, so a stray event on a settled view can't arm a late error).
      resetGenerationWatchdog()
      const payload = channelData as unknown as MailboxViewPayload
      switch (payload.type) {
        case "section": {
          // First section of a fresh generation: discard the prior set so a regeneration that
          // returns fewer sections can't leave stale ones behind. We swap here (on arrival)
          // rather than blanking when regeneration *started*, so the old view stays visible
          // until there's something to replace it with.
          const replacing = awaitingFreshGenerationRef.current
          awaitingFreshGenerationRef.current = false
          sawLiveStreamRef.current = true
          setErrorMessage(null)
          applyToIndex(prev => {
            const nextSections = slotSection(replacing ? [] : prev.sections, payload.section_index, payload.section)
            return { ...prev, sections: nextSections, entryIds: entryIdsFromSections(nextSections), generating: true }
          })
          fetchMissingEntries(payload.section.mailbox_entry_ids)
          break
        }
        case "complete": {
          // Signal only — sections are already in the cache from the streamed `section`/score events.
          awaitingFreshGenerationRef.current = false
          // Reconcile to the authoritative cached order when the on-screen order can't be trusted as
          // final: a mid-sort partial (sentinel-ordered, must snap to the ranked result), or a
          // generation that finished while we were unmounted (`!sawLiveStream`) — a boosted hop away
          // and back strands the index at generating:true holding only a partial order, and the server
          // re-announces `complete` on resubscribe with no deltas following. A live stream this session
          // ran to completion already holds the full order, so it just clears generating (no refetch).
          // Refetching is safe *only* because `complete` means generation is done — the GET returns the
          // full order and can't clobber a live partial to empty. All gated on generating, so a
          // redundant `complete` on an already-settled view is a no-op.
          if (isGeneratingRef.current && (hydratedFromPartialRef.current || !sawLiveStreamRef.current)) {
            void reconcileRef.current()
            break
          }
          applyToIndex(prev => ({ ...prev, generating: false }))
          break
        }
        case "error": {
          // The view body switches to the error message; leave any prior sections in the cache
          // untouched (they're hidden behind the error) so a transient failure doesn't lose them.
          awaitingFreshGenerationRef.current = false
          applyToIndex(prev => ({ ...prev, generating: false }))
          setErrorMessage(payload.message)
          break
        }
        case "entry_scored": {
          // Ranked sort delta: record the score and re-order the single flat section. Leave the
          // prior list rendered until the rebuild swaps it in, mirroring the grouped fresh-boundary.
          awaitingFreshGenerationRef.current = false
          sawLiveStreamRef.current = true
          if (hydratedFromPartialRef.current) {
            // A server-computed partial (all candidates, sentinel-ordered) is on screen. Rebuilding
            // from the sparse post-refresh scores would shrink the list to just those ids, so hold
            // the partial order and reconcile to the authoritative one on `complete`.
            setErrorMessage(null)
            applyToIndex(prev => ({ ...prev, generating: true }))
            break
          }
          rankedScoresRef.current.set(payload.entry_id, { score: payload.score, rank: payload.rank })
          setErrorMessage(null)
          const nextSections = rankedSectionFromScores(rankedScoresRef.current)
          applyToIndex(prev => ({
            ...prev,
            sections: nextSections,
            entryIds: entryIdsFromSections(nextSections),
            generating: true,
          }))
          fetchMissingEntries([payload.entry_id])
          break
        }
        case "entries_scored": {
          // Batched sentinel tail: every candidate the LLM never scored, in one frame.
          awaitingFreshGenerationRef.current = false
          sawLiveStreamRef.current = true
          if (hydratedFromPartialRef.current) {
            setErrorMessage(null)
            applyToIndex(prev => ({ ...prev, generating: true }))
            break
          }
          payload.entry_ids.forEach((id, i) => {
            rankedScoresRef.current.set(id, { score: payload.score, rank: payload.ranks[i] })
          })
          setErrorMessage(null)
          const nextSections = rankedSectionFromScores(rankedScoresRef.current)
          applyToIndex(prev => ({
            ...prev,
            sections: nextSections,
            entryIds: entryIdsFromSections(nextSections),
            generating: true,
          }))
          fetchMissingEntries(payload.entry_ids)
          break
        }
        case "cache_expired":
        case "regenerating": {
          beginRegeneration()
          break
        }
        case "new_messages": {
          setNewMessagesCount(payload.count)
          break
        }
      }
    },
    [applyToIndex, beginRegeneration, fetchMissingEntries, resetGenerationWatchdog]
  )

  // mailbox_view identity is {view_id, user_id}. The new-messages baseline is read from the server's
  // own cache record, so nothing about the cache rides as a subscribe param.
  useChannel(
    active && userId
      ? { stream: ChannelStream.MAILBOX_VIEW, params: { view_id: active.channel_id, user_id: userId } }
      : null,
    ChannelEventResource.MAILBOX_VIEW,
    handleChannelMessage
  )

  // Keep the new-messages count live as mail arrives, rather than only the one-shot count at subscribe.
  // `mailbox_view_mode` routes the mailbox_sync handler to its count-only branch (no inbox-list refresh),
  // which counts against the view's server cache — so we just name the view; no cache state is sent.
  // Safe to share the user's mailbox_sync topic: in view mode the inbox-list subscription is off.
  const syncParams = useMemo<Record<string, string>>(() => {
    if (!active) return {}
    const params: Record<string, string> = { mailbox_view_mode: "true", view_id: active.channel_id }
    return params
  }, [active])

  const handleSyncMessage = useCallback((_action: ChannelEventAction, syncData: Record<string, unknown>) => {
    const payload = syncData as unknown as MailboxSyncPayload
    if (payload.type === "new_messages") setNewMessagesCount(payload.count)
  }, [])

  // mailbox_sync identity is just {user_id}; mailbox_view_mode/view_id ride as subscribe-time params
  // (the broadcast handler reads them via MailboxSyncParams).
  useChannel(
    active && userId
      ? { stream: ChannelStream.MAILBOX_SYNC, params: { user_id: userId }, extraParams: syncParams }
      : null,
    ChannelEventResource.MAILBOX_SYNC,
    handleSyncMessage
  )

  const findEntry = useCallback(
    (id: string): MailboxEntry | undefined => queryClient.getQueryData<MailboxViewEntriesData>(entriesKey)?.byId[id],
    [queryClient, entriesKey]
  )

  const applyOptimistic = useCallback(
    (id: string, patch: Partial<MailboxEntry>): MailboxEntry | undefined => {
      const previous = queryClient.getQueryData<MailboxViewEntriesData>(entriesKey)?.byId[id]
      if (!previous) return undefined
      const patched = { ...previous, ...patch, mutatedAt: Date.now() }
      applyToEntries(prev => (prev.byId[id] ? { ...prev, byId: { ...prev.byId, [id]: patched } } : prev))
      return previous
    },
    [queryClient, entriesKey, applyToEntries]
  )

  const rollback = useCallback(
    (previous: MailboxEntry) => {
      const restored = { ...previous, mutatedAt: undefined }
      applyToEntries(prev =>
        prev.byId[previous.id] ? { ...prev, byId: { ...prev.byId, [previous.id]: restored } } : prev
      )
    },
    [applyToEntries]
  )

  const mutations = useMailboxMutations({ findEntry, applyOptimistic, rollback })

  const createView = useCallback(
    async (params: { view_request: string; title?: string; layout?: MailboxViewLayout }) => {
      try {
        const result = await apiFetch<MailboxViewMutationResponse>("/api/mailbox_views", {
          method: "POST",
          body: JSON.stringify(params),
        })
        boundaryNavigate(result.redirect_to)
      } catch (e) {
        showFlash(toErrorMessage(e, "Couldn't create view."))
      }
    },
    [boundaryNavigate]
  )

  const updateView = useCallback(
    async (viewId: string, params: { view_request?: string; title?: string; layout?: MailboxViewLayout }) => {
      try {
        const result = await apiFetch<MailboxViewMutationResponse>(`/api/mailbox_views/${viewId}`, {
          method: "PATCH",
          body: JSON.stringify(params),
        })
        boundaryNavigate(result.redirect_to)
      } catch (e) {
        showFlash(toErrorMessage(e, "Couldn't update view."))
      }
    },
    [boundaryNavigate]
  )

  const refreshView = useCallback(
    async (viewId: string) => {
      try {
        // viewId is the active view's opaque id — a UUID for saved views or `template:<name>[:<goalId>]`
        // for built-in sorts. Encode it: the template form carries colons the server round-trips.
        await apiFetch(`/api/mailbox_views/${encodeURIComponent(viewId)}/refresh`, { method: "POST" })
        // The endpoint only drops the server cache and broadcasts nothing, so drive the
        // regeneration from here: reset the streaming state exactly as a `regenerating` event
        // would, then refetch the index — the cache miss restarts generation and the channel
        // streams the fresh sections in. Reloading the document instead is a hard navigation,
        // which strands the realm (#8744).
        beginRegeneration()
        setNewMessagesCount(0)
        await queryClient.invalidateQueries({ queryKey: indexKey })
      } catch (e) {
        showFlash(toErrorMessage(e, "Couldn't refresh view."))
      }
    },
    [beginRegeneration, queryClient, indexKey]
  )

  const deleteView = useCallback(
    async (viewId: string) => {
      try {
        await apiFetch(`/api/mailbox_views/${viewId}`, { method: "DELETE" })
        // Drop it from the dropdown in place — deleting a view/sort you aren't currently viewing
        // shouldn't reload the page.
        applyToIndex(prev => ({ ...prev, allViews: prev.allViews.filter(v => v.id !== viewId) }))
        // Deleting the view that's on screen leaves nothing to show, so fall back to the plain
        // inbox. The island doesn't load inbox entries while a view is active, so this one case
        // still needs a navigation.
        const current = queryClient.getQueryData<MailboxViewIndexData>(indexKey)
        if (current?.active?.kind === "view" && current.active.id === viewId) {
          boundaryNavigate("/")
        }
      } catch (e) {
        showFlash(toErrorMessage(e, "Couldn't delete view."))
      }
    },
    [applyToIndex, queryClient, indexKey, boundaryNavigate]
  )

  return {
    loading,
    active,
    allViews,
    sections,
    entriesById,
    hasMoreEntries,
    loadingMoreEntries,
    loadMoreEntries,
    isGenerating,
    isNotFound,
    hasGoalsForView,
    errorMessage,
    isCleared,
    newMessagesCount,
    eligibleEntryCount,
    consideredEntryCount,
    mutations,
    createView,
    updateView,
    refreshView,
    deleteView,
  }
}
