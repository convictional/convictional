import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { GroupListResponse } from "~/react/features/groupsIndex/types"
import { makeGroup } from "./factories"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: apiFetchMock,
  ApiError: class extends Error {
    status: number
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
    }
  },
}))

vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({
    user: { id: "u1", display_name: "Alice", picture: null },
    clientConfig: null,
    loading: false,
    error: null,
  }),
}))

import { useGroupsData } from "~/react/features/groupsIndex/hooks/useGroupsData"

function listResponse(groups: GroupListResponse["groups"]): GroupListResponse {
  return { groups, next_cursor: null, has_more: false }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

beforeEach(() => {
  apiFetchMock.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("useGroupsData.deleteGroup", () => {
  test("a failed delete restores only the deleted row, preserving a concurrent rename", async () => {
    const deleteA = deferred<void>()
    apiFetchMock.mockImplementation((url: string, opts?: RequestInit) => {
      const method = opts?.method ?? "GET"
      if (url === "/api/groups" && method === "GET") {
        return Promise.resolve(
          listResponse([
            makeGroup({ id: "a", name: "Alpha" }),
            makeGroup({ id: "b", name: "Bravo" }),
            makeGroup({ id: "c", name: "Charlie" }),
          ])
        )
      }
      if (url === "/api/groups/a" && method === "DELETE") return deleteA.promise
      if (url === "/api/groups/b" && method === "PATCH") {
        return Promise.resolve(makeGroup({ id: "b", name: "Bravo renamed" }))
      }
      throw new Error(`unexpected ${method} ${url}`)
    })

    const { result } = renderHook(() => useGroupsData())
    await waitFor(() => expect(result.current.groups).toHaveLength(3))

    // Delete Alpha optimistically (DELETE still in flight)...
    act(() => result.current.deleteGroup("a"))
    expect(result.current.groups.map(g => g.id)).toEqual(["b", "c"])

    // ...then rename Bravo while the delete is unresolved.
    act(() => result.current.renameGroup("b", "Bravo renamed"))
    await waitFor(() => expect(result.current.groups.find(g => g.id === "b")?.name).toBe("Bravo renamed"))

    // The delete fails: Alpha must come back without clobbering the rename.
    await act(async () => {
      deleteA.reject(new Error("boom"))
      await deleteA.promise.catch(() => {})
    })

    expect(result.current.groups.map(g => g.id)).toEqual(["a", "b", "c"])
    expect(result.current.groups.find(g => g.id === "a")?.name).toBe("Alpha")
    expect(result.current.groups.find(g => g.id === "b")?.name).toBe("Bravo renamed")
  })
})
