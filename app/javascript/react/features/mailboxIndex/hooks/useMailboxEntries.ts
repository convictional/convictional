import { keepPreviousData, useInfiniteQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import { getChannelsClient } from "~/channels/client"
import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import {
  type MailboxEntriesData,
  appendNextPage,
  mailboxEntriesQueryKey,
  mailboxEntriesQueryOptions,
  mailboxEntriesUrl,
  shouldShowEntry,
} from "~/react/shared/queries/mailboxEntries"
import { type ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

import { localMutationWins } from "../optimisticMerge"
import type {
  MailboxEntry,
  MailboxEntryListItem,
  MailboxEntryListResponse,
  MailboxSort,
  MailboxSyncPayload,
  MailboxView,
} from "../types"
import { type MailboxMutations, useMailboxMutations } from "./useMailboxMutations"

// Channel-merge rule (load-bearing): when a `mailbox_sync` push (or a reconnect
// refetch) arrives, keep a local entry while its optimistic `mutatedAt` stamp is
// recent (a same-clock recency window against the browser's now). This prevents
// in-flight optimistic toggles from being clobbered by a concurrent channel push.
// Without it, archiving an entry while the server is mid-broadcast would briefly
// un-archive it on screen.
function preserveMutated(incoming: MailboxEntryListItem[], previous: MailboxEntry[]): MailboxEntry[] {
  const nowMs = Date.now()
  const previousById = new Map(previous.map(entry => [entry.id, entry]))
  return incoming.map(item => {
    const local = previousById.get(item.id)
    return localMutationWins(local, nowMs) ? local : item
  })
}

interface FetchOptions {
  // When true, merge the response with current first-page state, keeping any
  // local entry whose optimistic `mutatedAt` stamp is still recent (within
  // `OPTIMISTIC_GUARD_MS` of now). Used by the WS reconnect / subscription
  // re-arm paths so an in-flight optimistic mutation isn't clobbered by the refetch.
  keepMutated?: boolean
}

export interface UseMailboxEntriesResult {
  entries: MailboxEntry[]
  visibleEntries: MailboxEntry[]
  loading: boolean
  loadingMore: boolean
  error: boolean
  hasMore: boolean
  hasLoadedMore: boolean
  loadMore: () => void
  syncedAt: string
  resetToFirstPage: () => void
  mutations: MailboxMutations
}

export interface UseMailboxEntriesOptions {
  // When false, the hook skips the inbox list fetch entirely. Used by
  // MailboxIndex when a mailbox view is active: the visible entries come from
  // useMailboxView.entriesById instead, so fetching page 1 of the inbox is
  // wasted work. This flag also gates the channel subscription (the stream is
  // null when disabled), and it disables the *fetch*.
  enabled?: boolean
}

export function useMailboxEntries(
  userId: string | null,
  view: MailboxView,
  sort: MailboxSort,
  { enabled = true }: UseMailboxEntriesOptions = {}
): UseMailboxEntriesResult {
  const queryClient = useQueryClient()
  // view/sort identify the cache entry: a change is a new key, so the manual
  // reload-on-change effect the old hook carried is gone. (In MailboxIndex these
  // are fixed per mount; a view switch is a full navigation/remount.)
  const queryKey = useMemo(() => mailboxEntriesQueryKey(view, sort), [view, sort])

  const buildUrl = useCallback((cursor: string | null) => mailboxEntriesUrl(view, sort, cursor), [view, sort])

  const query = useInfiniteQuery({
    ...mailboxEntriesQueryOptions(view, sort),
    enabled,
    // Keep the previous list on screen across a view/sort key change instead of
    // blanking to a spinner — mirrors the old hook keeping firstPage visible
    // during a reload.
    placeholderData: keepPreviousData,
  })

  const { data, hasNextPage, isLoading, isError } = query

  // Local, because pages are appended by hand (appendNextPage, see below) rather than
  // by fetchNextPage, so there's no isFetchingNextPage to read.
  const [loadingMore, setLoadingMore] = useState(false)

  const entries = useMemo<MailboxEntry[]>(() => data?.pages.flatMap(page => page.entries) ?? [], [data])
  const visibleEntries = useMemo(() => entries.filter(entry => shouldShowEntry(entry, view)), [entries, view])

  // Pages 2+ are frozen while the user is scrolled down (only page 1 takes live
  // channel merges, see handleChannelMessage), so the tail drifts stale. This gates
  // the list's top-of-list sentinel, which calls resetToFirstPage to collapse that
  // stale tail once the user settles back at the live region.
  const hasLoadedMore = (data?.pages.length ?? 0) > 1

  // Stable fallback until the first page lands; matches the old useState initializer.
  const [fallbackSyncedAt] = useState(() => new Date().toISOString())
  const syncedAt = data?.pages[0]?.synced_at ?? fallbackSyncedAt

  // Merge-aware page-1 refetch: fetch page 1 out-of-band and write it with
  // setQueryData, collapsing to a single authoritative page (pages 2+ dropped,
  // as the old hook reset laterPages to []). With `keepMutated`, an in-flight
  // optimistic mutation survives the refetch. We never invalidateQueries here:
  // invalidate has no merge hook and its raw refetch would race and clobber the
  // optimistic state. setQueryData only writes once the response lands, so the
  // prior list stays visible (no spinner flash).
  //
  // The AbortController (abortRef) restores the old hook's abort behavior: each
  // call aborts any prior in-flight page-1 refetch, and the unmount cleanup below
  // aborts the last one. Without it, two overlapping refetches (e.g. a WS
  // reconnect coinciding with a scroll-to-top reset) resolve in completion order
  // and a slower/older response clobbers fresher data; and a refetch that resolves
  // after unmount would write stale data into the shared (cross-mount) query cache.
  // An aborted apiFetch rejects with AbortError, swallowed by each caller's
  // `.catch(() => {})`, so no setQueryData runs for a superseded request.
  const abortRef = useRef<AbortController | null>(null)
  const refetchFirstPage = useCallback(
    async (options: FetchOptions = {}) => {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller
      const response = await apiFetch<MailboxEntryListResponse>(buildUrl(null), { signal: controller.signal })
      queryClient.setQueryData<MailboxEntriesData>(queryKey, old => {
        const previousFirst = old?.pages[0]?.entries ?? []
        const entries = options.keepMutated ? preserveMutated(response.entries, previousFirst) : response.entries
        return { pages: [{ ...response, entries }], pageParams: [null] }
      })
    },
    [buildUrl, queryClient, queryKey]
  )

  // Abort any in-flight page-1 refetch on unmount so its setQueryData can't write
  // stale data into the shared cache after this island is gone.
  useEffect(() => () => abortRef.current?.abort(), [])

  // Refetch on websocket reconnect to recover any mailbox_sync broadcasts missed
  // while disconnected (broadcasts are not replayed by the server — the
  // `on_subscribe` handler only accepts the channel). Same pattern as useChatsData.
  useEffect(() => {
    if (!enabled) return
    const client = getChannelsClient()
    if (!client) return
    const onReconnect = () => {
      void refetchFirstPage({ keepMutated: true }).catch(() => {})
    }
    client.on("reconnected", onReconnect)
    return () => client.off("reconnected", onReconnect)
  }, [enabled, refetchFirstPage])

  // Subscription re-arm catch-up (SPA navigation remount). When this component
  // remounts within gcTime, its channel subscription was unwired while unmounted
  // and missed pushes; staleTime:Infinity + refetchOnMount:false means
  // useInfiniteQuery won't refetch and no "reconnected" fires (the socket never
  // dropped). A warm cache at mount time is exactly that case, so run the same
  // merge-aware page-1 refetch the reconnect path uses — never a plain
  // invalidate, same clobber reason. A cold first mount has no cached data here
  // (the queryFn's fetch hasn't resolved yet), so it's skipped and the initial
  // useInfiniteQuery fetch covers it. The ref makes this fire once per mount.
  const didMountCatchUpRef = useRef(false)
  useEffect(() => {
    if (!enabled || didMountCatchUpRef.current) return
    didMountCatchUpRef.current = true
    if (queryClient.getQueryData(queryKey) !== undefined) {
      void refetchFirstPage({ keepMutated: true }).catch(() => {})
    }
  }, [enabled, queryClient, queryKey, refetchFirstPage])

  const loadMore = useCallback(() => {
    if (loadingMore || isLoading || !hasNextPage) return
    setLoadingMore(true)
    void appendNextPage(queryClient, view, sort)
      .catch(() => {})
      .finally(() => setLoadingMore(false))
  }, [loadingMore, isLoading, hasNextPage, queryClient, view, sort])

  const resetToFirstPage = useCallback(() => {
    void refetchFirstPage().catch(() => {})
  }, [refetchFirstPage])

  const handleChannelMessage = useCallback(
    (_action: ChannelEventAction, data: Record<string, unknown>) => {
      const payload = data as unknown as MailboxSyncPayload
      if (payload.type !== "entries") return
      // Page-1 only merge: live updates replace the first-page slice. Pages 2+
      // stay frozen so the list doesn't reorder under a user who has scrolled
      // past the live region.
      queryClient.setQueryData<MailboxEntriesData>(queryKey, old => {
        if (!old || old.pages.length === 0) return old
        const first = old.pages[0]
        const merged = {
          ...first,
          synced_at: payload.synced_at,
          entries: preserveMutated(payload.entries, first.entries),
        }
        return { ...old, pages: [merged, ...old.pages.slice(1)] }
      })
    },
    [queryClient, queryKey]
  )

  useChannel(
    userId && enabled
      ? { stream: ChannelStream.MAILBOX_SYNC, params: { user_id: userId }, extraParams: { view, sort } }
      : null,
    ChannelEventResource.MAILBOX_SYNC,
    handleChannelMessage
  )

  // --- Optimistic mutations ---
  //
  // The optimistic engine (snapshot → apply → rollback) lives in
  // useMailboxMutations, shared with useMailboxView. We back its read/apply/
  // rollback primitives with the Query cache here instead of local useState, so
  // mutatedAt (stamped by applyOptimistic) lands on the cached entry the
  // channel-merge rule keys on.

  const findEntry = useCallback(
    (id: string): MailboxEntry | undefined => {
      const cached = queryClient.getQueryData<MailboxEntriesData>(queryKey)
      return cached?.pages.flatMap(page => page.entries).find(entry => entry.id === id)
    },
    [queryClient, queryKey]
  )

  const applyOptimistic = useCallback(
    (id: string, patch: Partial<MailboxEntry>): MailboxEntry | undefined => {
      let changed: MailboxEntry | undefined
      const stamp = Date.now()
      queryClient.setQueryData<MailboxEntriesData>(queryKey, old => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map(page => ({
            ...page,
            entries: page.entries.map(entry => {
              if (entry.id !== id) return entry
              changed = { ...entry, ...patch, mutatedAt: stamp }
              return changed
            }),
          })),
        }
      })
      return changed
    },
    [queryClient, queryKey]
  )

  const rollback = useCallback(
    (previous: MailboxEntry) => {
      const restored = { ...previous, mutatedAt: undefined }
      queryClient.setQueryData<MailboxEntriesData>(queryKey, old => {
        if (!old) return old
        return {
          ...old,
          pages: old.pages.map(page => ({
            ...page,
            entries: page.entries.map(entry => (entry.id === previous.id ? restored : entry)),
          })),
        }
      })
    },
    [queryClient, queryKey]
  )

  const mutations = useMailboxMutations({ findEntry, applyOptimistic, rollback })

  return {
    entries,
    visibleEntries,
    loading: isLoading,
    loadingMore,
    error: isError,
    hasMore: hasNextPage,
    hasLoadedMore,
    loadMore,
    syncedAt,
    resetToFirstPage,
    mutations,
  }
}
