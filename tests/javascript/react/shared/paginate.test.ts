import { beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))

import { apiFetch } from "~/react/shared/apiFetch"
import { fetchAllPages } from "~/react/shared/paginate"
import type { PaginatedResponse } from "~/react/shared/types"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  mockApiFetch.mockReset()
})

interface ThingResponse extends PaginatedResponse {
  things: string[]
  uncategorized_count?: number
}

function page(
  things: string[],
  pagination: { has_more: boolean; next_cursor: string | null },
  extra: Partial<ThingResponse> = {}
): ThingResponse {
  return { things, ...pagination, ...extra }
}

describe("fetchAllPages", () => {
  test("returns a single page's items with one apiFetch call", async () => {
    mockApiFetch.mockResolvedValueOnce(page(["a", "b"], { has_more: false, next_cursor: null }) as any)

    const items = await fetchAllPages<string, ThingResponse>("/api/things", r => r.things)

    expect(items).toEqual(["a", "b"])
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(mockApiFetch).toHaveBeenCalledWith("/api/things", {})
  })

  test("drains every page, following next_cursor, and concatenates in order", async () => {
    mockApiFetch
      .mockResolvedValueOnce(page(["a", "b"], { has_more: true, next_cursor: "cur/2" }) as any)
      .mockResolvedValueOnce(page(["c", "d"], { has_more: false, next_cursor: null }) as any)

    const items = await fetchAllPages<string, ThingResponse>("/api/things", r => r.things)

    expect(items).toEqual(["a", "b", "c", "d"])
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
    expect(mockApiFetch.mock.calls[0][0]).toBe("/api/things")
    expect(mockApiFetch.mock.calls[1][0]).toBe(`/api/things?cursor=${encodeURIComponent("cur/2")}`)
  })

  test("invokes onPage once per page with the full response", async () => {
    const first = page(["a"], { has_more: true, next_cursor: "cur2" }, { uncategorized_count: 5 })
    const second = page(["b"], { has_more: false, next_cursor: null }, { uncategorized_count: 5 })
    mockApiFetch.mockResolvedValueOnce(first as any).mockResolvedValueOnce(second as any)

    const onPage = vi.fn()
    await fetchAllPages<string, ThingResponse>("/api/things", r => r.things, { onPage })

    expect(onPage).toHaveBeenCalledTimes(2)
    expect(onPage).toHaveBeenNthCalledWith(1, first)
    expect(onPage).toHaveBeenNthCalledWith(2, second)
  })

  test("stops draining if the server repeats a cursor instead of looping forever", async () => {
    mockApiFetch
      .mockResolvedValueOnce(page(["a"], { has_more: true, next_cursor: "loop" }) as any)
      .mockResolvedValue(page(["b"], { has_more: true, next_cursor: "loop" }) as any)

    const items = await fetchAllPages<string, ThingResponse>("/api/things", r => r.things)

    expect(items).toEqual(["a", "b"])
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
  })

  test("threads the signal into apiFetch", async () => {
    mockApiFetch.mockResolvedValueOnce(page(["a"], { has_more: false, next_cursor: null }) as any)

    const controller = new AbortController()
    await fetchAllPages<string, ThingResponse>("/api/things", r => r.things, { signal: controller.signal })

    expect(mockApiFetch).toHaveBeenCalledWith("/api/things", { signal: controller.signal })
  })
})
