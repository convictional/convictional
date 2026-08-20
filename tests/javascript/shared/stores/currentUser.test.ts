import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

// Capture reconnect listeners so tests can fire a reconnect and assert the
// store wires exactly one listener regardless of how many consumers arm.
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

import { apiFetch } from "~/react/shared/apiFetch"
import { queryClient } from "~/react/shared/queryClient"
import {
  armCurrentUserLiveUpdates,
  consumeFlashes,
  getCurrentUser,
  refreshCurrentUser,
  stopCurrentUserLiveUpdates,
} from "~/react/shared/stores/currentUser"

const mockApiFetch = vi.mocked(apiFetch)

const response = {
  id: "u1",
  display_name: "Alice",
  email: "alice@example.com",
  is_superuser: false,
  is_admin: false,
  picture: null,
  organization_id: "org-1",
  organization_name: "Acme",
  time_zone: null,
  feedback_upload_url: "/upload",
  client_config: { klipy_api_key: "test-key" },
  flashes: [{ content: "Welcome back", level: "info" }],
}

const { client_config, flashes, ...user } = response

beforeEach(() => {
  mockApiFetch.mockReset()
  reconnectListeners = []
  mockClient.on.mockClear()
  mockClient.off.mockClear()
})

// The accessors operate on the module singleton, so clear it between tests to
// keep cached state from leaking across cases.
afterEach(() => {
  stopCurrentUserLiveUpdates()
  queryClient.clear()
  consumeFlashes()
})

describe("currentUser query module", () => {
  test("getCurrentUser fetches once, returns the user, and caches client_config", async () => {
    mockApiFetch.mockResolvedValueOnce(response)

    const result = await getCurrentUser()

    expect(result).toEqual(user)
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(queryClient.getQueryData(["currentUser"])).toEqual({ user, clientConfig: client_config })
  })

  test("concurrent getCurrentUser calls share one fetch", async () => {
    mockApiFetch.mockResolvedValueOnce(response)

    const [a, b] = await Promise.all([getCurrentUser(), getCurrentUser()])

    expect(mockApiFetch).toHaveBeenCalledTimes(1)
    expect(a).toEqual(b)
  })

  test("getCurrentUser returns the cached value without refetching", async () => {
    mockApiFetch.mockResolvedValueOnce(response)
    await getCurrentUser()
    mockApiFetch.mockClear()

    const result = await getCurrentUser()

    expect(mockApiFetch).not.toHaveBeenCalled()
    expect(result.id).toBe("u1")
  })

  test("a failed fetch rejects and the next call retries", async () => {
    mockApiFetch.mockRejectedValueOnce(new Error("boom"))

    await expect(getCurrentUser()).rejects.toThrow("boom")

    mockApiFetch.mockResolvedValueOnce(response)
    const result = await getCurrentUser()
    expect(result.id).toBe("u1")
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
  })

  test("refreshCurrentUser marks the query invalidated", async () => {
    // An active observer (the mounted useCurrentUser hook) then refetches — see
    // the hook's reconnect test. With no observer, invalidation only flags the
    // cache, which is what this module-level accessor guarantees.
    mockApiFetch.mockResolvedValueOnce(response)
    await getCurrentUser()

    await refreshCurrentUser()

    expect(queryClient.getQueryState(["currentUser"])?.isInvalidated).toBe(true)
  })

  test("consumeFlashes returns the bootstrap flashes once, then empties", async () => {
    mockApiFetch.mockResolvedValueOnce(response)
    await getCurrentUser()

    expect(consumeFlashes()).toEqual([{ content: "Welcome back", level: "info" }])
    expect(consumeFlashes()).toEqual([])
  })

  test("arming many consumers wires a single reconnect listener", () => {
    armCurrentUserLiveUpdates()
    armCurrentUserLiveUpdates()
    armCurrentUserLiveUpdates()

    expect(reconnectListeners).toHaveLength(1)
    expect(mockClient.on).toHaveBeenCalledTimes(1)
  })

  test("a burst of refreshes coalesces into one leading and one trailing invalidate (rate-limit fix)", async () => {
    // Count invalidateQueries calls, not /api/users/me fetches: this store-level
    // accessor has no mounted observer, so invalidate (refetchType "active") never
    // refetches here — the guard is what we're testing, and it wraps invalidate.
    mockApiFetch.mockResolvedValue(response)
    await getCurrentUser()
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries")

    // Five reconnect-driven refreshes in the same tick — the multi-tab/flaky-socket
    // burst that flooded /api/users/me. Without the guard each would invalidate.
    await Promise.all([
      refreshCurrentUser(),
      refreshCurrentUser(),
      refreshCurrentUser(),
      refreshCurrentUser(),
      refreshCurrentUser(),
    ])
    // Let the trailing refresh the finally block schedules settle.
    await new Promise(r => setTimeout(r, 0))

    // Coalesced: the leading invalidate plus a single trailing one, never five.
    expect(invalidateSpy).toHaveBeenCalledTimes(2)
    invalidateSpy.mockRestore()
  })
})
