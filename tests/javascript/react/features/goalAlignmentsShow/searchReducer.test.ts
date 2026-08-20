import { describe, expect, test } from "vitest"

import { initialSearchState, searchReducer, type SearchState } from "~/react/features/goalAlignmentsShow/searchReducer"
import type { AlignableContent } from "~/react/features/goalAlignmentsShow/types"

function content(id: string): AlignableContent {
  return { id, title: `Content ${id}`, author: null, content_type: "post", source_url: `/c/${id}` }
}

const results = [content("a"), content("b"), content("c")]

function openState(overrides: Partial<SearchState> = {}): SearchState {
  return { ...initialSearchState, query: "qu", results, isOpen: true, ...overrides }
}

describe("searchReducer", () => {
  test("set_query below the threshold closes the menu and drops results", () => {
    const next = searchReducer(openState({ activeIndex: 1 }), { type: "set_query", query: "q" })
    expect(next).toMatchObject({ query: "q", results: [], isOpen: false, activeIndex: -1 })
  })

  test("set_query at/above the threshold keeps results but resets the highlight", () => {
    const next = searchReducer(openState({ activeIndex: 2 }), { type: "set_query", query: "quar" })
    expect(next).toMatchObject({ query: "quar", results, activeIndex: -1 })
  })

  test("highlight_next clamps at the last result and highlight_prev never goes below 0", () => {
    let state = openState({ activeIndex: -1 })
    state = searchReducer(state, { type: "highlight_next" }) // 0
    state = searchReducer(state, { type: "highlight_next" }) // 1
    state = searchReducer(state, { type: "highlight_next" }) // 2
    state = searchReducer(state, { type: "highlight_next" }) // clamps at 2
    expect(state.activeIndex).toBe(2)

    state = searchReducer(state, { type: "highlight_prev" }) // 1
    state = searchReducer(state, { type: "highlight_prev" }) // 0
    state = searchReducer(state, { type: "highlight_prev" }) // stays 0 (never -1)
    expect(state.activeIndex).toBe(0)
  })

  test("highlight_next on an empty result set is a no-op", () => {
    const empty = { ...initialSearchState, query: "qu", isOpen: true }
    expect(searchReducer(empty, { type: "highlight_next" })).toBe(empty)
  })

  test("select_active picks the highlighted result, closes the menu, and clears the highlight", () => {
    const next = searchReducer(openState({ activeIndex: 1 }), { type: "select_active" })
    expect(next.selected).toEqual(results[1])
    expect(next.isOpen).toBe(false)
    expect(next.activeIndex).toBe(-1)
  })

  test("select_active with no highlight is a no-op", () => {
    const state = openState({ activeIndex: -1 })
    expect(searchReducer(state, { type: "select_active" })).toBe(state)
  })

  test("select sets the chosen content and closes the menu", () => {
    const next = searchReducer(openState(), { type: "select", content: results[2] })
    expect(next).toMatchObject({ selected: results[2], isOpen: false, activeIndex: -1 })
  })

  test("clear_selection resets to the initial state", () => {
    const next = searchReducer(openState({ selected: results[0] }), { type: "clear_selection" })
    expect(next).toEqual(initialSearchState)
  })

  test("close hides the menu and clears the highlight without dropping results", () => {
    const next = searchReducer(openState({ activeIndex: 2 }), { type: "close" })
    expect(next).toMatchObject({ isOpen: false, activeIndex: -1, results })
  })
})
