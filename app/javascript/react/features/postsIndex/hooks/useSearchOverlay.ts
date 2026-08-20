import type React from "react"
import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { SearchResponse, SearchResult } from "~/react/shared/searchResults"

const DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2
const EMPTY_RESULTS: SearchResult[] = []

function buildApiUrl(query: string): string {
  const params = new URLSearchParams()
  params.set("q", query)
  params.set("content_type", "post")
  return `/api/search?${params.toString()}`
}

interface UseSearchOverlayOptions {
  // The committed query from the route's `q` search param — the source of truth
  // for deep links and back/forward. The overlay syncs its input to it.
  routeQuery: string
  // Push the committed query into the URL (router navigation, replace).
  onCommit: (query: string) => void
  // Navigate to a keyboard-selected result. Results are server-resolved gid links
  // (not /posts/{id}), so this is a full-document load the gid_redirect resolves.
  onNavigateToResult: (sourceUrl: string) => void
}

// The posts search overlay: a full-surface takeover backed by the shared
// GET /api/search?content_type=post, rendering lightweight result rows (not full
// post cards). Independent of usePostsData — search has no cursor and is
// filter-agnostic. The `q` param lives in the route (the router owns history);
// the input value is local for responsiveness, debounced into the URL.
export function useSearchOverlay({ routeQuery, onCommit, onNavigateToResult }: UseSearchOverlayOptions) {
  const [query, setQuery] = useState(routeQuery)
  const [committedQuery, setCommittedQuery] = useState(routeQuery)
  const [isOpen, setIsOpen] = useState(routeQuery.length > 0)
  const [results, setResults] = useState<SearchResult[]>(EMPTY_RESULTS)
  const [fetching, setFetching] = useState(false)
  const [debouncing, setDebouncing] = useState(false)
  const [error, setError] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(-1)

  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)
  const debounceRef = useRef<number | null>(null)
  const queryRef = useRef(query)
  const resultsRef = useRef(results)
  const selectedIndexRef = useRef(selectedIndex)
  queryRef.current = query
  resultsRef.current = results
  selectedIndexRef.current = selectedIndex

  const searchActive = query.length >= MIN_QUERY_LENGTH

  // Fetch results for an already-committed query. Clears when below the minimum.
  const runFetch = useCallback(async (q: string) => {
    abortRef.current?.abort()

    if (q.length < MIN_QUERY_LENGTH) {
      setResults(EMPTY_RESULTS)
      setFetching(false)
      setDebouncing(false)
      setError(false)
      return
    }

    const controller = new AbortController()
    abortRef.current = controller
    const thisRequest = ++requestIdRef.current

    setFetching(true)
    setDebouncing(false)
    setError(false)

    try {
      const data = await apiFetch<SearchResponse>(buildApiUrl(q), { signal: controller.signal })
      if (requestIdRef.current !== thisRequest) return
      setResults(data.results)
      setSelectedIndex(-1)
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      if (requestIdRef.current === thisRequest) {
        setError(true)
        setResults(EMPTY_RESULTS)
      }
    } finally {
      if (requestIdRef.current === thisRequest) setFetching(false)
    }
  }, [])

  // Commit a query to the URL and fetch it. Setting committedQuery before the
  // navigate lands keeps the route-resync effect from re-firing on our own write.
  const commit = useCallback(
    (q: string) => {
      setCommittedQuery(q)
      onCommit(q)
      void runFetch(q)
    },
    [onCommit, runFetch]
  )

  // Mount-only: fetch once for a deep-linked `?q=` and clean up on unmount.
  // `runFetch` is a stable callback (empty deps); listing it would just make this
  // re-run on every render, so the exhaustive-deps check is suppressed here.
  useEffect(() => {
    if (routeQuery.length >= MIN_QUERY_LENGTH) void runFetch(routeQuery)
    return () => {
      abortRef.current?.abort()
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Back/forward (or a deep link) changes the route `q` out from under us. Resync
  // the overlay to it: reopen+refetch if it carries a query, otherwise stay put.
  // Guarded on committedQuery so our own commit() writes don't re-trigger a fetch.
  useEffect(() => {
    if (routeQuery === committedQuery) return
    setQuery(routeQuery)
    setCommittedQuery(routeQuery)
    setSelectedIndex(-1)
    if (routeQuery.length > 0) setIsOpen(true)
    void runFetch(routeQuery)
    // Only react to route changes; committedQuery is compared, not depended on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeQuery])

  const handleQueryChange = useCallback(
    (newQuery: string) => {
      setQuery(newQuery)
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
      setDebouncing(newQuery.length >= MIN_QUERY_LENGTH)
      debounceRef.current = window.setTimeout(() => {
        debounceRef.current = null
        commit(newQuery)
      }, DEBOUNCE_MS)
    },
    [commit]
  )

  const openSearch = useCallback(() => setIsOpen(true), [])

  const handleClose = useCallback(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    abortRef.current?.abort()
    setIsOpen(false)
    setQuery("")
    setResults(EMPTY_RESULTS)
    setSelectedIndex(-1)
    setError(false)
    setFetching(false)
    setDebouncing(false)
    setCommittedQuery("")
    onCommit("")
  }, [onCommit])

  const loading = fetching || debouncing

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex(prev => Math.min(prev + 1, resultsRef.current.length - 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex(prev => (prev <= 0 ? -1 : prev - 1))
      } else if (e.key === "Enter" && selectedIndexRef.current >= 0) {
        e.preventDefault()
        const result = resultsRef.current[selectedIndexRef.current]
        if (result) onNavigateToResult(result.source_url)
      } else if (e.key === "Escape") {
        if (selectedIndexRef.current >= 0) setSelectedIndex(-1)
        else if (queryRef.current === "") handleClose()
      }
    },
    [handleClose, onNavigateToResult]
  )

  return {
    results,
    loading,
    error,
    query,
    isOpen,
    searchActive,
    selectedIndex,
    setQuery: handleQueryChange,
    openSearch,
    handleClose,
    handleKeyDown,
  }
}
