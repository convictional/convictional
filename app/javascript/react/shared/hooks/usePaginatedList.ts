import { type Dispatch, type SetStateAction, useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { PaginatedResponse } from "~/react/shared/types"

interface PaginatedListOptions<T extends { id: string }, R extends PaginatedResponse> {
  // Build the request URL for a given cursor. A null cursor means page one.
  // Closes over the caller's filter state; list those in `deps` so a filter
  // change refetches page one.
  buildUrl: (cursor: string | null) => string
  // Pull the resource array out of the named envelope field (`d => d.meetings`).
  select: (response: R) => T[]
  // Refetch page one (resetting items/cursor/hasMore) whenever any of these
  // change, compared like a useEffect dependency array.
  deps?: readonly unknown[]
  // Side-channel for extra envelope fields (collection metadata, …).
  // Runs after each successful page is committed.
  onPage?: (response: R, context: { isLoadMore: boolean }) => void
}

interface PaginatedListResult<T> {
  items: T[]
  loading: boolean
  loadingMore: boolean
  error: boolean
  hasMore: boolean
  // Referentially stable for the hook's lifetime, so it is safe to pass as
  // LoadMoreSentinel's onIntersect without churning its IntersectionObserver.
  loadMore: () => void
  // Refetch page one. Stable. For reconnect handlers and "try again" buttons.
  // Resolves when the request settles, so callers can coalesce bursts.
  reload: () => Promise<void>
  // Escape hatch for optimistic mutations and channel merges. Stable.
  setItems: Dispatch<SetStateAction<T[]>>
}

function dedupe<T extends { id: string }>(existing: T[], incoming: T[]): T[] {
  const seen = new Set(existing.map(item => item.id))
  return [...existing, ...incoming.filter(item => !seen.has(item.id))]
}

// Consolidates the cursor-pagination boilerplate shared by the island list
// hooks: aborting the in-flight request, ignoring stale responses, tracking
// loading/error/hasMore, and de-duping appended pages. Feature hooks layer
// their URL building, filter state, optimistic mutations, and channel
// subscriptions on top via the options and the returned `setItems`/`reload`.
export function usePaginatedList<T extends { id: string }, R extends PaginatedResponse>({
  buildUrl,
  select,
  deps = [],
  onPage,
}: PaginatedListOptions<T, R>): PaginatedListResult<T> {
  const [items, setItems] = useState<T[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState(false)
  const [hasMore, setHasMore] = useState(false)

  const nextCursorRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)

  // Mirror the paging gates into refs so loadMore stays referentially stable.
  // A loadMore that changed identity on every loadingMore/hasMore toggle would
  // force LoadMoreSentinel's IntersectionObserver to re-observe the still-visible
  // sentinel, re-firing its callback and re-loading on a loop while a request
  // keeps failing.
  const loadingMoreRef = useRef(false)
  loadingMoreRef.current = loadingMore
  const hasMoreRef = useRef(false)
  hasMoreRef.current = hasMore

  // Keep the latest config in a ref so the stable fetchPage closure reads
  // current values without being rebuilt (which would break loadMore's identity).
  const configRef = useRef({ buildUrl, select, onPage })
  configRef.current = { buildUrl, select, onPage }

  const fetchPage = useCallback(async (cursor: string | null) => {
    const { buildUrl, select, onPage } = configRef.current
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const thisRequest = ++requestIdRef.current
    const isLoadMore = cursor != null

    if (isLoadMore) setLoadingMore(true)
    else setLoading(true)

    try {
      setError(false)
      const url = buildUrl(cursor)
      const data = await apiFetch<R>(url, { signal: controller.signal })
      if (requestIdRef.current !== thisRequest) return

      const incoming = select(data)
      if (isLoadMore) {
        setItems(prev => dedupe(prev, incoming))
      } else {
        setItems(incoming)
      }
      nextCursorRef.current = data.next_cursor
      setHasMore(data.has_more)
      onPage?.(data, { isLoadMore })
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      if (requestIdRef.current === thisRequest) setError(true)
    } finally {
      if (requestIdRef.current === thisRequest) {
        setLoading(false)
        setLoadingMore(false)
      }
    }
  }, [])

  // Reset and refetch page one when caller deps change. Clearing items first
  // prevents a stale list flashing under the new filter, and resetting the
  // cursor stops an in-view sentinel from paginating against the old cursor.
  useEffect(() => {
    nextCursorRef.current = null
    setHasMore(false)
    setItems([])
    void fetchPage(null)
    return () => abortRef.current?.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fetchPage, ...deps])

  const loadMore = useCallback(() => {
    if (loadingMoreRef.current || !hasMoreRef.current) return
    void fetchPage(nextCursorRef.current)
  }, [fetchPage])

  const reload = useCallback(() => fetchPage(null), [fetchPage])

  return { items, loading, loadingMore, error, hasMore, loadMore, reload, setItems }
}
