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

import { useEmailThreadCommentsChannel } from "~/react/features/emailThreadShow/hooks/useEmailThreadCommentsChannel"

const noopHandlers = {
  onCommentCreated: vi.fn(),
  onCommentUpdated: vi.fn(),
  onCommentRemoved: vi.fn(),
  onReactionToggled: vi.fn(),
}

const COMMENT = {
  id: "c1",
  content: "edited",
  user: { id: "u1", display_name: "Alice", picture: null },
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:10Z",
  reactions: {},
  link_preview: null,
  attachments: [],
}

beforeEach(() => {
  registeredHandler = null
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("useEmailThreadCommentsChannel", () => {
  it("TYPING replaces the typing user set wholesale and clears after the silence timeout", () => {
    const { result } = renderHook(() => useEmailThreadCommentsChannel({ emailThreadId: "t", ...noopHandlers }))
    act(() => {
      registeredHandler?.(ChannelEventAction.TYPING, {
        typing_users: [{ id: "u1", display_name: "Alice", picture: null }],
      })
    })
    expect(result.current.typingUsers.map(u => u.display_name)).toEqual(["Alice"])

    act(() => {
      registeredHandler?.(ChannelEventAction.TYPING, {
        typing_users: [
          { id: "u2", display_name: "Bob", picture: null },
          { id: "u3", display_name: "Carol", picture: null },
        ],
      })
    })
    expect(result.current.typingUsers.map(u => u.display_name)).toEqual(["Bob", "Carol"])

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current.typingUsers).toHaveLength(0)
  })

  it("CREATED forwards the comment payload", () => {
    const onCommentCreated = vi.fn()
    renderHook(() => useEmailThreadCommentsChannel({ emailThreadId: "t", ...noopHandlers, onCommentCreated }))
    act(() => {
      registeredHandler?.(ChannelEventAction.CREATED, { comment: COMMENT })
    })
    expect(onCommentCreated).toHaveBeenCalledWith(COMMENT)
  })

  it("UPDATED forwards the comment and REMOVED forwards the id", () => {
    const onCommentUpdated = vi.fn()
    const onCommentRemoved = vi.fn()
    renderHook(() =>
      useEmailThreadCommentsChannel({ emailThreadId: "t", ...noopHandlers, onCommentUpdated, onCommentRemoved })
    )
    act(() => {
      registeredHandler?.(ChannelEventAction.UPDATED, { comment: COMMENT })
      registeredHandler?.(ChannelEventAction.REMOVED, { comment_id: "c2" })
    })
    expect(onCommentUpdated).toHaveBeenCalledWith(COMMENT)
    expect(onCommentRemoved).toHaveBeenCalledWith("c2")
  })

  it("REACTION_TOGGLED forwards the comment id and reactions map, ignoring malformed payloads", () => {
    const onReactionToggled = vi.fn()
    renderHook(() => useEmailThreadCommentsChannel({ emailThreadId: "t", ...noopHandlers, onReactionToggled }))
    const reactions = { thumbs_up: [{ id: "u1", display_name: "Alice" }] }
    act(() => {
      registeredHandler?.(ChannelEventAction.REACTION_TOGGLED, { comment_id: "c1", reactions })
    })
    expect(onReactionToggled).toHaveBeenCalledWith("c1", reactions)

    onReactionToggled.mockClear()
    act(() => {
      registeredHandler?.(ChannelEventAction.REACTION_TOGGLED, { comment_id: "c1" })
      registeredHandler?.(ChannelEventAction.REACTION_TOGGLED, { reactions })
    })
    expect(onReactionToggled).not.toHaveBeenCalled()
  })
})
