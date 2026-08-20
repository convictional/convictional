import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import type { PaginatedResponse } from "~/react/shared/types"
import { usePaginatedList } from "~/react/shared/hooks/usePaginatedList"

import { deferred } from "../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)

interface Item {
  id: string
  label?: string
}

interface ItemListResponse extends PaginatedResponse {
  items: Item[]
  topic_id?: string
}

function makePage(items: Item[], pagination: Partial<PaginatedResponse> = {}): ItemListResponse {
  return { items, next_cursor: null, has_more: false, ...pagination }
}

// The hook is fed relative URLs; parse them against a dummy origin so we can
// assert on path + query params without string matching.
function calledUrl(callIndex: number): URL {
  return new URL(mockApiFetch.mock.calls[callIndex][0] as string, "http://test.local")
}

function buildUrl(cursor: string | null): string {
  return cursor ? `/api/items?cursor=${encodeURIComponent(cursor)}` : "/api/items"
}

function renderList(overrides: Partial<Parameters<typeof usePaginatedList<Item, ItemListResponse>>[0]> = {}) {
  return renderHook(() => usePaginatedList<Item, ItemListResponse>({ buildUrl, select: d => d.items, ...overrides }))
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

describe("usePaginatedList initial load", () => {
  it("fetches page one on mount and exposes items, hasMore, and the cursor", async () => {
    mockApiFetch.mockResolvedValue(makePage([{ id: "a" }, { id: "b" }], { next_cursor: "c1", has_more: true }))

    const { result } = renderList()
    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(calledUrl(0).pathname).toBe("/api/items")
    expect(result.current.items.map(i => i.id)).toEqual(["a", "b"])
    expect(result.current.hasMore).toBe(true)
  })
})

describe("usePaginatedList pagination", () => {
  it("appends the next page, carries the cursor, and de-dupes overlap by id", async () => {
    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "a" }, { id: "b" }], { next_cursor: "c1", has_more: true }))

    const { result } = renderList()
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "b" }, { id: "c" }], { has_more: false }))
    act(() => result.current.loadMore())
    await waitFor(() => expect(result.current.loadingMore).toBe(false))

    expect(result.current.items.map(i => i.id)).toEqual(["a", "b", "c"])
    expect(result.current.hasMore).toBe(false)
    expect(calledUrl(1).searchParams.get("cursor")).toBe("c1")
  })

  it("ignores loadMore when there is no next page", async () => {
    mockApiFetch.mockResolvedValue(makePage([{ id: "a" }], { has_more: false }))

    const { result } = renderList()
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.loadMore())
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })

  it("ignores a second loadMore while one is already in flight", async () => {
    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "a" }], { next_cursor: "c1", has_more: true }))

    const { result } = renderList()
    await waitFor(() => expect(result.current.loading).toBe(false))

    const pending = deferred<ItemListResponse>()
    mockApiFetch.mockReturnValueOnce(pending.promise)
    act(() => result.current.loadMore())
    act(() => result.current.loadMore())
    expect(mockApiFetch).toHaveBeenCalledTimes(2)

    await act(async () => {
      pending.resolve(makePage([{ id: "b" }], { has_more: false }))
    })
    expect(result.current.items.map(i => i.id)).toEqual(["a", "b"])
  })
})

describe("usePaginatedList dependency changes", () => {
  it("aborts the in-flight request and refetches page one when deps change", async () => {
    const first = deferred<ItemListResponse>()
    const second = deferred<ItemListResponse>()
    mockApiFetch.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)
    const abortSpy = vi.spyOn(AbortController.prototype, "abort")

    const { result, rerender } = renderHook(
      ({ scope }) =>
        usePaginatedList<Item, ItemListResponse>({
          buildUrl: cursor => `/api/items?scope=${scope}${cursor ? `&cursor=${cursor}` : ""}`,
          select: d => d.items,
          deps: [scope],
        }),
      { initialProps: { scope: "all" } }
    )
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))

    rerender({ scope: "mine" })
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))
    expect(abortSpy).toHaveBeenCalled()

    // Newer request resolves first, then the stale one — the stale one is ignored.
    await act(async () => {
      second.resolve(makePage([{ id: "from-mine" }]))
    })
    await act(async () => {
      first.resolve(makePage([{ id: "from-all" }]))
    })

    expect(calledUrl(1).searchParams.get("scope")).toBe("mine")
    expect(result.current.items.map(i => i.id)).toEqual(["from-mine"])
    abortSpy.mockRestore()
  })
})

describe("usePaginatedList error handling", () => {
  it("sets error and stops loading when the request fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))

    const { result } = renderList()
    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.loading).toBe(false)
    expect(result.current.items).toEqual([])
  })

  it("does not treat an AbortError as a failure", async () => {
    mockApiFetch.mockRejectedValue(new DOMException("aborted", "AbortError"))

    const { result } = renderList()
    // Give the rejected promise a chance to settle.
    await act(async () => {
      await Promise.resolve()
    })
    expect(result.current.error).toBe(false)
  })
})

describe("usePaginatedList reload", () => {
  it("refetches page one and replaces items", async () => {
    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "a" }], { next_cursor: "c1", has_more: true }))

    const { result } = renderList()
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "x" }], { has_more: false }))
    await act(async () => {
      await result.current.reload()
    })
    await waitFor(() => expect(result.current.items.map(i => i.id)).toEqual(["x"]))
    expect(result.current.hasMore).toBe(false)
    expect(calledUrl(1).searchParams.get("cursor")).toBeNull()
  })
})

describe("usePaginatedList onPage", () => {
  it("invokes onPage with the response and isLoadMore, only for non-stale pages", async () => {
    const onPage = vi.fn()
    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "a" }], { topic_id: "t1", next_cursor: "c1", has_more: true }))

    const { result } = renderList({ onPage })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(onPage).toHaveBeenCalledTimes(1)
    expect(onPage.mock.calls[0][0].topic_id).toBe("t1")
    expect(onPage.mock.calls[0][1]).toEqual({ isLoadMore: false })

    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "b" }], { has_more: false }))
    act(() => result.current.loadMore())
    await waitFor(() => expect(result.current.loadingMore).toBe(false))
    expect(onPage).toHaveBeenLastCalledWith(expect.anything(), { isLoadMore: true })
  })
})

describe("usePaginatedList setItems", () => {
  it("updates items without a fetch (optimistic / channel escape hatch)", async () => {
    mockApiFetch.mockResolvedValue(makePage([{ id: "a" }]))

    const { result } = renderList()
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.setItems(prev => [...prev, { id: "b" }]))
    expect(result.current.items.map(i => i.id)).toEqual(["a", "b"])
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })
})

describe("usePaginatedList stability", () => {
  it("keeps loadMore referentially stable across a loadingMore toggle", async () => {
    mockApiFetch.mockResolvedValueOnce(makePage([{ id: "a" }], { next_cursor: "c1", has_more: true }))

    const { result } = renderList()
    await waitFor(() => expect(result.current.loading).toBe(false))
    const before = result.current.loadMore

    const pending = deferred<ItemListResponse>()
    mockApiFetch.mockReturnValueOnce(pending.promise)
    act(() => result.current.loadMore())
    await waitFor(() => expect(result.current.loadingMore).toBe(true))
    expect(result.current.loadMore).toBe(before)

    await act(async () => {
      pending.resolve(makePage([{ id: "b" }], { has_more: false }))
    })
    expect(result.current.loadMore).toBe(before)
  })
})
