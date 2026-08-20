import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ChannelEventAction, ChannelEventResource } from "~/types/channels"

// Capture the onMessage callback registered with the chat channel so tests can
// push NEW/UPDATED/DELETED events through it directly.
let registeredCallback:
  | ((action: ChannelEventAction, data: Record<string, unknown>) => void)
  | undefined
vi.mock("~/react/shared/hooks/useChatChannel", () => ({
  useChatChannel: (
    _chatId: string | null,
    _workspaceId: string | null,
    _resource: ChannelEventResource,
    onMessage: (action: ChannelEventAction, data: Record<string, unknown>) => void
  ) => {
    registeredCallback = onMessage
  },
}))

import { useChatMessageSubscription } from "~/react/shared/hooks/useChatMessageSubscription"

beforeEach(() => {
  registeredCallback = undefined
})

afterEach(() => {
  vi.restoreAllMocks()
})

function makeMessage(id: string) {
  return { id, content: "hi", user: { id: "u1" } } as never
}

describe("useChatMessageSubscription", () => {
  it("appends a NEW_MESSAGE and notifies onNewMessage when at the tail", () => {
    let messages: { id: string }[] = []
    const setMessages = vi.fn((updater: (prev: { id: string }[]) => { id: string }[]) => {
      messages = updater(messages)
    })
    const onNewMessage = vi.fn()

    renderHook(() =>
      useChatMessageSubscription("c1", "w1", setMessages as never, {
        onNewMessage,
        isAtTail: () => true,
      })
    )

    registeredCallback!(ChannelEventAction.NEW_MESSAGE, makeMessage("m1"))
    expect(messages.map(m => m.id)).toEqual(["m1"])
    expect(onNewMessage).toHaveBeenCalledTimes(1)
  })

  it("appends by default when no isAtTail getter is supplied", () => {
    let messages: { id: string }[] = []
    const setMessages = vi.fn((updater: (prev: { id: string }[]) => { id: string }[]) => {
      messages = updater(messages)
    })

    renderHook(() => useChatMessageSubscription("c1", "w1", setMessages as never, {}))

    registeredCallback!(ChannelEventAction.NEW_MESSAGE, makeMessage("m1"))
    expect(messages.map(m => m.id)).toEqual(["m1"])
  })

  it("does NOT append a NEW_MESSAGE while not at the tail (loadNewer will fetch it)", () => {
    let messages: { id: string }[] = []
    const setMessages = vi.fn((updater: (prev: { id: string }[]) => { id: string }[]) => {
      messages = updater(messages)
    })
    const onNewMessage = vi.fn()

    renderHook(() =>
      useChatMessageSubscription("c1", "w1", setMessages as never, {
        onNewMessage,
        isAtTail: () => false,
      })
    )

    registeredCallback!(ChannelEventAction.NEW_MESSAGE, makeMessage("m1"))
    expect(setMessages).not.toHaveBeenCalled()
    expect(messages).toEqual([])
    expect(onNewMessage).not.toHaveBeenCalled()
  })

  it("reads the gate at event time, so a value flip takes effect without re-subscribing", () => {
    let messages: { id: string }[] = []
    const setMessages = vi.fn((updater: (prev: { id: string }[]) => { id: string }[]) => {
      messages = updater(messages)
    })
    let atTail = true

    const { rerender } = renderHook(() =>
      useChatMessageSubscription("c1", "w1", setMessages as never, {
        isAtTail: () => atTail,
      })
    )

    registeredCallback!(ChannelEventAction.NEW_MESSAGE, makeMessage("m1"))
    expect(messages.map(m => m.id)).toEqual(["m1"])

    atTail = false
    rerender()
    registeredCallback!(ChannelEventAction.NEW_MESSAGE, makeMessage("m2"))
    expect(messages.map(m => m.id)).toEqual(["m1"])
  })

  it("applies UPDATED and DELETED unconditionally even while not at the tail", () => {
    let messages: { id: string; content?: string }[] = [{ id: "m1", content: "old" }]
    const setMessages = vi.fn(
      (updater: (prev: { id: string; content?: string }[]) => { id: string; content?: string }[]) => {
        messages = updater(messages)
      }
    )

    renderHook(() =>
      useChatMessageSubscription("c1", "w1", setMessages as never, {
        isAtTail: () => false,
      })
    )

    registeredCallback!(ChannelEventAction.UPDATED_MESSAGE, { id: "m1", content: "new" })
    expect(messages[0].content).toBe("new")

    registeredCallback!(ChannelEventAction.DELETED_MESSAGE, { id: "m1" })
    expect(messages).toEqual([])
  })
})
