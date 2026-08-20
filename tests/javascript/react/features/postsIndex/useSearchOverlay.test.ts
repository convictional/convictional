import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))

import { useSearchOverlay } from "~/react/features/postsIndex/hooks/useSearchOverlay"
import { apiFetch } from "~/react/shared/apiFetch"
import type { SearchResponse, SearchResult } from "~/react/shared/searchResults"

const mockApiFetch = vi.mocked(apiFetch)

function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    id: "r1",
    title: "A post",
    author: "Alice",
    content_type: "post",
    category: "post",
    source_url: "/posts/r1",
    preview_content: "snippet",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    relevance_score: null,
    metadata: {},
    shared_with_me: false,
    ...overrides,
  }
}

function makeResponse(results: SearchResult[]): SearchResponse {
  return { results, query: "x", content_type: "post", hero_count: 0, next_cursor: null, has_more: false }
}

// `q` lives in the route now; the hook takes the committed query plus callbacks
// (the component owns the navigate that commits it and the result navigation).
function options(routeQuery = "") {
  return { routeQuery, onCommit: vi.fn(), onNavigateToResult: vi.fn() }
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe("useSearchOverlay", () => {
  test("starts closed with no initial query", () => {
    const { result } = renderHook(() => useSearchOverlay(options()))
    expect(result.current.isOpen).toBe(false)
    expect(result.current.searchActive).toBe(false)
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("opens and fetches /api/search?content_type=post past the 2-char gate, committing the query", async () => {
    vi.useFakeTimers()
    mockApiFetch.mockResolvedValue(makeResponse([makeResult()]))
    const opts = options()

    const { result } = renderHook(() => useSearchOverlay(opts))
    act(() => result.current.openSearch())

    act(() => result.current.setQuery("a"))
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    // One char → below the gate → no fetch (but the empty-ish commit still fires).
    expect(mockApiFetch).not.toHaveBeenCalled()

    act(() => result.current.setQuery("ab"))
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining("content_type=post"),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("q=ab"), expect.any(Object))
    expect(opts.onCommit).toHaveBeenCalledWith("ab")
  })

  test("fetches on mount when the route already carries a query", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([makeResult()]))

    const { result } = renderHook(() => useSearchOverlay(options("hello")))
    expect(result.current.isOpen).toBe(true)
    expect(result.current.query).toBe("hello")

    await waitFor(() => expect(result.current.results).toHaveLength(1))
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("q=hello"), expect.any(Object))
  })

  test("handleClose clears query, results, and commits an empty query", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([makeResult()]))
    const opts = options("hello")

    const { result } = renderHook(() => useSearchOverlay(opts))
    await waitFor(() => expect(result.current.results).toHaveLength(1))

    act(() => result.current.handleClose())
    expect(result.current.isOpen).toBe(false)
    expect(result.current.query).toBe("")
    expect(result.current.results).toHaveLength(0)
    expect(opts.onCommit).toHaveBeenCalledWith("")
  })

  test("commits the debounced query through onCommit", async () => {
    vi.useFakeTimers()
    mockApiFetch.mockResolvedValue(makeResponse([]))
    const opts = options()

    const { result } = renderHook(() => useSearchOverlay(opts))
    act(() => result.current.setQuery("term"))
    await act(async () => {
      vi.advanceTimersByTime(300)
    })
    expect(opts.onCommit).toHaveBeenCalledWith("term")
  })

  test("navigates to a keyboard-selected result", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([makeResult({ source_url: "/posts/r1" })]))
    const opts = options("hello")

    const { result } = renderHook(() => useSearchOverlay(opts))
    await waitFor(() => expect(result.current.results).toHaveLength(1))

    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault() {} } as never))
    act(() => result.current.handleKeyDown({ key: "Enter", preventDefault() {} } as never))
    expect(opts.onNavigateToResult).toHaveBeenCalledWith("/posts/r1")
  })
})
