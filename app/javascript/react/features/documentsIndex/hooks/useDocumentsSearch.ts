import { useQuery } from "@tanstack/react-query"
import type React from "react"
import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { SearchResponse, SearchResult } from "~/react/shared/searchResults"

const DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2
const EMPTY_RESULTS: SearchResult[] = []

function buildSearchUrl(query: string): string {
  const params = new URLSearchParams({ q: query, content_type: "document" })
  return `/api/search?${params.toString()}`
}

interface UseDocumentsSearchOptions {
  // The committed search query from the route's `q` search param. Drives the URL
  // (deep links, back/forward) and is the source of truth this hook syncs to.
  routeQuery: string
  // Push a debounced query into the URL (router navigation, replace).
  onCommit: (query: string) => void
  // Client-navigate to a result (Enter on a keyboard-selected row).
  onNavigateToResult: (sourceUrl: string) => void
}

// Search is its own Query path (keyed by ["documents", "search", q]) because it
// hits /api/search with a different shape than the browse list. The input value
// is local for responsiveness; a debounce commits it to the URL, and useQuery
// keys off the committed value so results follow the address bar (and recover on
// back/forward).
export function useDocumentsSearch({ routeQuery, onCommit, onNavigateToResult }: UseDocumentsSearchOptions) {
  const [query, setQueryState] = useState(routeQuery)
  const [committedQuery, setCommittedQuery] = useState(routeQuery)
  const [isOpen, setIsOpen] = useState(routeQuery.length > 0)
  const [selectedIndex, setSelectedIndex] = useState(-1)

  const debounceRef = useRef<number | null>(null)

  // External navigation (back/forward, a deep link) changes the route query out
  // from under us; resync the input and open the panel to match.
  useEffect(() => {
    if (routeQuery !== committedQuery) {
      setQueryState(routeQuery)
      setCommittedQuery(routeQuery)
      setSelectedIndex(-1)
      if (routeQuery.length > 0) setIsOpen(true)
    }
    // Only react to route changes; committedQuery is compared, not depended on.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeQuery])

  const searchQuery = useQuery({
    queryKey: ["documents", "search", committedQuery] as const,
    queryFn: ({ signal }) => apiFetch<SearchResponse>(buildSearchUrl(committedQuery), { signal }),
    enabled: committedQuery.length >= MIN_QUERY_LENGTH,
  })

  const results = searchQuery.data?.results ?? EMPTY_RESULTS
  const resultsRef = useRef(results)
  resultsRef.current = results
  const selectedIndexRef = useRef(selectedIndex)
  selectedIndexRef.current = selectedIndex

  const trimmed = query.trim()
  const searchActive = trimmed.length >= MIN_QUERY_LENGTH
  const isDebouncing = searchActive && trimmed !== committedQuery
  const loading = isDebouncing || (committedQuery.length >= MIN_QUERY_LENGTH && searchQuery.isFetching)
  const error = searchQuery.isError

  const commit = useCallback(
    (value: string) => {
      setCommittedQuery(value)
      setSelectedIndex(-1)
      onCommit(value)
    },
    [onCommit]
  )

  const setQuery = useCallback(
    (next: string) => {
      setQueryState(next)
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
      debounceRef.current = window.setTimeout(() => {
        debounceRef.current = null
        commit(next.trim())
      }, DEBOUNCE_MS)
    },
    [commit]
  )

  const handleClose = useCallback(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current)
      debounceRef.current = null
    }
    setIsOpen(false)
    setQueryState("")
    commit("")
  }, [commit])

  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    }
  }, [])

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
        if (selectedIndexRef.current >= 0) {
          setSelectedIndex(-1)
        } else if (query === "") {
          handleClose()
        }
      }
    },
    [handleClose, onNavigateToResult, query]
  )

  return {
    results,
    loading,
    error,
    query,
    isOpen,
    searchActive,
    selectedIndex,
    setQuery,
    setIsOpen,
    handleClose,
    handleKeyDown,
  }
}
