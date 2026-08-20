import { type QueryClient } from "@tanstack/react-query"
import { act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { ChannelEventAction } from "~/types/channels"
import { ChannelEventAction as Action, ChannelEventResource, ChannelStream } from "~/types/channels"

const apiFetchMock = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: apiFetchMock }))

// Capture the channel handler so tests can drive channel events directly, and
// the (stream, params) it subscribed with so we can assert topic identity.
let channelHandler: ((action: ChannelEventAction, data: Record<string, unknown>) => void) | null = null
let channelTarget: { stream: string; params: Record<string, unknown> } | null = null
vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: (
    target: { stream: string; params: Record<string, unknown> } | null,
    _resource: unknown,
    onMessage: typeof channelHandler
  ) => {
    channelTarget = target
    channelHandler = onMessage
  },
}))

// Capture reconnect listeners so tests can fire them.
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

import {
  addCommentToList,
  applyResolvedThread,
  groupIntoThreads,
  removeCommentFromList,
  toggleReactionInList,
  useCommentThreads,
  type Comment,
} from "~/react/composites/editor/features/comments/commentThreads"
import { createCommentUIStore } from "~/react/composites/editor/features/comments/createCommentUIStore"

import { createTestQueryClient, renderHookWithClient } from "../../shared/testUtils"
import { makeComment } from "./commentTestUtils"

const envelope = (comments: Comment[]) => ({ comments, next_cursor: null, has_more: false })
const threadResponse = (comments: Comment[], resolvedAt: string | null = null) => ({
  comment_mark_id: comments[0]?.comment_mark_id ?? "",
  resolved_at: resolvedAt,
  comments,
})

function setup({
  resourceId = "doc-1",
  client = createTestQueryClient(),
  uiStore = createCommentUIStore(),
}: { resourceId?: string; client?: QueryClient; uiStore?: ReturnType<typeof createCommentUIStore> } = {}) {
  const rendered = renderHookWithClient(
    () =>
      useCommentThreads({
        commentsPath: id => `/api/documents/${id}/comments`,
        resourceId,
        channel: { stream: ChannelStream.DOCUMENT_COMMENTS, params: { document_id: resourceId } },
        commentResource: ChannelEventResource.DOCUMENT_COMMENT,
        uiStore,
      }),
    client
  )
  return { ...rendered, uiStore }
}

beforeEach(() => {
  apiFetchMock.mockReset()
  channelHandler = null
  channelTarget = null
  reconnectListeners = []
  mockClient.on.mockClear()
  mockClient.off.mockClear()
})

afterEach(() => {
  vi.clearAllMocks()
})

describe("useCommentThreads — pure cache helpers", () => {
  test("groupIntoThreads buckets comments by mark id", () => {
    const threads = groupIntoThreads([
      makeComment({ id: "c1", comment_mark_id: "m1" }),
      makeComment({ id: "c2", comment_mark_id: "m1" }),
      makeComment({ id: "c3", comment_mark_id: "m2" }),
    ])
    expect(threads).toHaveLength(2)
    expect(threads[0].comments).toHaveLength(2)
    expect(threads[1].markId).toBe("m2")
  })

  test("addCommentToList dedupes by id", () => {
    const c = makeComment({ id: "c1" })
    expect(addCommentToList([c], c)).toHaveLength(1)
    expect(addCommentToList([c], makeComment({ id: "c2" }))).toHaveLength(2)
  })

  test("removeCommentFromList drops the comment", () => {
    expect(removeCommentFromList([makeComment({ id: "c1" })], "c1")).toHaveLength(0)
  })

  test("applyResolvedThread drops the mark when resolved, replaces when reopened", () => {
    const list = [makeComment({ id: "c1", comment_mark_id: "m1" })]
    expect(applyResolvedThread(list, "m1", list, "2026-01-01T00:00:00Z")).toHaveLength(0)
    const reopened = [makeComment({ id: "c1", comment_mark_id: "m1", content: "v2" })]
    const next = applyResolvedThread(list, "m1", reopened, null)
    expect(next[0].content).toBe("v2")
  })

  test("toggleReactionInList adds then removes the viewer", () => {
    const c = makeComment({ id: "c1", reactions: {} })
    const added = toggleReactionInList([c], "c1", "thumbs_up", "u1", "Alice")
    expect(added[0].reactions.thumbs_up).toHaveLength(1)
    const removed = toggleReactionInList(added, "c1", "thumbs_up", "u1", "Alice")
    expect(removed[0].reactions.thumbs_up).toBeUndefined()
  })
})

describe("useCommentThreads — query + mutations", () => {
  test("fetches comments and groups them into threads", async () => {
    apiFetchMock.mockResolvedValue(
      envelope([
        makeComment({ id: "c1", comment_mark_id: "m1" }),
        makeComment({ id: "c2", comment_mark_id: "m1" }),
        makeComment({ id: "c3", comment_mark_id: "m2" }),
      ])
    )
    const { result } = setup()

    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(result.current.threads).toHaveLength(2)
    expect(result.current.threads[0].comments).toHaveLength(2)
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  test("subscribes to the document_comments topic by id", async () => {
    apiFetchMock.mockResolvedValue(envelope([]))
    setup()
    await waitFor(() => expect(channelHandler).not.toBeNull())
    expect(channelTarget).toEqual({ stream: "document_comments", params: { document_id: "doc-1" } })
  })

  test("createComment inserts the returned comment into the cache", async () => {
    apiFetchMock.mockResolvedValueOnce(envelope([]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    apiFetchMock.mockResolvedValueOnce(makeComment({ id: "new-1", comment_mark_id: "m1" }))
    await act(async () => {
      await result.current.createComment("hello", "quoted", "m1")
    })

    await waitFor(() => expect(result.current.threads[0]?.comments.map(c => c.id)).toEqual(["new-1"]))
  })

  test("editComment updates the comment and clears editingCommentId", async () => {
    apiFetchMock.mockResolvedValueOnce(envelope([makeComment({ id: "c1", content: "old" })]))
    const { result, uiStore } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    uiStore.getState().setEditingComment("c1")

    apiFetchMock.mockResolvedValueOnce(makeComment({ id: "c1", content: "new" }))
    await act(async () => {
      await result.current.editComment("c1", "new")
    })

    await waitFor(() => expect(result.current.threads[0].comments[0].content).toBe("new"))
    expect(uiStore.getState().editingCommentId).toBeNull()
  })

  test("deleteComment removes the comment", async () => {
    apiFetchMock.mockResolvedValueOnce(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    apiFetchMock.mockResolvedValueOnce(null)
    await act(async () => {
      await result.current.deleteComment("c1")
    })

    await waitFor(() => expect(result.current.threads).toHaveLength(0))
  })

  test("resolveThread drops the thread", async () => {
    apiFetchMock.mockResolvedValueOnce(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    apiFetchMock.mockResolvedValueOnce(
      threadResponse(
        [makeComment({ id: "c1", comment_mark_id: "m1", resolved_at: "2026-01-01T12:00:00Z" })],
        "2026-01-01T12:00:00Z"
      )
    )
    await act(async () => {
      await result.current.resolveThread("c1")
    })

    await waitFor(() => expect(result.current.threads).toHaveLength(0))
  })

  test("toggleReaction applies optimistically and rolls back on API error", async () => {
    apiFetchMock.mockResolvedValueOnce(envelope([makeComment({ id: "c1", reactions: {} })]))
    const { result, uiStore } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    uiStore.getState().init("u1", "Alice")

    apiFetchMock.mockRejectedValueOnce(new Error("server error"))
    await act(async () => {
      await result.current.toggleReaction("c1", "thumbs_up")
    })

    // Rolled back to no reactions after the failure (onError restores the snapshot).
    await waitFor(() => expect(result.current.threads[0].comments[0].reactions.thumbs_up).toBeUndefined())
  })

  test("toggleReaction reconciles with the server response on success", async () => {
    apiFetchMock.mockResolvedValueOnce(envelope([makeComment({ id: "c1", reactions: {} })]))
    const { result, uiStore } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    uiStore.getState().init("u1", "Alice")

    apiFetchMock.mockResolvedValueOnce(
      makeComment({ id: "c1", reactions: { thumbs_up: [{ id: "u1", display_name: "Alice" }] } })
    )
    await act(async () => {
      await result.current.toggleReaction("c1", "thumbs_up")
    })

    await waitFor(() => expect(result.current.threads[0].comments[0].reactions.thumbs_up).toHaveLength(1))
  })
})

describe("useCommentThreads — channel events", () => {
  test("CREATED appends and dedupes by id", async () => {
    apiFetchMock.mockResolvedValue(envelope([]))
    const { result } = setup()
    await waitFor(() => expect(channelHandler).not.toBeNull())

    const comment = makeComment({ id: "c1", comment_mark_id: "m1" })
    act(() => channelHandler!(Action.CREATED, comment as unknown as Record<string, unknown>))
    await waitFor(() => expect(result.current.threads[0]?.comments.map(c => c.id)).toEqual(["c1"]))

    // A duplicate CREATED (e.g. the echo of an optimistic insert) is a no-op.
    act(() => channelHandler!(Action.CREATED, comment as unknown as Record<string, unknown>))
    expect(result.current.threads[0].comments).toHaveLength(1)
  })

  test("UPDATED reconciles content", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", content: "old" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    act(() =>
      channelHandler!(Action.UPDATED, makeComment({ id: "c1", content: "new" }) as unknown as Record<string, unknown>)
    )
    await waitFor(() => expect(result.current.threads[0].comments[0].content).toBe("new"))
  })

  test("DELETED removes the comment", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    act(() => channelHandler!(Action.DELETED, { id: "c1" }))
    await waitFor(() => expect(result.current.threads).toHaveLength(0))
  })

  test("RESOLVED drops the thread", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    act(() =>
      channelHandler!(Action.RESOLVED, {
        comment_mark_id: "m1",
        comments: [makeComment({ id: "c1", comment_mark_id: "m1", resolved_at: "2026-01-01T12:00:00Z" })],
      })
    )
    await waitFor(() => expect(result.current.threads).toHaveLength(0))
  })

  test("RESOLVED reopen replaces the thread's comments", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", comment_mark_id: "m1", content: "old" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    act(() =>
      channelHandler!(Action.RESOLVED, {
        comment_mark_id: "m1",
        comments: [makeComment({ id: "c1", comment_mark_id: "m1", content: "new", resolved_at: null })],
      })
    )
    await waitFor(() => expect(result.current.threads[0].comments[0].content).toBe("new"))
  })

  test("REACTION_TOGGLED merges reactions", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    const reactions = { thumbs_up: [{ id: "u2", display_name: "Bob" }] }
    act(() => channelHandler!(Action.REACTION_TOGGLED, { comment_id: "c1", reactions }))
    await waitFor(() => expect(result.current.threads[0].comments[0].reactions).toEqual(reactions))
  })
})

describe("useCommentThreads — comment deep link (#comment-<id>)", () => {
  // A controllable rAF queue so a test can render the mark between frames and
  // assert the scroll retry picks it up.
  let rafQueue: FrameRequestCallback[]
  const flushRaf = () => {
    const q = rafQueue
    rafQueue = []
    q.forEach(cb => cb(0))
  }
  const mountMark = (markId: string): HTMLElement => {
    const el = document.createElement("span")
    el.setAttribute("data-comment-id", markId)
    vi.spyOn(el, "scrollIntoView").mockImplementation(() => {})
    document.body.appendChild(el)
    return el
  }

  beforeEach(() => {
    rafQueue = []
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => rafQueue.push(cb))
    vi.stubGlobal("cancelAnimationFrame", () => {})
    window.location.hash = ""
    document.body.innerHTML = ""
  })
  afterEach(() => {
    vi.unstubAllGlobals()
    window.location.hash = ""
    document.body.innerHTML = ""
  })

  test("activates the target thread and scrolls its already-rendered mark into view", async () => {
    const mark = mountMark("m1")
    window.location.hash = "#comment-c1"
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))

    const { result, uiStore } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    await waitFor(() => expect(uiStore.getState().activeCommentId).toBe("m1"))
    act(() => flushRaf())
    expect(mark.scrollIntoView).toHaveBeenCalled()
  })

  test("retries the scroll until the mark renders from a later Yjs sync", async () => {
    window.location.hash = "#comment-c1"
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))

    const { result, uiStore } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    await waitFor(() => expect(uiStore.getState().activeCommentId).toBe("m1"))

    // Mark absent on the first frame: the retry reschedules rather than scrolling.
    act(() => flushRaf())
    const mark = mountMark("m1")
    act(() => flushRaf())
    expect(mark.scrollIntoView).toHaveBeenCalled()
  })

  test("no-ops for a hash naming an unknown comment", async () => {
    window.location.hash = "#comment-missing"
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))

    const { result, uiStore } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    expect(uiStore.getState().activeCommentId).toBeNull()
  })

  test("does nothing without a comment hash", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1", comment_mark_id: "m1" })]))

    const { result, uiStore } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    expect(uiStore.getState().activeCommentId).toBeNull()
    expect(rafQueue).toHaveLength(0)
  })
})

describe("useCommentThreads — liveness and resource scoping", () => {
  test("distinct resources keep distinct caches", async () => {
    const client = createTestQueryClient()
    apiFetchMock.mockImplementation((url: string) =>
      Promise.resolve(
        url.includes("doc-1") ? envelope([makeComment({ id: "a" })]) : envelope([makeComment({ id: "b" })])
      )
    )

    const docA = setup({ resourceId: "doc-1", client })
    await waitFor(() => expect(docA.result.current.threads[0]?.comments[0]?.id).toBe("a"))
    const docB = setup({ resourceId: "doc-2", client })
    await waitFor(() => expect(docB.result.current.threads[0]?.comments[0]?.id).toBe("b"))

    expect(docA.result.current.threads[0].comments[0].id).toBe("a")
  })

  test("refetchComments resolves only after fresh data lands in the cache", async () => {
    apiFetchMock.mockResolvedValueOnce(envelope([makeComment({ id: "c1" })]))
    const { result, client } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))

    apiFetchMock.mockResolvedValueOnce(envelope([makeComment({ id: "c1" }), makeComment({ id: "c2" })]))
    await act(async () => {
      await result.current.refetchComments()
    })

    // The promise resolved, so the cache already holds the fresh list.
    expect(client.getQueryData(["comments", "doc-1"])).toHaveLength(2)
  })

  test("a cold first mount does not double-fetch", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    // No re-arm catch-up fires on a cold mount (cache was empty when the effect ran).
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
  })

  test("a remount within gcTime invalidates to catch up on missed events", async () => {
    const client = createTestQueryClient()
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1" })]))

    const first = setup({ client })
    await waitFor(() => expect(first.result.current.isLoaded).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(1)
    first.unmount()

    // Remount against the same client: the cache is warm, so the re-arm effect
    // invalidates and refetches to recover events missed while unmounted.
    setup({ client })
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))
  })

  test("a reconnect triggers a refetch", async () => {
    apiFetchMock.mockResolvedValue(envelope([makeComment({ id: "c1" })]))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoaded).toBe(true))
    expect(apiFetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      reconnectListeners.forEach(l => l())
    })
    await waitFor(() => expect(apiFetchMock).toHaveBeenCalledTimes(2))
  })
})
