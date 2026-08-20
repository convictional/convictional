import { renderHook, act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { SearchResponse } from "../../../../../app/javascript/react/features/searchResults/types"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: null
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = null
    }
  },
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { useSearchResults } from "../../../../../app/javascript/react/features/searchResults/hooks/useSearchResults"

const mockApiFetch = vi.mocked(apiFetch)

function makeSearchResponse(overrides: Partial<SearchResponse> = {}): SearchResponse {
  return {
    results: [],
    query: "test",
    content_type: null,
    ...overrides,
  }
}

const replaceStateSpy = vi.fn()

beforeEach(() => {
  mockApiFetch.mockReset()

  Object.defineProperty(window, "location", {
    value: { search: "", href: "" },
    writable: true,
    configurable: true,
  })

  window.history.replaceState = replaceStateSpy
})

afterEach(() => {
  vi.clearAllMocks()
  vi.useRealTimers()
})

describe("useSearchResults", () => {
  test("fetches on mount when initial query >= 2 chars", async () => {
    const response = makeSearchResponse({
      results: [
        {
          id: "1",
          title: "Test Result",
          author: "Alice",
          content_type: "document",
          category: "document",
          source_url: "/docs/1",
          preview_content: "Some preview",
          created_at: "2026-04-14T00:00:00Z",
          updated_at: "2026-04-14T00:00:00Z",
        },
      ],
      query: "test query",
    })
    mockApiFetch.mockResolvedValue(response as any)

    const { result } = renderHook(() => useSearchResults("test query"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.results).toHaveLength(1)
    expect(result.current.results[0].title).toBe("Test Result")
    expect(result.current.error).toBe(false)
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/search?q=test+query"),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
  })

  test("does not fetch when query < 2 chars", async () => {
    const { result } = renderHook(() => useSearchResults("a"))

    // Short query should not trigger a fetch — give a tick for the effect to run
    await act(async () => {})

    expect(result.current.loading).toBe(false)
    expect(result.current.results).toHaveLength(0)
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("does not fetch with empty query", async () => {
    const { result } = renderHook(() => useSearchResults(""))

    await act(async () => {})

    expect(result.current.loading).toBe(false)
    expect(result.current.results).toHaveLength(0)
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("debounces query changes", async () => {
    vi.useFakeTimers()
    mockApiFetch.mockResolvedValue(makeSearchResponse() as any)

    const { result } = renderHook(() => useSearchResults(""))

    act(() => {
      result.current.setQuery("hello")
    })

    // Not called yet (debouncing)
    expect(mockApiFetch).not.toHaveBeenCalled()

    // Advance past debounce period
    await act(async () => {
      vi.advanceTimersByTime(300)
    })

    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining("q=hello"),
      expect.any(Object)
    )
  })

  test("fetches immediately on content type filter change", async () => {
    const response = makeSearchResponse()
    mockApiFetch.mockResolvedValue(response as any)

    const { result } = renderHook(() => useSearchResults("test query"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    mockApiFetch.mockClear()
    mockApiFetch.mockResolvedValue(makeSearchResponse() as any)

    act(() => {
      result.current.setContentType("document")
    })

    // Should fetch immediately, no debounce
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining("content_type=document"),
      expect.any(Object)
    )
  })

  test("sets error state on fetch failure", async () => {
    mockApiFetch.mockRejectedValue(new Error("Network error"))

    const { result } = renderHook(() => useSearchResults("test query"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe(true)
    expect(result.current.results).toHaveLength(0)
  })

  test("updates browser URL via replaceState", async () => {
    mockApiFetch.mockResolvedValue(makeSearchResponse() as any)

    renderHook(() => useSearchResults("test query"))

    await waitFor(() => {
      expect(replaceStateSpy).toHaveBeenCalled()
    })

    expect(replaceStateSpy).toHaveBeenCalledWith(null, "", "/search?q=test+query")
  })

  test("parses initial state from URL params", async () => {
    Object.defineProperty(window, "location", {
      value: { search: "?q=url+query&content_type=meeting", href: "" },
      writable: true,
      configurable: true,
    })
    mockApiFetch.mockResolvedValue(makeSearchResponse() as any)

    const { result } = renderHook(() => useSearchResults("fallback"))

    // URL params take precedence over initialQuery prop
    expect(result.current.query).toBe("url query")
    expect(result.current.contentType).toBe("meeting")

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        expect.stringContaining("q=url+query"),
        expect.any(Object)
      )
    })
  })
})
