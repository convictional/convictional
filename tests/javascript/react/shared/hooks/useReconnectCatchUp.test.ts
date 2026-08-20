import { act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

// useReconnectInvalidate subscribes to the channels client's "reconnected" event;
// capture the listeners so a test can fire a reconnect.
let reconnectListeners: Array<() => void> = []
const mockClient = {
  on: vi.fn((event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.push(cb)
  }),
  off: vi.fn((event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners = reconnectListeners.filter(l => l !== cb)
  }),
}
vi.mock("~/channels/client", () => ({ getChannelsClient: () => mockClient }))

import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"

import { createTestQueryClient, renderHookWithClient } from "../../shared/testUtils"

const KEY = ["reconnect-catch-up-test"] as const

beforeEach(() => {
  reconnectListeners = []
  mockClient.on.mockClear()
  mockClient.off.mockClear()
})
afterEach(() => vi.clearAllMocks())

describe("useReconnectCatchUp", () => {
  test("catches up a warm or errored cache on mount and any cache on reconnect, but skips a cold mount", async () => {
    // Warm cache at mount → invalidate to catch up on missed broadcasts.
    const warm = createTestQueryClient()
    warm.setQueryData(KEY, { ok: true })
    const warmInvalidate = vi.spyOn(warm, "invalidateQueries")
    renderHookWithClient(() => useReconnectCatchUp(KEY, "test"), warm)
    expect(warmInvalidate).toHaveBeenCalledWith({ queryKey: KEY })

    // Errored cache at mount → re-fetch, since channelQueryDefaults won't retry on mount.
    const errored = createTestQueryClient()
    await errored.prefetchQuery({ queryKey: KEY, queryFn: () => Promise.reject(new Error("boom")) })
    const erroredInvalidate = vi.spyOn(errored, "invalidateQueries")
    renderHookWithClient(() => useReconnectCatchUp(KEY, "test"), errored)
    expect(erroredInvalidate).toHaveBeenCalledWith({ queryKey: KEY })

    // Cold cache at mount → nothing cached yet, so nothing to catch up.
    const cold = createTestQueryClient()
    const coldInvalidate = vi.spyOn(cold, "invalidateQueries")
    renderHookWithClient(() => useReconnectCatchUp(KEY, "test"), cold)
    expect(coldInvalidate).not.toHaveBeenCalled()

    // Socket reconnect invalidates unconditionally — the way back for an errored or
    // cold channel-backed query the mount path skips. Every mounted subscriber fires.
    act(() => reconnectListeners.forEach(fn => fn()))
    expect(coldInvalidate).toHaveBeenCalledWith({ queryKey: KEY })
    expect(warmInvalidate).toHaveBeenCalledTimes(2) // once on mount, once on reconnect
  })
})
