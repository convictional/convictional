import { useCallback, useEffect, useReducer, useRef } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { initialSearchState, MIN_QUERY_LENGTH, searchReducer } from "../searchReducer"
import type { AlignableContent, AlignableContentListResponse } from "../types"

const DEBOUNCE_MS = 300

// Debounced org-wide content search for the add-alignment form. Wires the pure
// searchReducer to a debounced GET /api/goal_alignments/lookup (not goal-scoped —
// see PR-1 post-review revisions) and exposes keyboard-nav dispatchers.
export function useContentSearch() {
  const [state, dispatch] = useReducer(searchReducer, initialSearchState)
  // Monotonic request id so a slow earlier response can't overwrite a newer one.
  const requestId = useRef(0)

  useEffect(() => {
    if (state.query.length < MIN_QUERY_LENGTH || state.selected) return

    const id = ++requestId.current
    const timer = setTimeout(() => {
      apiFetch<AlignableContentListResponse>(`/api/goal_alignments/lookup?q=${encodeURIComponent(state.query)}`)
        .then(data => {
          if (id === requestId.current) dispatch({ type: "results_loaded", results: data.results })
        })
        .catch(() => {
          if (id === requestId.current) dispatch({ type: "results_loaded", results: [] })
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(timer)
  }, [state.query, state.selected])

  const setQuery = useCallback((query: string) => dispatch({ type: "set_query", query }), [])
  const highlightNext = useCallback(() => dispatch({ type: "highlight_next" }), [])
  const highlightPrev = useCallback(() => dispatch({ type: "highlight_prev" }), [])
  const selectActive = useCallback(() => dispatch({ type: "select_active" }), [])
  const select = useCallback((content: AlignableContent) => dispatch({ type: "select", content }), [])
  const clearSelection = useCallback(() => dispatch({ type: "clear_selection" }), [])
  const close = useCallback(() => dispatch({ type: "close" }), [])

  return { state, setQuery, highlightNext, highlightPrev, selectActive, select, clearSelection, close }
}
