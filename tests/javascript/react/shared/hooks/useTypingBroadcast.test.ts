import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { getChannelsClient } from "~/channels/client"
import { useTypingBroadcast } from "~/react/shared/hooks/useTypingBroadcast"
import { ChannelStream } from "~/types/channels"

vi.mock("~/channels/client", () => ({ getChannelsClient: vi.fn(() => null) }))

const mockGetChannelsClient = vi.mocked(getChannelsClient)

function mockClient() {
  const broadcastTo = vi.fn()
  mockGetChannelsClient.mockReturnValue({ broadcastTo } as never)
  return broadcastTo
}

const threadParams = { email_thread_id: "t1" }

function renderThreadTyping() {
  return renderHook(() => useTypingBroadcast({ stream: ChannelStream.EMAIL_THREAD_COMMENTS, params: threadParams }))
}

afterEach(() => {
  vi.useRealTimers()
  mockGetChannelsClient.mockReset()
})

describe("useTypingBroadcast", () => {
  test("emits is_typing:true once per burst, addressed to the topic", () => {
    const broadcastTo = mockClient()
    const { result } = renderThreadTyping()

    act(() => result.current.onType())
    act(() => result.current.onType())

    expect(broadcastTo).toHaveBeenCalledTimes(1)
    expect(broadcastTo).toHaveBeenCalledWith("email_thread_comments", threadParams, {
      type: "typing",
      is_typing: true,
    })
  })

  test("stopTyping emits is_typing:false only once typing has started", () => {
    const broadcastTo = mockClient()
    const { result } = renderThreadTyping()

    act(() => result.current.stopTyping())
    expect(broadcastTo).not.toHaveBeenCalled()

    act(() => result.current.onType())
    act(() => result.current.stopTyping())
    expect(broadcastTo).toHaveBeenLastCalledWith("email_thread_comments", threadParams, {
      type: "typing",
      is_typing: false,
    })
  })

  test("auto-stops after the idle timeout", () => {
    vi.useFakeTimers()
    const broadcastTo = mockClient()
    const { result } = renderThreadTyping()

    act(() => result.current.onType())
    act(() => vi.advanceTimersByTime(3000))

    expect(broadcastTo).toHaveBeenLastCalledWith("email_thread_comments", threadParams, {
      type: "typing",
      is_typing: false,
    })
  })

  test("does nothing when disabled or when params are null", () => {
    const broadcastTo = mockClient()
    const { result: disabled } = renderHook(() =>
      useTypingBroadcast({ stream: ChannelStream.CHAT, params: { chat_id: "c1", workspace_id: "w1" }, enabled: false })
    )
    act(() => disabled.current.onType())

    const { result: noParams } = renderHook(() => useTypingBroadcast({ stream: ChannelStream.CHAT, params: null }))
    act(() => noParams.current.onType())

    expect(broadcastTo).not.toHaveBeenCalled()
  })

  test("emits a stop on unmount when typing was active", () => {
    const broadcastTo = mockClient()
    const { result, unmount } = renderThreadTyping()

    act(() => result.current.onType())
    broadcastTo.mockClear()
    unmount()

    expect(broadcastTo).toHaveBeenCalledWith("email_thread_comments", threadParams, {
      type: "typing",
      is_typing: false,
    })
  })

  test("returns stable callbacks across re-renders", () => {
    mockClient()
    const { result, rerender } = renderThreadTyping()
    const first = result.current
    rerender()
    expect(result.current.onType).toBe(first.onType)
    expect(result.current.stopTyping).toBe(first.stopTyping)
  })
})
