import { act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { useDocumentsIndex } from "../../../../../app/javascript/react/features/documentsIndex/hooks/useDocumentsIndex"
import type { DocumentListResponse } from "../../../../../app/javascript/react/features/documentsIndex/types"
import { renderHookWithClient } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)

function makeResponse(overrides: Partial<DocumentListResponse> = {}): DocumentListResponse {
  return { documents: [], next_cursor: null, has_more: false, ...overrides }
}

function makeDoc(id: string) {
  return {
    id,
    title: id,
    author_display_name: "Me",
    last_viewed_at: null,
    updated_at: "2026-04-20T09:00:00Z",
    comment_count: 0,
    sharing: "private" as const,
    collaborator_count: 1,
    source_url: `/documents/${id}`,
  }
}

beforeEach(() => mockApiFetch.mockReset())
afterEach(() => vi.clearAllMocks())

describe("useDocumentsIndex", () => {
  test("fetches the default filter with no query param and flattens pages", async () => {
    mockApiFetch.mockResolvedValue(makeResponse({ documents: [makeDoc("a"), makeDoc("b")] }))

    const { result } = renderHookWithClient(() => useDocumentsIndex("mine"))

    await waitFor(() => expect(result.current.documents).toHaveLength(2))
    expect(mockApiFetch).toHaveBeenCalledWith("/api/documents", expect.any(Object))
  })

  test("non-default filter is sent as a query param", async () => {
    mockApiFetch.mockResolvedValue(makeResponse())

    renderHookWithClient(() => useDocumentsIndex("anyone"))

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/documents?filter=anyone", expect.any(Object)))
  })

  test("loadMore appends the next cursor page", async () => {
    mockApiFetch
      .mockResolvedValueOnce(makeResponse({ documents: [makeDoc("a")], next_cursor: "c1", has_more: true }))
      .mockResolvedValueOnce(makeResponse({ documents: [makeDoc("b")], next_cursor: null, has_more: false }))

    const { result } = renderHookWithClient(() => useDocumentsIndex("mine"))

    await waitFor(() => expect(result.current.hasMore).toBe(true))
    act(() => result.current.loadMore())

    await waitFor(() => expect(result.current.documents.map(d => d.id)).toEqual(["a", "b"]))
    expect(mockApiFetch).toHaveBeenCalledWith("/api/documents?cursor=c1", expect.any(Object))
  })
})
