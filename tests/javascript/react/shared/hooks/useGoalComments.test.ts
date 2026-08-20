import { act } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { GoalComment } from "~/react/shared/hooks/useGoalComments"
import type { ChannelEventAction } from "~/types/channels"
import { ChannelEventAction as Action } from "~/types/channels"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

// Capture the (stream, params) the hook subscribed with plus its handler so we
// can assert the topic identity and drive channel events directly.
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

import { useGoalComments } from "~/react/shared/hooks/useGoalComments"
import { apiFetch } from "~/react/shared/apiFetch"
import { showFlash } from "~/shared/flash"

import { renderHookWithClient, waitFor } from "../testUtils"

const mockApiFetch = vi.mocked(apiFetch)
const mockShowFlash = vi.mocked(showFlash)

function buildComment(overrides: Partial<GoalComment> = {}): GoalComment {
  return {
    id: "c1",
    content: "Hello",
    parent_id: null,
    closed_at: null,
    created_at: "2026-06-22T00:00:00Z",
    updated_at: "2026-06-22T00:00:00Z",
    user: { id: "u1", display_name: "Ada" } as GoalComment["user"],
    reactions: {},
    replies: [],
    ...overrides,
  }
}

beforeEach(() => {
  channelHandler = null
  channelStream = null
  channelParams = null
  mockApiFetch.mockResolvedValue({ comments: [] } as never)
})
afterEach(() => vi.clearAllMocks())

describe("useGoalComments", () => {
  test("loads the thread list and subscribes to the goal_comments topic by goal id", async () => {
    const { result } = renderHookWithClient(() => useGoalComments("goal-1"))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(mockApiFetch).toHaveBeenCalledWith("/api/goals/goal-1/comments", expect.anything())
    expect(channelStream).toBe("goal_comments")
    expect(channelParams).toEqual({ goal_id: "goal-1" })
  })

  test("a CREATED broadcast inserts the comment with no refetch", async () => {
    const { result } = renderHookWithClient(() => useGoalComments("goal-1"))
    await waitFor(() => expect(result.current.loading).toBe(false))
    mockApiFetch.mockClear()

    act(() => channelHandler!(Action.CREATED, buildComment({ id: "c1" }) as unknown as Record<string, unknown>))

    // A cache write notifies observers on the next microtask, so the re-render is awaited.
    await waitFor(() => expect(result.current.comments.map(c => c.id)).toEqual(["c1"]))
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("a PANEL_UPDATED broadcast replaces the list from its payload rather than refetching", async () => {
    const { result } = renderHookWithClient(() => useGoalComments("goal-1"))
    await waitFor(() => expect(result.current.loading).toBe(false))
    mockApiFetch.mockClear()

    act(() => channelHandler!(Action.PANEL_UPDATED, { comments: [buildComment({ id: "c9" })] }))

    await waitFor(() => expect(result.current.comments.map(c => c.id)).toEqual(["c9"]))
    expect(mockApiFetch).not.toHaveBeenCalled()
  })

  test("a failed create flashes and leaves the list alone, without rejecting to the caller", async () => {
    const { result } = renderHookWithClient(() => useGoalComments("goal-1"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockRejectedValueOnce(new Error("boom"))
    await act(async () => result.current.createComment("Nope"))

    expect(mockShowFlash).toHaveBeenCalledWith("Couldn't post comment. Your text is preserved — try again.")
    expect(result.current.comments).toEqual([])
  })

  test("closing a thread adopts the full list the endpoint answers with", async () => {
    const { result } = renderHookWithClient(() => useGoalComments("goal-1"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce({
      comments: [buildComment({ id: "c1", closed_at: "2026-06-23T00:00:00Z" })],
    } as never)
    await act(async () => result.current.closeThread("c1"))

    await waitFor(() => expect(result.current.comments.map(c => c.closed_at)).toEqual(["2026-06-23T00:00:00Z"]))
  })
})
