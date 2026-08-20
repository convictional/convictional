import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChannelEventAction } from "~/types/channels"

let registeredHandler: ((action: string, data: Record<string, unknown>) => void) | null = null
vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: (
    _target: { stream: string; params: Record<string, unknown> } | null,
    _resource: string,
    onMessage: (action: string, data: Record<string, unknown>) => void
  ) => {
    registeredHandler = onMessage
  },
}))

import {
  isOwnWorkspaceEvent,
  useWorkspaceEventsChannel,
  type WorkspaceEventBroadcast,
} from "~/react/features/emailThreadShow/hooks/useWorkspaceEventsChannel"

beforeEach(() => {
  registeredHandler = null
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useWorkspaceEventsChannel", () => {
  it("ADDED forwards a normalized broadcast payload", () => {
    const onEventAdded = vi.fn()
    renderHook(() => useWorkspaceEventsChannel({ workspaceId: "t", onEventAdded }))
    act(() => {
      registeredHandler?.(ChannelEventAction.ADDED, {
        event_id: "e1",
        event_action: "commented",
        recordable_type: "EmailThreadComment",
        recordable_id: "c1",
        creator_id: "u1",
      })
    })
    expect(onEventAdded).toHaveBeenCalledWith({
      eventId: "e1",
      eventAction: "commented",
      recordableType: "EmailThreadComment",
      recordableId: "c1",
      creatorId: "u1",
    })
  })

  it("ignores non-string fields", () => {
    const onEventAdded = vi.fn()
    renderHook(() => useWorkspaceEventsChannel({ workspaceId: "t", onEventAdded }))
    act(() => {
      registeredHandler?.(ChannelEventAction.ADDED, {
        event_id: null,
        event_action: "commented",
        recordable_type: "EmailThreadComment",
        recordable_id: "c1",
      })
    })
    expect(onEventAdded).not.toHaveBeenCalled()
  })
})

describe("isOwnWorkspaceEvent", () => {
  const buildEvent = (creatorId: string | null): WorkspaceEventBroadcast => ({
    eventId: "e1",
    eventAction: "commented",
    recordableType: "Comment",
    recordableId: "c1",
    creatorId,
  })

  it("returns true only when the current user is the proven creator", () => {
    // Current user's own action → nudge suppressed.
    expect(isOwnWorkspaceEvent(buildEvent("u1"), "u1")).toBe(true)
    // Another user's action → nudge proceeds.
    expect(isOwnWorkspaceEvent(buildEvent("u2"), "u1")).toBe(false)
    // System event (no creator) → nudge proceeds.
    expect(isOwnWorkspaceEvent(buildEvent(null), "u1")).toBe(false)
    // Viewer not loaded → cannot prove self → nudge proceeds.
    expect(isOwnWorkspaceEvent(buildEvent("u1"), null)).toBe(false)
  })
})
