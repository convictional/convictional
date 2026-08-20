import { act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { ChannelEventAction } from "~/types/channels"
import { ChannelEventAction as Action } from "~/types/channels"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

// Capture the (stream, params) the hook subscribed with plus its handler.
let channelHandler: ((action: ChannelEventAction, data: Record<string, unknown>) => void) | null = null
let channelStream: string | null = null
let channelParams: Record<string, unknown> | null = null
vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: (
    target: { stream: string; params: Record<string, unknown> } | null,
    _resource: unknown,
    onMessage: typeof channelHandler
  ) => {
    channelStream = target?.stream ?? null
    channelParams = target?.params ?? null
    channelHandler = onMessage
  },
}))

import { useGoalTimeline } from "~/react/features/goalShow/hooks/useGoalTimeline"
import { apiFetch } from "~/react/shared/apiFetch"

import { renderHookWithClient, waitFor } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  channelHandler = null
  channelStream = null
  channelParams = null
  mockApiFetch.mockResolvedValue({ events: [] } as never)
})
afterEach(() => vi.clearAllMocks())

describe("useGoalTimeline", () => {
  test("fetches the timeline and subscribes to the goal_timeline topic by goal id", async () => {
    const { result } = renderHookWithClient(() => useGoalTimeline("goal-1"))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1/timeline", expect.anything())
    expect(channelStream).toBe("goal_timeline")
    expect(channelParams).toEqual({ goal_id: "goal-1" })
  })

  test("a broadcast replaces the events from its payload, with no refetch", async () => {
    const { result } = renderHookWithClient(() => useGoalTimeline("goal-1"))
    await waitFor(() => expect(result.current.loading).toBe(false))
    mockApiFetch.mockClear()

    act(() =>
      channelHandler!(Action.UPDATED, {
        events: [{ id: "e1" }],
      } as unknown as Record<string, unknown>)
    )

    await waitFor(() => expect(result.current.events.map(e => (e as { id: string }).id)).toEqual(["e1"]))
    // The payload is the whole TimelineResponse, so patching it needs no network.
    expect(mockApiFetch).not.toHaveBeenCalled()
  })
})
