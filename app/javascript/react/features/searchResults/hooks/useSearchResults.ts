import type React from "react"
import { useCallback, useEffect, useRef, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { resultNavigationUrl, type SearchResponse, type SearchResult } from "~/react/shared/searchResults"
import type { ContentTypeFilter } from "../types"

const DEBOUNCE_MS = 300
const MIN_QUERY_LENGTH = 2
const EMPTY_RESULTS: SearchResult[] = []

function parseInitialState(initialQuery: string): {
  query: string
  contentType: ContentTypeFilter | null
} {
  const params = new URLSearchParams(window.location.search)
  return {
    query: params.get("q") || initialQuery || "",
    contentType: (params.get("content_type") as ContentTypeFilter) || null,
  }
}

function buildApiUrl(query: string, contentType: ContentTypeFilter | null): string {
  const params = new URLSearchParams()
  params.set("q", query)
  if (contentType) params.set("content_type", contentType)
  return `/api/search?${params.toString()}`
}

function syncBrowserUrl(query: string, contentType: ContentTypeFilter | null): void {
  const params = new URLSearchParams()
  if (query) params.set("q", query)
  if (contentType) params.set("content_type", contentType)
  const qs = params.toString()
  const url = `/search${qs ? `?${qs}` : ""}`
  window.history.replaceState(null, "", url)
}

export function useSearchResults(initialQuery: string) {
  const initial = useRef(parseInitialState(initialQuery)).current

  const [results, setResults] = useState<SearchResult[]>(EMPTY_RESULTS)
  const [heroCount, setHeroCount] = useState(0)
  const [fetching, setFetching] = useState(false)
  const [debouncing, setDebouncing] = useState(false)
  const [error, setError] = useState(false)
  const [query, setQuery] = useState(initial.query)
  const [contentType, setContentType] = useState<ContentTypeFilter | null>(initial.contentType)
  const [selectedIndex, setSelectedIndex] = useState(-1)

  const abortRef = useRef<AbortController | null>(null)
  const requestIdRef = useRef(0)
  const debounceRef = useRef<number | null>(null)
  const queryRef = useRef(query)
  const contentTypeRef = useRef(contentType)
  const resultsRef = useRef(results)
  const selectedIndexRef = useRef(selectedIndex)
  queryRef.current = query
  contentTypeRef.current = contentType
  resultsRef.current = results
  selectedIndexRef.current = selectedIndex

  const fetchResults = useCallback(async (q: string, ct: ContentTypeFilter | null) => {
    abortRef.current?.abort()

    syncBrowserUrl(q, ct)

    if (q.length < MIN_QUERY_LENGTH) {
      setResults(EMPTY_RESULTS)
      setHeroCount(0)
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
      const data = await apiFetch<SearchResponse>(buildApiUrl(q, ct), {
        signal: controller.signal,
      })

      if (requestIdRef.current !== thisRequest) return

      setResults(data.results)
      setHeroCount(data.hero_count)
      setSelectedIndex(-1)
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") return
      if (requestIdRef.current === thisRequest) {
        setError(true)
        setResults(EMPTY_RESULTS)
        setHeroCount(0)
      }
    } finally {
      if (requestIdRef.current === thisRequest) {
        setFetching(false)
      }
    }
  }, [])

  useEffect(() => {
    fetchResults(initial.query, initial.contentType)
    return () => {
      abortRef.current?.abort()
      if (debounceRef.current !== null) window.clearTimeout(debounceRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleQueryChange = useCallback(
    (newQuery: string) => {
      setQuery(newQuery)

      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current)
      }

      if (newQuery.length >= MIN_QUERY_LENGTH) {
        setDebouncing(true)
      }

      debounceRef.current = window.setTimeout(() => {
        debounceRef.current = null
        fetchResults(newQuery, contentTypeRef.current)
      }, DEBOUNCE_MS)
    },
    [fetchResults]
  )

  const handleContentTypeChange = useCallback(
    (newType: ContentTypeFilter | null) => {
      setContentType(newType)

      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current)
        debounceRef.current = null
      }

      fetchResults(queryRef.current, newType)
    },
    [fetchResults]
  )

  const loading = fetching || debouncing

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setSelectedIndex(prev => Math.min(prev + 1, resultsRef.current.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setSelectedIndex(prev => (prev <= 0 ? -1 : prev - 1))
    } else if (e.key === "Enter" && selectedIndexRef.current >= 0) {
      e.preventDefault()
      const result = resultsRef.current[selectedIndexRef.current]
      if (result) window.open(resultNavigationUrl(result), "_blank", "noopener,noreferrer")
    } else if (e.key === "Escape") {
      setSelectedIndex(-1)
    }
  }, [])

  return {
    results,
    heroCount,
    loading,
    error,
    query,
    contentType,
    selectedIndex,
    setQuery: handleQueryChange,
    setContentType: handleContentTypeChange,
    handleKeyDown,
  }
}
