import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
import { useCollectionsIndex } from "~/react/features/meetingsCollectionsIndex/hooks/useCollectionsIndex"

import { deferred, makeCollection, makeCollectionListResponse } from "../../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)

function calledUrl(callIndex: number): URL {
  return new URL(mockApiFetch.mock.calls[callIndex][0] as string, "http://test.local")
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

describe("useCollectionsIndex fetching", () => {
  it("exhausts every page and exposes the uncategorized count from the last page", async () => {
    mockApiFetch
      .mockResolvedValueOnce(
        makeCollectionListResponse([makeCollection({ id: "a" })], {
          next_cursor: "cursor-1",
          has_more: true,
          uncategorized_count: 1,
        })
      )
      .mockResolvedValueOnce(
        makeCollectionListResponse([makeCollection({ id: "b" })], { uncategorized_count: 4 })
      )

    const { result } = renderHook(() => useCollectionsIndex())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.collections.map(c => c.id)).toEqual(["a", "b"])
    expect(result.current.uncategorizedCount).toBe(4)
    expect(calledUrl(0).pathname).toBe("/api/meetings_collections")
    expect(calledUrl(0).search).toBe("")
    expect(calledUrl(1).searchParams.get("cursor")).toBe("cursor-1")
  })

  it("sets error and stops loading when the fetch fails", async () => {
    mockApiFetch.mockRejectedValue(new Error("boom"))

    const { result } = renderHook(() => useCollectionsIndex())

    await waitFor(() => expect(result.current.error).toBe(true))
    expect(result.current.loading).toBe(false)
    expect(result.current.collections).toEqual([])
  })
})

describe("useCollectionsIndex.create", () => {
  it("POSTs the collection and inserts it alphabetically", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeCollectionListResponse([makeCollection({ id: "m", title: "Marketing" })])
    )

    const { result } = renderHook(() => useCollectionsIndex())
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makeCollection({ id: "a", title: "Alpha" }))
    let err: string | null = "unset"
    await act(async () => {
      err = await result.current.create("Alpha", "the first one")
    })

    expect(err).toBeNull()
    const createCall = mockApiFetch.mock.calls[1]
    expect(createCall[0]).toBe("/api/meetings_collections")
    expect(createCall[1]).toMatchObject({ method: "POST" })
    expect(JSON.parse(createCall[1]!.body as string)).toEqual({ title: "Alpha", description: "the first one" })
    expect(result.current.collections.map(c => c.title)).toEqual(["Alpha", "Marketing"])
  })

  it("omits description when none is given and returns an error message on failure", async () => {
    mockApiFetch.mockResolvedValueOnce(makeCollectionListResponse([]))

    const { result } = renderHook(() => useCollectionsIndex())
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makeCollection({ id: "x", title: "No Desc" }))
    await act(async () => {
      await result.current.create("No Desc", null)
    })
    expect(JSON.parse(mockApiFetch.mock.calls[1][1]!.body as string)).toEqual({ title: "No Desc" })

    mockApiFetch.mockRejectedValueOnce(new Error("nope"))
    let err: string | null = null
    await act(async () => {
      err = await result.current.create("Boom", null)
    })
    expect(err).toBe("Failed to create collection.")
  })
})

describe("useCollectionsIndex race handling", () => {
  it("discards a stale refresh that resolves after a newer one", async () => {
    const first = deferred<ReturnType<typeof makeCollectionListResponse>>()
    const second = deferred<ReturnType<typeof makeCollectionListResponse>>()
    mockApiFetch.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise)

    const { result } = renderHook(() => useCollectionsIndex())
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))

    // A second refresh supersedes the first before it settles.
    act(() => {
      result.current.refresh()
    })
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))

    // Newer refresh resolves first, then the stale one — the stale result must
    // not clobber state.
    await act(async () => {
      second.resolve(makeCollectionListResponse([makeCollection({ id: "new" })]))
    })
    await act(async () => {
      first.resolve(makeCollectionListResponse([makeCollection({ id: "stale" })]))
    })

    expect(result.current.collections.map(c => c.id)).toEqual(["new"])
  })
})
