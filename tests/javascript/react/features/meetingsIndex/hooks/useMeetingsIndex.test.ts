import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useMeetingsIndex } from "~/react/features/meetingsIndex/hooks/useMeetingsIndex"

import { deferred, makeCollection, makeListPage, makeMeeting, makeShowPage } from "../../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)

// The hook is fed relative URLs; parse them against a dummy origin so we can
// assert on path + query params without string matching.
function calledUrl(callIndex: number): URL {
  return new URL(mockApiFetch.mock.calls[callIndex][0] as string, "http://test.local")
}

const mostRecent = { collectionId: null, uncategorized: false }
const uncategorized = { collectionId: null, uncategorized: true }
const collection = { collectionId: "col-1", uncategorized: false }

beforeEach(() => {
  mockApiFetch.mockReset()
})

describe("useMeetingsIndex query building", () => {
  it("requests past + declined meetings from /api/meetings, newest first, with no collection filter", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([]))

    renderHook(() => useMeetingsIndex(mostRecent))

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))
    const url = calledUrl(0)
    expect(url.pathname).toBe("/api/meetings")
    expect(url.searchParams.get("past")).toBe("true")
    expect(url.searchParams.get("include_declined")).toBe("true")
    expect(url.searchParams.get("sort")).toBe("scheduled_at_desc")
    expect(url.searchParams.get("collection_id")).toBeNull()
    expect(url.searchParams.get("uncategorized")).toBeNull()
  })

  it("adds uncategorized=true when the uncategorized pseudo-filter is active", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([]))

    renderHook(() => useMeetingsIndex(uncategorized))

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))
    expect(calledUrl(0).searchParams.get("uncategorized")).toBe("true")
  })

  it("fetches the dedicated collection endpoint and exposes its metadata in collection mode", async () => {
    mockApiFetch.mockResolvedValue(makeShowPage(makeCollection({ id: "col-1", title: "Sync" }), []))

    const { result } = renderHook(() => useMeetingsIndex(collection))
    await waitFor(() => expect(result.current.loading).toBe(false))

    const url = calledUrl(0)
    expect(url.pathname).toBe("/api/meetings_collections/col-1")
    expect(url.search).toBe("")
    expect(result.current.collection?.title).toBe("Sync")
  })
})

describe("useMeetingsIndex pagination", () => {
  it("appends the next page, carrying the cursor and de-duping overlap (pseudo mode)", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeListPage([makeMeeting({ id: "a" }), makeMeeting({ id: "b" })], { next_cursor: "cursor-1", has_more: true })
    )

    const { result } = renderHook(() => useMeetingsIndex(mostRecent))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.meetings.map(m => m.id)).toEqual(["a", "b"])

    mockApiFetch.mockResolvedValueOnce(
      makeListPage([makeMeeting({ id: "b" }), makeMeeting({ id: "c" })], { has_more: false })
    )
    act(() => {
      result.current.loadMore()
    })
    await waitFor(() => expect(result.current.loadingMore).toBe(false))

    expect(result.current.meetings.map(m => m.id)).toEqual(["a", "b", "c"])
    expect(result.current.hasMore).toBe(false)
    expect(calledUrl(1).searchParams.get("cursor")).toBe("cursor-1")
  })

  it("carries the cursor on the collection endpoint in collection mode", async () => {
    const col = makeCollection({ id: "col-1" })
    mockApiFetch.mockResolvedValueOnce(
      makeShowPage(col, [makeMeeting({ id: "a" })], { next_cursor: "cursor-1", has_more: true })
    )

    const { result } = renderHook(() => useMeetingsIndex(collection))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makeShowPage(col, [makeMeeting({ id: "b" })], { has_more: false }))
    act(() => {
      result.current.loadMore()
    })
    await waitFor(() => expect(result.current.loadingMore).toBe(false))

    expect(result.current.meetings.map(m => m.id)).toEqual(["a", "b"])
    expect(calledUrl(1).pathname).toBe("/api/meetings_collections/col-1")
    expect(calledUrl(1).searchParams.get("cursor")).toBe("cursor-1")
  })

  it("ignores loadMore when there is no next page", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([makeMeeting({ id: "a" })], { has_more: false }))

    const { result } = renderHook(() => useMeetingsIndex(mostRecent))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.loadMore()
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })
})

describe("useMeetingsIndex race handling", () => {
  it("discards a stale response that resolves after a newer filter switch", async () => {
    const first = deferred<ReturnType<typeof makeListPage>>()
    const second = deferred<ReturnType<typeof makeListPage>>()
    mockApiFetch.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const { result, rerender } = renderHook(args => useMeetingsIndex(args), { initialProps: mostRecent })
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))

    rerender(uncategorized)
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))

    // Newer (uncategorized) request resolves first, then the stale one.
    await act(async () => {
      second.resolve(makeListPage([makeMeeting({ id: "from-uncategorized" })]))
    })
    await act(async () => {
      first.resolve(makeListPage([makeMeeting({ id: "from-most-recent" })]))
    })

    expect(calledUrl(1).searchParams.get("uncategorized")).toBe("true")
    expect(result.current.meetings.map(m => m.id)).toEqual(["from-uncategorized"])
  })
})

describe("useMeetingsIndex error handling", () => {
  it("sets error and stops loading when the request fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))

    const { result } = renderHook(() => useMeetingsIndex(mostRecent))

    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.loading).toBe(false)
    expect(result.current.meetings).toEqual([])
  })
})

describe("useMeetingsIndex.upsertMeeting", () => {
  it("replaces in place without reordering on the Most Recent list", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([makeMeeting({ id: "a", title: "Old" }), makeMeeting({ id: "b" })]))

    const { result } = renderHook(() => useMeetingsIndex(mostRecent))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.upsertMeeting(makeMeeting({ id: "a", title: "New" }))
    })

    expect(result.current.meetings.map(m => m.id)).toEqual(["a", "b"])
    expect(result.current.meetings[0].title).toBe("New")
  })

  it("drops a meeting that gains a collection on the Uncategorized list", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([makeMeeting({ id: "a", collection: null }), makeMeeting({ id: "b" })]))

    const { result } = renderHook(() => useMeetingsIndex(uncategorized))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.upsertMeeting(
        makeMeeting({ id: "a", collection: { id: "col-9", title: "Filed", auto_assigned: false } })
      )
    })

    expect(result.current.meetings.map(m => m.id)).toEqual(["b"])
  })

  it("drops a meeting reassigned away from the viewed collection", async () => {
    const col = makeCollection({ id: "col-1" })
    mockApiFetch.mockResolvedValue(
      makeShowPage(col, [
        makeMeeting({ id: "a", collection: { id: "col-1", title: "Sync", auto_assigned: false } }),
        makeMeeting({ id: "b", collection: { id: "col-1", title: "Sync", auto_assigned: false } }),
      ])
    )

    const { result } = renderHook(() => useMeetingsIndex(collection))
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.upsertMeeting(
        makeMeeting({ id: "a", collection: { id: "col-2", title: "Other", auto_assigned: false } })
      )
    })

    expect(result.current.meetings.map(m => m.id)).toEqual(["b"])
  })
})

describe("useMeetingsIndex.updateCollection", () => {
  it("stores the updated collection and returns no error", async () => {
    mockApiFetch.mockResolvedValueOnce(makeShowPage(makeCollection({ id: "col-1" }), []))
    const { result } = renderHook(() => useMeetingsIndex(collection))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makeCollection({ id: "col-1", title: "Renamed" }))
    let returned: string | null = "unset"
    await act(async () => {
      returned = await result.current.updateCollection({ title: "Renamed" })
    })

    expect(returned).toBeNull()
    expect(result.current.collection?.title).toBe("Renamed")
    expect(calledUrl(1).pathname).toBe("/api/meetings_collections/col-1")
    expect(mockApiFetch.mock.calls[1][1]?.method).toBe("PATCH")
  })

  it("returns a fallback message when the update fails", async () => {
    mockApiFetch.mockResolvedValueOnce(makeShowPage(makeCollection({ id: "col-1" }), []))
    const { result } = renderHook(() => useMeetingsIndex(collection))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockRejectedValueOnce(new ApiError(500, null))
    let returned: string | null = null
    await act(async () => {
      returned = await result.current.updateCollection({ title: "x" })
    })

    expect(returned).toBe("Failed to update collection.")
  })

  it("is a no-op in pseudo mode", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([]))
    const { result } = renderHook(() => useMeetingsIndex(mostRecent))
    await waitFor(() => expect(result.current.loading).toBe(false))

    let returned: string | null = null
    await act(async () => {
      returned = await result.current.updateCollection({ title: "x" })
    })

    expect(returned).toBe("No collection to update.")
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })
})

describe("useMeetingsIndex.deleteCollection", () => {
  it("surfaces the server's 409 detail when the collection can't be deleted", async () => {
    mockApiFetch.mockResolvedValueOnce(makeShowPage(makeCollection({ id: "col-1" }), []))
    const { result } = renderHook(() => useMeetingsIndex(collection))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockRejectedValueOnce(new ApiError(409, { detail: "Collection still has meetings." }))
    let returned: string | null = null
    await act(async () => {
      returned = await result.current.deleteCollection()
    })

    expect(returned).toBe("Collection still has meetings.")
  })

  it("returns null on a successful delete", async () => {
    mockApiFetch.mockResolvedValueOnce(makeShowPage(makeCollection({ id: "col-1" }), []))
    const { result } = renderHook(() => useMeetingsIndex(collection))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(null)
    let returned: string | null = "unset"
    await act(async () => {
      returned = await result.current.deleteCollection()
    })

    expect(returned).toBeNull()
  })
})
