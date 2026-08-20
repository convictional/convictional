import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
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

import { GroupsIndex } from "~/react/features/groupsIndex/GroupsIndex"

function listResponse(groups: GroupListResponse["groups"]): GroupListResponse {
  return { groups, next_cursor: null, has_more: false }
}

// Capture the IntersectionObserver callbacks so tests can simulate the sentinel
// scrolling into view, and so a disconnected observer stops firing (mirroring how
// React unmounting the sentinel tears the observer down).
type StubObserver = { callback: IntersectionObserverCallback; disconnected: boolean }
let observers: StubObserver[]

function triggerIntersection() {
  for (const o of observers) {
    if (!o.disconnected) {
      o.callback([{ isIntersecting: true } as IntersectionObserverEntry], {} as IntersectionObserver)
    }
  }
}

// A promise the test settles by hand. Returning one from the apiFetch mock lets
// a test hold a page request open and resolve/reject it on its own schedule,
// rather than racing the component's fire-and-forget loadMore against a timer.
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

// Flush the microtask + macrotask queues inside act so a just-settled fetch's
// state commit lands before the next assertion.
async function flush() {
  await act(async () => {
    await new Promise(resolve => setTimeout(resolve, 0))
  })
}

beforeEach(() => {
  apiFetchMock.mockReset()
  observers = []
  vi.stubGlobal(
    "IntersectionObserver",
    vi.fn(function (callback: IntersectionObserverCallback) {
      const record: StubObserver = { callback, disconnected: false }
      observers.push(record)
      return {
        observe: vi.fn(),
        disconnect: vi.fn(() => {
          record.disconnected = true
        }),
        unobserve: vi.fn(),
      }
    })
  )
})

afterEach(() => {
  vi.clearAllMocks()
  vi.unstubAllGlobals()
})

describe("GroupsIndex", () => {
  test("shows the admin empty state with a create button when there are no groups", async () => {
    apiFetchMock.mockResolvedValue(listResponse([]))
    render(<GroupsIndex canManage />)

    expect(await screen.findByText("No groups yet")).toBeInTheDocument()
    expect(screen.getByText("Create groups to organize your team.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Create group/ })).toBeInTheDocument()
  })

  test("shows the non-admin empty state directing users to an admin", async () => {
    apiFetchMock.mockResolvedValue(listResponse([]))
    render(<GroupsIndex canManage={false} />)

    expect(await screen.findByText("Ask an admin to create a group.")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: /Create group/ })).not.toBeInTheDocument()
  })

  test("renders groups in the list layout", async () => {
    apiFetchMock.mockResolvedValue(listResponse([makeGroup({ name: "Engineering" })]))
    render(<GroupsIndex canManage={false} />)

    expect(await screen.findByText("Engineering")).toBeInTheDocument()
    expect(screen.getByText("Members")).toBeInTheDocument()
  })

  test("stops auto-loading after a paging error and recovers via Retry", async () => {
    // The failing second page is a hand-settled promise so the error commit is
    // sequenced deterministically (fire the request, confirm it landed, then
    // reject) rather than racing loadMore's fire-and-forget settle against a
    // timer — the flake this test has fought twice before.
    const failingPage = deferred<unknown>()
    apiFetchMock
      .mockResolvedValueOnce({
        groups: [makeGroup({ id: "g1", name: "Engineering" })],
        next_cursor: "c1",
        has_more: true,
      })
      .mockReturnValueOnce(failingPage.promise)
      .mockResolvedValueOnce({
        groups: [makeGroup({ id: "g2", name: "Platform" })],
        next_cursor: null,
        has_more: false,
      })

    render(<GroupsIndex canManage={false} />)
    await screen.findByText("Engineering")
    expect(apiFetchMock).toHaveBeenCalledTimes(1)

    // Sentinel scrolls into view → loadMore fires the second-page request.
    act(() => triggerIntersection())
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))

    // The request fails: the sentinel unmounts (so the observer stops firing)
    // and a Retry surfaces.
    await act(async () => {
      failingPage.reject(new Error("boom"))
    })
    await flush()
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument()

    // The sentinel is gone, so a further intersection must NOT re-fire (the bug
    // this guards against was an unbounded retry loop while the sentinel stayed
    // in view).
    act(() => triggerIntersection())
    await flush()
    expect(apiFetchMock).toHaveBeenCalledTimes(2)

    // Explicit Retry re-attempts and, on success, loads the next page.
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }))
    await screen.findByText("Platform")
    expect(apiFetchMock).toHaveBeenCalledTimes(3)
    expect(apiFetchMock).toHaveBeenLastCalledWith("/api/groups?cursor=c1", expect.anything())
    expect(screen.queryByRole("button", { name: /Retry/ })).not.toBeInTheDocument()
  })
})
