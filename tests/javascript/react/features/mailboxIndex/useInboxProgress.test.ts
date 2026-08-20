import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { InboxProgressResponse } from "../../../../../app/javascript/react/features/mailboxIndex/types"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: null
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = null
    }
  },
  errorMessage: (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback),
}))

const channelHandlers = new Map<string, (action: string, data: Record<string, unknown>) => void>()

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (
    target: { stream: string; params: Record<string, unknown>; extraParams?: Record<string, unknown> } | null,
    resource: string,
    onMessage: (action: string, data: Record<string, unknown>) => void
  ) => {
    if (target) channelHandlers.set(resource, onMessage)
  },
}))

const reconnectListeners = new Set<() => void>()
const fakeClient = {
  on: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.add(cb)
  },
  off: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.delete(cb)
  },
}

vi.mock("../../../../../app/javascript/channels/client", () => ({
  getChannelsClient: () => fakeClient,
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { useInboxProgress } from "../../../../../app/javascript/react/features/mailboxIndex/hooks/useInboxProgress"

const mockApiFetch = vi.mocked(apiFetch)

function makeProgress(overrides: Partial<InboxProgressResponse> = {}): InboxProgressResponse {
  return {
    is_onboarding_mailbox_sync_complete: false,
    onboarding_mailbox_sync_started_at: "2026-05-13T18:00:00Z",
    has_gmail_integration: true,
    has_calendar_integration: false,
    ...overrides,
  }
}

beforeEach(() => {
  channelHandlers.clear()
  reconnectListeners.clear()
  mockApiFetch.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("useInboxProgress", () => {
  test("reconnect refetches /api/inbox_progress to recover broadcasts missed during disconnect", async () => {
    // Initial fetch returns sync-in-progress.
    mockApiFetch.mockResolvedValueOnce(makeProgress({ is_onboarding_mailbox_sync_complete: false }))

    const { result } = renderHook(() => useInboxProgress("user-1"))
    await waitFor(() => expect(result.current.is_onboarding_mailbox_sync_complete).toBe(false))

    expect(mockApiFetch).toHaveBeenCalledTimes(1)

    // While the WS was disconnected, the sync-completion broadcast fired and was
    // lost. On reconnect the hook must refetch to pick up the latest state.
    mockApiFetch.mockResolvedValueOnce(makeProgress({ is_onboarding_mailbox_sync_complete: true }))

    await act(async () => {
      reconnectListeners.forEach(cb => cb())
      await Promise.resolve()
    })

    await waitFor(() => expect(result.current.is_onboarding_mailbox_sync_complete).toBe(true))
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
  })

  test("channel EVENT message updates state without a refetch", async () => {
    mockApiFetch.mockResolvedValueOnce(makeProgress({ is_onboarding_mailbox_sync_complete: false }))

    const { result } = renderHook(() => useInboxProgress("user-1"))
    await waitFor(() => expect(result.current.is_onboarding_mailbox_sync_complete).toBe(false))

    const handler = channelHandlers.get("inbox_progress")
    expect(handler).toBeDefined()

    act(() => {
      handler!("updated", makeProgress({ is_onboarding_mailbox_sync_complete: true }) as unknown as Record<string, unknown>)
    })

    expect(result.current.is_onboarding_mailbox_sync_complete).toBe(true)
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })
})
