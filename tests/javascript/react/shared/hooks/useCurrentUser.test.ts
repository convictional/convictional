import { act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// Capture reconnect listeners registered by the hook so tests can fire them.
let reconnectListeners: Array<() => void> = []
const mockClient = {
  on: vi.fn((event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.push(cb)
  }),
  off: vi.fn((event: string, cb: () => void) => {
    if (event === "reconnected") {
      reconnectListeners = reconnectListeners.filter(l => l !== cb)
    }
  }),
}

vi.mock("~/channels/client", () => ({
  getChannelsClient: () => mockClient,
}))

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

import { queryClient } from "~/react/shared/queryClient"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { stopCurrentUserLiveUpdates } from "~/react/shared/stores/currentUser"

import { createTestQueryClient, renderHookWithClient } from "../testUtils"
import { buildCurrentUserApiResponse } from "../currentUserFixtures"

beforeEach(() => {
  reconnectListeners = []
  mockClient.on.mockClear()
  mockClient.off.mockClear()
  apiFetchMock.mockReset()
  apiFetchMock.mockResolvedValue(buildCurrentUserApiResponse({ id: "u1" }))
})

afterEach(() => {
  // The reconnect listener is a session-lifetime store singleton; reset it so the
  // latched client doesn't make the next test's arm() a no-op.
  stopCurrentUserLiveUpdates()
  queryClient.clear()
})

describe("useCurrentUser", () => {
  test("fetches and returns the current user", async () => {
    const { result } = renderHookWithClient(() => useCurrentUser())

    await waitFor(() => expect(result.current.user).not.toBeNull())
    expect(result.current.user?.id).toBe("u1")
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  test("wires a single session-lifetime reconnect listener that survives unmount", async () => {
    // The listener is armed once per session in the store (not per mount) so a
    // reconnect fans out to one /api/users/me refetch, not one per consumer — the
    // multiplier that tripped the rate limiter. It deliberately survives unmount
    // so hx-boost navigation doesn't drop and re-arm it (mirrors org members).
    const first = renderHookWithClient(() => useCurrentUser())
    await waitFor(() => expect(first.result.current.user).not.toBeNull())
    const second = renderHookWithClient(() => useCurrentUser())
    await waitFor(() => expect(second.result.current.user).not.toBeNull())

    expect(mockClient.on).toHaveBeenCalledTimes(1)
    expect(reconnectListeners).toHaveLength(1)

    first.unmount()
    second.unmount()
    expect(mockClient.off).not.toHaveBeenCalled()
    expect(reconnectListeners).toHaveLength(1)
  })

  test("a reconnect triggers exactly one refetch and keeps data on screen", async () => {
    // Render against the singleton: refreshCurrentUser invalidates the singleton
    // queryClient (as in production, where every root provides it), so the
    // observer must live on the same client to refetch on reconnect.
    const { result } = renderHookWithClient(() => useCurrentUser(), queryClient)
    await waitFor(() => expect(result.current.user).not.toBeNull())
    expect(apiFetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      reconnectListeners.forEach(l => l())
    })

    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))
    // Previous data stays visible during the refetch — no loading flash.
    expect(result.current.user?.id).toBe("u1")
    expect(result.current.loading).toBe(false)
  })

  test("a reconnect fetch failure does not produce an unhandled rejection", async () => {
    // Regression for DECIDE-94W: on mobile Safari the fetch can throw while the
    // network settles after a reconnect. The hook swallows it; without the
    // .catch() the rejection was unhandled and surfaced as a Sentry event.
    const { result } = renderHookWithClient(() => useCurrentUser(), queryClient)
    await waitFor(() => expect(result.current.user).not.toBeNull())

    const unhandled: unknown[] = []
    const handler = (event: PromiseRejectionEvent) => {
      unhandled.push(event.reason)
      event.preventDefault()
    }
    window.addEventListener("unhandledrejection", handler)

    apiFetchMock.mockRejectedValueOnce(new TypeError("Load failed"))
    await act(async () => {
      reconnectListeners.forEach(l => l())
      await new Promise(r => setTimeout(r, 0))
    })

    window.removeEventListener("unhandledrejection", handler)
    expect(unhandled).toHaveLength(0)
  })

  test("concurrent mounts on one client share a single fetch (dedup)", async () => {
    const client = createTestQueryClient()
    const a = renderHookWithClient(() => useCurrentUser(), client)
    const b = renderHookWithClient(() => useCurrentUser(), client)

    await waitFor(() => expect(a.result.current.user).not.toBeNull())
    await waitFor(() => expect(b.result.current.user).not.toBeNull())
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  test("two roots sharing the singleton client fetch only once", async () => {
    // The singleton-across-roots invariant: every island/SPA root provides the
    // same queryClient, so currentUser is fetched once, not per root.
    const a = renderHookWithClient(() => useCurrentUser(), queryClient)
    const b = renderHookWithClient(() => useCurrentUser(), queryClient)

    await waitFor(() => expect(a.result.current.user).not.toBeNull())
    await waitFor(() => expect(b.result.current.user).not.toBeNull())
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })
})
