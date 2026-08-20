import type { AlignableContent } from "./types"

// Minimum characters before a search fires. Mirrors the API's `q` min_length.
export const MIN_QUERY_LENGTH = 2

export interface SearchState {
  query: string
  results: AlignableContent[]
  // Whether the results menu is open.
  isOpen: boolean
  // Index of the keyboard-highlighted result, or -1 for none.
  activeIndex: number
  // The chosen content, or null while still searching.
  selected: AlignableContent | null
}

export const initialSearchState: SearchState = {
  query: "",
  results: [],
  isOpen: false,
  activeIndex: -1,
  selected: null,
}

export type SearchAction =
  | { type: "set_query"; query: string }
  | { type: "results_loaded"; results: AlignableContent[] }
  | { type: "highlight_next" }
  | { type: "highlight_prev" }
  | { type: "select_active" }
  | { type: "select"; content: AlignableContent }
  | { type: "clear_selection" }
  | { type: "close" }

// Pure reducer for the search/keyboard-nav state: a single testable transition
// function covering query changes, highlight movement, selection, and close.
export function searchReducer(state: SearchState, action: SearchAction): SearchState {
  switch (action.type) {
    case "set_query": {
      // Below the threshold the menu closes and prior results are dropped, so a
      // stale list can't be highlighted or selected.
      if (action.query.length < MIN_QUERY_LENGTH) {
        return { ...state, query: action.query, results: [], isOpen: false, activeIndex: -1 }
      }
      return { ...state, query: action.query, activeIndex: -1 }
    }
    case "results_loaded":
      return { ...state, results: action.results, isOpen: true, activeIndex: -1 }
    case "highlight_next": {
      if (state.results.length === 0) return state
      return { ...state, activeIndex: Math.min(state.activeIndex + 1, state.results.length - 1) }
    }
    case "highlight_prev": {
      // Arrow-up only moves while past the first row; it never unsets to -1.
      if (state.activeIndex <= 0) return state
      return { ...state, activeIndex: state.activeIndex - 1 }
    }
    case "select_active": {
      if (state.activeIndex < 0 || state.activeIndex >= state.results.length) return state
      return { ...state, selected: state.results[state.activeIndex], isOpen: false, activeIndex: -1 }
    }
    case "select":
      return { ...state, selected: action.content, isOpen: false, activeIndex: -1 }
    case "clear_selection":
      return { ...initialSearchState }
    case "close":
      return { ...state, isOpen: false, activeIndex: -1 }
    default:
      return state
  }
}
