import { act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { ChannelEventAction } from "~/types/channels"
import { ChannelEventAction as Action } from "~/types/channels"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

// The optimistic reaction needs the viewer's display name; the channel new-comment
// guard needs their id. Both come from useCurrentUser — pin it to a fixed viewer.
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({
    user: { id: "viewer", display_name: "Viewer", picture: null },
    clientConfig: null,
    loading: false,
    error: null,
  }),
}))

// Capture the channel handler so tests drive events directly, plus the
// (stream, params) it subscribed with so we can assert the topic identity.
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

// useReconnectInvalidate subscribes on the channels client; capture its reconnect
// listeners so a test can fire a reconnect.
let reconnectListeners: Array<() => void> = []
const mockClient = {
  on: vi.fn((event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.push(cb)
  }),
  off: vi.fn((event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners = reconnectListeners.filter(l => l !== cb)
  }),
}
vi.mock("~/channels/client", () => ({ getChannelsClient: () => mockClient }))

import { apiFetch } from "~/react/shared/apiFetch"
import { usePostComments } from "~/react/features/postShow/hooks/usePostComments"
import type { PostComment } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"

import { createTestQueryClient, renderHookWithClient } from "../../shared/testUtils"
import { buildComment, buildUser } from "./fixtures"

const mockedFetch = vi.mocked(apiFetch)
const mockedFlash = vi.mocked(showFlash)

const envelope = (comments: PostComment[]) => ({ comments, next_cursor: null, has_more: false })

interface SetupOverrides {
  currentUserId?: string
  initial?: PostComment[]
  initialOriginal?: PostComment | null
}

// Renders the hook under a fresh QueryClient, then flushes the mount so the seed
// (initialData) and the remount catch-up invalidate settle. The catch-up fires a
// background GET only when the query is enabled (an original comment is present);
// letting it resolve against the default mock here means per-test
// mockResolvedValueOnce values are consumed only by the action under test.
async function setup(overrides: SetupOverrides = {}) {
  const currentUserId = overrides.currentUserId ?? "viewer"
  const initial = overrides.initial ?? []
  const initialOriginal = overrides.initialOriginal ?? null
  mockedFetch.mockResolvedValue(envelope(initialOriginal ? [...initial, initialOriginal] : initial))
  const onRemoteCreate = vi.fn()
  const rendered = renderHookWithClient(
    () => usePostComments({ postId: "post-1", currentUserId, initial, initialOriginal, onRemoteCreate }),
    createTestQueryClient()
  )
  await act(async () => {})
  return { ...rendered, onRemoteCreate }
}

beforeEach(() => {
  channelHandler = null
  channelStream = null
  channelParams = null
  reconnectListeners = []
  mockClient.on.mockClear()
  mockClient.off.mockClear()
  mockedFetch.mockReset()
})
afterEach(() => vi.clearAllMocks())

describe("usePostComments", () => {
  test("subscribes to the post_comments topic by post id", async () => {
    await setup()
    expect(channelStream).toBe("post_comments")
    expect(channelParams).toEqual({ post_id: "post-1" })
  })

  test("seeds the original and top-level split from the initial props", async () => {
    const { result } = await setup({
      initial: [buildComment({ id: "c1" })],
      initialOriginal: buildComment({ id: "orig", content: "Post body" }),
    })
    expect(result.current.original?.id).toBe("orig")
    expect(result.current.topLevel.map(c => c.id)).toEqual(["c1"])
  })

  test("local createComment inserts the returned comment", async () => {
    const { result } = await setup()
    mockedFetch.mockResolvedValueOnce(buildComment({ id: "new-1", content: "fresh" }))

    await act(async () => {
      await result.current.createComment("fresh")
    })

    await waitFor(() => expect(result.current.topLevel.map(c => c.id)).toEqual(["new-1"]))
  })

  test("local createComment routes a reply under its parent", async () => {
    const { result } = await setup({ initial: [buildComment({ id: "p1" })] })
    mockedFetch.mockResolvedValueOnce(buildComment({ id: "r1", parent_id: "p1" }))

    await act(async () => {
      await result.current.createComment("a reply", { parentId: "p1" })
    })

    await waitFor(() => expect(result.current.topLevel[0].replies.map(c => c.id)).toEqual(["r1"]))
  })

  test("createComment failure flashes and returns null, preserving nothing in the tree", async () => {
    const { result } = await setup()
    mockedFetch.mockRejectedValueOnce(new Error("boom"))

    let returned: PostComment | null = null
    await act(async () => {
      returned = await result.current.createComment("fresh")
    })

    expect(returned).toBeNull()
    expect(mockedFlash).toHaveBeenCalledWith("Couldn't post comment. Your text is preserved — try again.")
    expect(result.current.topLevel).toHaveLength(0)
  })

  test("channel CREATED appends, dedupes by id, and fires onRemoteCreate once", async () => {
    const { result, onRemoteCreate } = await setup()
    const comment = buildComment({ id: "c1" })

    act(() => channelHandler!(Action.CREATED, comment as unknown as Record<string, unknown>))
    await waitFor(() => expect(result.current.topLevel.map(c => c.id)).toEqual(["c1"]))
    expect(onRemoteCreate).toHaveBeenCalledTimes(1)

    // Duplicate CREATED for the same id is ignored (no author-skip on the wire).
    act(() => channelHandler!(Action.CREATED, comment as unknown as Record<string, unknown>))
    await waitFor(() => expect(result.current.topLevel).toHaveLength(1))
    expect(onRemoteCreate).toHaveBeenCalledTimes(1)
  })

  test("channel CREATED appends the viewer's own comment without raising the indicator", async () => {
    const { result, onRemoteCreate } = await setup({ currentUserId: "viewer" })
    const ownComment = buildComment({ id: "mine", user: buildUser({ id: "viewer" }) })

    act(() => channelHandler!(Action.CREATED, ownComment as unknown as Record<string, unknown>))
    await waitFor(() => expect(result.current.topLevel.map(c => c.id)).toEqual(["mine"]))
    expect(onRemoteCreate).not.toHaveBeenCalled()
  })

  test("channel UPDATED reconciles content", async () => {
    const { result } = await setup({ initial: [buildComment({ id: "c1", content: "old" })] })
    act(() =>
      channelHandler!(Action.UPDATED, buildComment({ id: "c1", content: "new" }) as unknown as Record<string, unknown>)
    )
    await waitFor(() => expect(result.current.topLevel[0].content).toBe("new"))
  })

  test("channel DELETED removes the comment", async () => {
    const { result } = await setup({ initial: [buildComment({ id: "c1" })] })
    act(() => channelHandler!(Action.DELETED, { id: "c1" }))
    await waitFor(() => expect(result.current.topLevel).toHaveLength(0))
  })

  test("channel REACTION_TOGGLED merges reactions", async () => {
    const { result } = await setup({ initial: [buildComment({ id: "c1" })] })
    const reactions = { thumbs_up: [{ id: "u1", display_name: "Bob" }] }
    act(() => channelHandler!(Action.REACTION_TOGGLED, { comment_id: "c1", reactions }))
    await waitFor(() => expect(result.current.topLevel[0].reactions).toEqual(reactions))
  })

  test("channel UPDATED to the original updates the original, not the top-level list", async () => {
    const { result } = await setup({ initialOriginal: buildComment({ id: "orig", content: "old" }) })
    act(() =>
      channelHandler!(Action.UPDATED, buildComment({ id: "orig", content: "new" }) as unknown as Record<string, unknown>)
    )
    await waitFor(() => expect(result.current.original?.content).toBe("new"))
    expect(result.current.topLevel).toHaveLength(0)
  })

  test("reactions on the original comment update the original, not the tree", async () => {
    const { result } = await setup({ initialOriginal: buildComment({ id: "orig" }) })
    mockedFetch.mockResolvedValueOnce(
      buildComment({ id: "orig", reactions: { heart: [{ id: "viewer", display_name: "Viewer" }] } })
    )

    await act(async () => {
      result.current.toggleReaction("orig", "heart")
    })

    await waitFor(() => expect(result.current.original?.reactions.heart).toHaveLength(1))
    expect(result.current.topLevel).toHaveLength(0)
  })

  test("toggleReaction applies optimistically while the request is in flight", async () => {
    const { result } = await setup({ initial: [buildComment({ id: "c1", reactions: {} })] })

    // Hold the POST open so the optimistic write is observable before it resolves.
    let resolvePost: (value: PostComment) => void = () => {}
    mockedFetch.mockReturnValueOnce(new Promise<PostComment>(resolve => (resolvePost = resolve)))

    await act(async () => {
      result.current.toggleReaction("c1", "thumbs_up")
    })

    // The viewer's reaction shows immediately, before the server responds.
    await waitFor(() => expect(result.current.topLevel[0].reactions.thumbs_up).toHaveLength(1))
    expect(result.current.topLevel[0].reactions.thumbs_up?.[0].id).toBe("viewer")

    await act(async () => {
      resolvePost(buildComment({ id: "c1", reactions: { thumbs_up: [{ id: "viewer", display_name: "Viewer" }] } }))
    })
    await waitFor(() => expect(result.current.topLevel[0].reactions.thumbs_up).toHaveLength(1))
  })

  test("toggleReaction rolls back the optimistic write when the request fails", async () => {
    const { result } = await setup({ initial: [buildComment({ id: "c1", reactions: {} })] })
    mockedFetch.mockRejectedValueOnce(new Error("server error"))

    await act(async () => {
      result.current.toggleReaction("c1", "thumbs_up")
    })

    // Rolled back to no reactions after the failure (onError restores the snapshot).
    await waitFor(() => expect(result.current.topLevel[0].reactions.thumbs_up).toBeUndefined())
  })

  test("toggleReaction merges only reactions on success, preserving updated_at", async () => {
    // The reaction response carries a transient bumped updated_at (server auto_now
    // in memory) that must not flip the "(edited)" indicator.
    const comment = buildComment({ id: "c1", created_at: "2026-05-25T14:00:00Z", updated_at: "2026-05-25T14:00:00Z" })
    const { result } = await setup({ initial: [comment] })
    mockedFetch.mockResolvedValueOnce(
      buildComment({
        id: "c1",
        created_at: "2026-05-25T14:00:00Z",
        updated_at: "2026-05-28T20:59:03Z",
        reactions: { eyes: [{ id: "viewer", display_name: "Viewer" }] },
      })
    )

    await act(async () => {
      result.current.toggleReaction("c1", "eyes")
    })

    await waitFor(() => expect(result.current.topLevel[0].reactions.eyes).toHaveLength(1))
    expect(result.current.topLevel[0].updated_at).toBe("2026-05-25T14:00:00Z")
  })

  test("setOriginalContent optimistically edits the post body", async () => {
    const { result } = await setup({ initialOriginal: buildComment({ id: "orig", content: "old body" }) })

    act(() => result.current.setOriginalContent("new body"))

    await waitFor(() => expect(result.current.original?.content).toBe("new body"))
  })

  test("fetch refetches the canonical list", async () => {
    const { result } = await setup({ initialOriginal: buildComment({ id: "orig" }) })

    mockedFetch.mockResolvedValue(envelope([buildComment({ id: "orig" }), buildComment({ id: "c1" })]))
    await act(async () => {
      await result.current.fetch()
    })

    await waitFor(() => expect(result.current.topLevel.map(c => c.id)).toEqual(["c1"]))
  })

  test("recovers missed broadcasts on socket reconnect", async () => {
    const { result } = await setup({ initialOriginal: buildComment({ id: "orig" }) })

    mockedFetch.mockResolvedValue(envelope([buildComment({ id: "orig" }), buildComment({ id: "c9" })]))
    await act(async () => {
      reconnectListeners.forEach(fn => fn())
    })

    await waitFor(() => expect(result.current.topLevel.map(c => c.id)).toEqual(["c9"]))
  })
})
