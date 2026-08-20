import { act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { useDocumentsSearch } from "../../../../../app/javascript/react/features/documentsIndex/hooks/useDocumentsSearch"
import type { SearchResponse, SearchResult } from "../../../../../app/javascript/react/shared/searchResults"
import { renderHookWithClient } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)

function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    id: "r1",
    title: "Result",
    author: null,
    content_type: "document",
    category: "document",
    source_url: "/documents/r1",
    preview_content: null,
    created_at: "2026-04-21T09:00:00Z",
    updated_at: "2026-04-21T09:00:00Z",
    relevance_score: null,
    metadata: {},
    shared_with_me: false,
    ...overrides,
  }
}

function makeResponse(results: SearchResult[]): SearchResponse {
  return { results, query: "q", content_type: "document" }
}

const noop = () => {}

beforeEach(() => mockApiFetch.mockReset())
afterEach(() => vi.clearAllMocks())

describe("useDocumentsSearch", () => {
  test("debounced typing commits the trimmed query", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([]))
    const onCommit = vi.fn()

    const { result } = renderHookWithClient(() =>
      useDocumentsSearch({ routeQuery: "", onCommit, onNavigateToResult: noop })
    )

    act(() => result.current.setQuery("  plan  "))
    await waitFor(() => expect(onCommit).toHaveBeenCalledWith("plan"))
  })

  test("fetches and exposes results for a committed query", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([makeResult({ title: "Found" })]))

    const { result } = renderHookWithClient(() =>
      useDocumentsSearch({ routeQuery: "plan", onCommit: noop, onNavigateToResult: noop })
    )

    await waitFor(() => expect(result.current.results).toHaveLength(1))
    expect(mockApiFetch).toHaveBeenCalledWith(expect.stringContaining("content_type=document"), expect.any(Object))
  })

  test("handleClose clears the query and commits empty", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([]))
    const onCommit = vi.fn()

    const { result } = renderHookWithClient(() =>
      useDocumentsSearch({ routeQuery: "plan", onCommit, onNavigateToResult: noop })
    )

    act(() => result.current.handleClose())
    expect(result.current.isOpen).toBe(false)
    expect(onCommit).toHaveBeenCalledWith("")
  })

  test("Enter on a keyboard-selected result navigates to it", async () => {
    mockApiFetch.mockResolvedValue(makeResponse([makeResult({ source_url: "/documents/r1" })]))
    const onNavigateToResult = vi.fn()

    const { result } = renderHookWithClient(() =>
      useDocumentsSearch({ routeQuery: "plan", onCommit: noop, onNavigateToResult })
    )
    await waitFor(() => expect(result.current.results).toHaveLength(1))

    const keyEvent = (key: string) => ({ key, preventDefault: vi.fn() }) as unknown as React.KeyboardEvent
    act(() => result.current.handleKeyDown(keyEvent("ArrowDown")))
    act(() => result.current.handleKeyDown(keyEvent("Enter")))

    expect(onNavigateToResult).toHaveBeenCalledWith("/documents/r1")
  })
})
