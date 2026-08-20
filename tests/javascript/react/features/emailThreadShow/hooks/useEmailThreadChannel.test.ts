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

import { useEmailThreadChannel } from "~/react/features/emailThreadShow/hooks/useEmailThreadChannel"

beforeEach(() => {
  registeredHandler = null
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useEmailThreadChannel", () => {
  it("MESSAGE_ADDED fires the callback with the deserialized message", () => {
    const onMessageAdded = vi.fn()
    renderHook(() => useEmailThreadChannel({ threadId: "t", onMessageAdded }))
    const message = {
      id: "m1",
      sender_name: "Alice",
      sender_email: "alice@example.com",
      content_url: "/api/email_threads/t/messages/m1",
    }
    act(() => {
      registeredHandler?.(ChannelEventAction.MESSAGE_ADDED, { message })
    })
    expect(onMessageAdded).toHaveBeenCalledWith(message)
  })

  it("other actions are ignored", () => {
    const onMessageAdded = vi.fn()
    renderHook(() => useEmailThreadChannel({ threadId: "t", onMessageAdded }))
    act(() => {
      registeredHandler?.(ChannelEventAction.UPDATED, { message: { id: "m1" } })
    })
    expect(onMessageAdded).not.toHaveBeenCalled()
  })

  it("MESSAGE_ADDED with an invalid payload is dropped", () => {
    const onMessageAdded = vi.fn()
    renderHook(() => useEmailThreadChannel({ threadId: "t", onMessageAdded }))
    act(() => {
      registeredHandler?.(ChannelEventAction.MESSAGE_ADDED, { message: { id: "m1" } })
    })
    expect(onMessageAdded).not.toHaveBeenCalled()
  })
})
