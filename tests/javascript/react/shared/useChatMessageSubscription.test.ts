import { act, renderHook } from "@testing-library/react"
import { useState } from "react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { ChannelEventAction, ChannelEventResource } from "~/types/channels"

type ChannelCallback = (action: ChannelEventAction, data: Record<string, unknown>) => void

// Capture the callback handed to the channel so tests can drive incoming events.
let channelCallback: ChannelCallback | null = null
vi.mock("~/react/shared/hooks/useChatChannel", () => ({
  useChatChannel: (
    _chatId: string | null,
    _workspaceId: string | null,
    _resource: ChannelEventResource,
    onMessage: ChannelCallback
  ) => {
    channelCallback = onMessage
  },
}))

vi.mock("~/react/shared/reportOutOfOrderDelivery", () => ({
  reportOutOfOrderDelivery: vi.fn(),
}))

import { useChatMessageSubscription } from "~/react/shared/hooks/useChatMessageSubscription"
import { reportOutOfOrderDelivery } from "~/react/shared/reportOutOfOrderDelivery"
import type { ChatMessage } from "~/react/shared/types"

const mockedReport = vi.mocked(reportOutOfOrderDelivery)

function makeMessage(id: string, createdAt: string): ChatMessage {
  return { id, created_at: createdAt } as ChatMessage
}

function renderSubscription(initial: ChatMessage[]) {
  return renderHook(() => {
    const [messages, setMessages] = useState(initial)
    useChatMessageSubscription("chat-1", "ws-1", setMessages)
    return messages
  })
}

function deliver(msg: ChatMessage): void {
  act(() => {
    channelCallback?.(ChannelEventAction.NEW_MESSAGE, msg as unknown as Record<string, unknown>)
  })
}

beforeEach(() => {
  channelCallback = null
  mockedReport.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("useChatMessageSubscription", () => {
  test("reports an out-of-order arrival after the updater commits", () => {
    const { result } = renderSubscription([makeMessage("a", "2026-06-29T10:00:02Z")])

    deliver(makeMessage("b", "2026-06-29T10:00:01Z"))

    expect(result.current.map(m => m.id)).toEqual(["b", "a"])
    expect(mockedReport).toHaveBeenCalledTimes(1)
    expect(mockedReport).toHaveBeenCalledWith({
      chatId: "chat-1",
      messageId: "b",
      messageCreatedAt: "2026-06-29T10:00:01Z",
      tailCreatedAt: "2026-06-29T10:00:02Z",
      gapMs: 1000,
    })
  })

  test("does not report an in-order arrival", () => {
    const { result } = renderSubscription([makeMessage("a", "2026-06-29T10:00:01Z")])

    deliver(makeMessage("b", "2026-06-29T10:00:02Z"))

    expect(result.current.map(m => m.id)).toEqual(["a", "b"])
    expect(mockedReport).not.toHaveBeenCalled()
  })

  test("does not report a duplicate message", () => {
    const { result } = renderSubscription([makeMessage("a", "2026-06-29T10:00:02Z")])

    deliver(makeMessage("a", "2026-06-29T10:00:02Z"))

    expect(result.current.map(m => m.id)).toEqual(["a"])
    expect(mockedReport).not.toHaveBeenCalled()
  })
})
