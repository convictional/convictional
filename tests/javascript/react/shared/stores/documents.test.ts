import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn().mockResolvedValue({}),
}))

import { apiFetch } from "~/react/shared/apiFetch"
import {
  documentContentQueryOptions,
  documentQueryOptions,
  documentsListQueryOptions,
} from "~/react/shared/stores/documents"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => mockApiFetch.mockClear())
afterEach(() => vi.clearAllMocks())

describe("documents query options", () => {
  test("list query keys by filter and reads the cursor envelope", async () => {
    const options = documentsListQueryOptions("anyone")
    expect(options.queryKey).toEqual(["documents", { filter: "anyone" }])

    // First page (null cursor) omits the cursor param; the non-default filter is sent.
    await options.queryFn!({ pageParam: null, signal: undefined } as never)
    expect(mockApiFetch).toHaveBeenCalledWith("/api/documents?filter=anyone", { signal: undefined })

    // getNextPageParam reads has_more/next_cursor.
    expect(options.getNextPageParam({ documents: [], next_cursor: "c1", has_more: true })).toBe("c1")
    expect(options.getNextPageParam({ documents: [], next_cursor: "c1", has_more: false })).toBeUndefined()
  })

  test("the default filter omits the query param", async () => {
    const options = documentsListQueryOptions("mine")
    await options.queryFn!({ pageParam: "c2", signal: undefined } as never)
    expect(mockApiFetch).toHaveBeenCalledWith("/api/documents?cursor=c2", { signal: undefined })
  })

  test("detail and content queries key on the document id", async () => {
    // 403 (access denied) is declared expected so it stays out of Sentry while
    // still throwing for the show page to turn into a request-access affordance.
    const accessDenied = { expectedStatuses: [403] }

    const detail = documentQueryOptions("doc-1")
    expect(detail.queryKey).toEqual(["document", "doc-1"])
    await detail.queryFn!({ signal: undefined } as never)
    expect(mockApiFetch).toHaveBeenCalledWith("/api/documents/doc-1", { signal: undefined }, accessDenied)

    const content = documentContentQueryOptions("doc-1")
    expect(content.queryKey).toEqual(["document", "doc-1", "content"])
    await content.queryFn!({ signal: undefined } as never)
    expect(mockApiFetch).toHaveBeenCalledWith("/api/documents/doc-1/content", { signal: undefined }, accessDenied)
  })
})
