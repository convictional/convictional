import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChannelEventAction, ChannelEventResource, ChannelMessageType, ChannelStream } from "~/types/channels"
import type { ChannelParams, WebSocketMessage } from "~/types/channels"

// Capture the callback registered with subscribeTo so tests can push messages through it.
let registeredCallback: ((message: WebSocketMessage) => void) | null = null
const subscribeTo = vi.fn((_stream: string, _params: ChannelParams, callback: (message: WebSocketMessage) => void) => {
  registeredCallback = callback
  return { name: "sub" }
})
const unsubscribe = vi.fn()

vi.mock("~/react/shared/hooks/useChannelsClient", () => ({
  useChannelsClient: () => ({ subscribeTo, unsubscribe }),
}))

import { useChannel } from "~/react/shared/hooks/useChannel"

beforeEach(() => {
  registeredCallback = null
  subscribeTo.mockClear()
  unsubscribe.mockClear()
})

afterEach(() => {
  vi.restoreAllMocks()
})

function eventMessage(resource: ChannelEventResource, action: ChannelEventAction, data: Record<string, unknown>) {
  return {
    type: ChannelMessageType.EVENT,
    topic_stream: "goal_timeline",
    topic_params: { goal_id: "5" },
    resource,
    action,
    data,
  } as WebSocketMessage
}

describe("useChannel", () => {
  it("subscribes by stream + params on mount", () => {
    renderHook(() =>
      useChannel(
        { stream: ChannelStream.GOAL_TIMELINE, params: { goal_id: "5" } },
        ChannelEventResource.GOAL_TIMELINE,
        vi.fn()
      )
    )

    expect(subscribeTo).toHaveBeenCalledTimes(1)
    const [stream, params, , extraParams] = subscribeTo.mock.calls[0]
    expect(stream).toBe("goal_timeline")
    expect(params).toEqual({ goal_id: "5" })
    expect(extraParams).toEqual({})
  })

  it("forwards EVENT messages matching the resource and ignores others", () => {
    const onMessage = vi.fn()
    renderHook(() =>
      useChannel(
        { stream: ChannelStream.GOAL_TIMELINE, params: { goal_id: "5" } },
        ChannelEventResource.GOAL_TIMELINE,
        onMessage
      )
    )

    act(() => {
      registeredCallback?.(eventMessage(ChannelEventResource.GOAL_TIMELINE, ChannelEventAction.UPDATED, { x: 1 }))
    })
    expect(onMessage).toHaveBeenCalledWith(ChannelEventAction.UPDATED, { x: 1 })

    act(() => {
      registeredCallback?.(eventMessage(ChannelEventResource.GOAL_COMMENT, ChannelEventAction.CREATED, { y: 2 }))
    })
    expect(onMessage).toHaveBeenCalledTimes(1)
  })

  it("forwards extraParams as the fourth subscribe argument", () => {
    renderHook(() =>
      useChannel(
        { stream: ChannelStream.MAILBOX_VIEW, params: { view_id: "abc" }, extraParams: { cached_at: "2026-01-01" } },
        ChannelEventResource.MAILBOX_VIEW,
        vi.fn()
      )
    )
    const [, , , extraParams] = subscribeTo.mock.calls[0]
    expect(extraParams).toEqual({ cached_at: "2026-01-01" })
  })

  it("re-subscribes when identity params change", () => {
    const { rerender } = renderHook(
      ({ goalId }) =>
        useChannel(
          { stream: ChannelStream.GOAL_TIMELINE, params: { goal_id: goalId } },
          ChannelEventResource.GOAL_TIMELINE,
          vi.fn()
        ),
      { initialProps: { goalId: "5" } }
    )
    expect(subscribeTo).toHaveBeenCalledTimes(1)

    rerender({ goalId: "9" })
    expect(unsubscribe).toHaveBeenCalledTimes(1)
    expect(subscribeTo).toHaveBeenCalledTimes(2)
  })

  it("unsubscribes on unmount", () => {
    const { unmount } = renderHook(() =>
      useChannel(
        { stream: ChannelStream.GOAL_TIMELINE, params: { goal_id: "5" } },
        ChannelEventResource.GOAL_TIMELINE,
        vi.fn()
      )
    )
    unmount()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })

  it("no-ops when target is null", () => {
    renderHook(() => useChannel(null, ChannelEventResource.GOAL_TIMELINE, vi.fn()))
    expect(subscribeTo).not.toHaveBeenCalled()
  })
})
