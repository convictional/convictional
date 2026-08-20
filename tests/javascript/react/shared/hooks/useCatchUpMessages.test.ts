import { renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
}))

// Capture the "reconnected" handler so tests can fire a reconnect directly.
let reconnectHandler: (() => void) | undefined
const channelClient = {
  on: vi.fn((event: string, handler: () => void) => {
    if (event === "reconnected") reconnectHandler = handler
  }),
  off: vi.fn(),
}
vi.mock("~/channels/client", () => ({
  getChannelsClient: vi.fn(() => channelClient),
}))

import { apiFetch } from "~/react/shared/apiFetch"
import { useCatchUpMessages } from "~/react/shared/hooks/useCatchUpMessages"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  reconnectHandler = undefined
})

afterEach(() => {
  vi.clearAllMocks()
})

function makeMessage(id: string, createdAt: string) {
  return { id, created_at: createdAt } as never
}

describe("useCatchUpMessages reconnect gating", () => {
  it("merges latest messages on reconnect when at the tail", async () => {
    mockApiFetch.mockResolvedValue({ messages: [makeMessage("m1", "2026-01-01T00:00:00Z")], next_cursor: null, has_more: false })
    const setMessages = vi.fn()

    renderHook(() =>
      useCatchUpMessages({
        chatId: "c1",
        workspaceId: "w1",
        setMessages: setMessages as never,
        onInitialLoad: vi.fn(),
        isAtTail: () => true,
      })
    )
    await waitFor(() => expect(reconnectHandler).toBeDefined())
    mockApiFetch.mockClear()

    mockApiFetch.mockResolvedValueOnce({
      messages: [makeMessage("m2", "2026-01-01T00:01:00Z")],
      next_cursor: null,
      has_more: false,
    })
    reconnectHandler!()
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/chats/c1/messages", expect.anything()))
  })

  it("does not merge if the user jumps into a historical window while the reconnect fetch is in flight", async () => {
    // Race: the gate passes at reconnect time (live tail), but the user jumps
    // before the fetch resolves. Merging now would splice the latest page onto
    // the window and sort it, leaving a gap. The post-await re-check prevents it.
    let atTail = true
    const setMessages = vi.fn()

    renderHook(() =>
      useCatchUpMessages({
        chatId: "c1",
        workspaceId: "w1",
        setMessages: setMessages as never,
        onInitialLoad: vi.fn(),
        isAtTail: () => atTail,
      })
    )
    await waitFor(() => expect(reconnectHandler).toBeDefined())
    mockApiFetch.mockClear()
    setMessages.mockClear() // drop the mount initial-load call; we only care about the reconnect merge

    // The reconnect fetch is in flight; resolve it only after the jump flips the flag.
    let resolveFetch: (value: unknown) => void = () => {}
    mockApiFetch.mockReturnValueOnce(new Promise(resolve => (resolveFetch = resolve)) as never)

    reconnectHandler!()
    expect(mockApiFetch).toHaveBeenCalledWith("/api/chats/c1/messages", expect.anything())

    // User jumps into a historical window, then the in-flight fetch resolves.
    atTail = false
    resolveFetch({ messages: [makeMessage("m2", "2026-01-01T00:01:00Z")], next_cursor: null, has_more: false })
    // Flush the microtask queue so onReconnect's resolved .then (the gate
    // re-check + merge) runs before we assert — otherwise the merge simply
    // hasn't happened yet and the test would pass for the wrong reason.
    await Promise.resolve()

    // The latest page must NOT have been merged into the window.
    expect(setMessages).not.toHaveBeenCalled()
  })

  it("skips the reconnect merge while not at the tail (no fetch)", async () => {
    mockApiFetch.mockResolvedValue({ messages: [], next_cursor: null, has_more: false })
    const setMessages = vi.fn()

    renderHook(() =>
      useCatchUpMessages({
        chatId: "c1",
        workspaceId: "w1",
        setMessages: setMessages as never,
        onInitialLoad: vi.fn(),
        isAtTail: () => false,
      })
    )
    await waitFor(() => expect(reconnectHandler).toBeDefined())
    mockApiFetch.mockClear()

    reconnectHandler!()
    // No reconnect fetch should be issued while not at the tail.
    expect(mockApiFetch).not.toHaveBeenCalled()
  })
})
