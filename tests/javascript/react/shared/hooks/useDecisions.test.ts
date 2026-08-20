import { act, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { ChannelEventAction } from "~/types/channels"
import { ChannelEventAction as Action } from "~/types/channels"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
vi.mock("~/shared/flash", () => ({ showFlash: vi.fn() }))

// Capture the channel handler so tests can drive DECISIONS_CHANGED directly.
let channelHandler: ((action: ChannelEventAction, data: Record<string, unknown>) => void) | null = null
vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: (
    _target: { stream: string; params: Record<string, unknown> } | null,
    _resource: unknown,
    onMessage: typeof channelHandler
  ) => {
    channelHandler = onMessage
  },
}))

// Capture reconnect listeners (useReconnectInvalidate subscribes here) so tests
// can fire a reconnect.
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
import { useDecisions } from "~/react/shared/hooks/useDecisions"

import { createTestQueryClient, renderHookWithClient } from "../../shared/testUtils"

const mockedFetch = vi.mocked(apiFetch)

function buildListResponse(decisions: unknown[]) {
  return { decisions, next_cursor: null, has_more: false }
}

function decision(commentGid: string, id = "d1") {
  return {
    id,
    comment_gid: commentGid,
    comment_preview: "Decided",
    decided_by: { id: "u1", display_name: "Alice", picture: null },
    decided_at: "2026-06-01T00:00:00Z",
  }
}

beforeEach(() => {
  channelHandler = null
  reconnectListeners = []
  mockClient.on.mockClear()
  mockClient.off.mockClear()
  mockedFetch.mockReset()
})
afterEach(() => vi.clearAllMocks())

function setup(workspaceId = "ws-1") {
  return renderHookWithClient(() => useDecisions({ workspaceId }), createTestQueryClient())
}

describe("useDecisions", () => {
  test("issues no request until the workspace id is known", async () => {
    // Islands whose show response loads async (e.g. chat) mount with an empty
    // workspaceId for a frame; the hook must not fire GET /api/workspaces//decisions.
    setup("")
    await act(async () => {})
    expect(mockedFetch).not.toHaveBeenCalled()
  })

  test("loads decisions on mount and indexes them by comment_gid", async () => {
    mockedFetch.mockResolvedValueOnce(buildListResponse([decision("gid://convictional/ChatMessage/c1")]))
    const { result } = setup()

    await waitFor(() => expect(result.current.decisions).toHaveLength(1))
    expect(result.current.decisionsByGid.get("gid://convictional/ChatMessage/c1")?.id).toBe("d1")
  })

  test("toggleDecision POSTs the comment gid when undecided then refetches", async () => {
    mockedFetch.mockResolvedValueOnce(buildListResponse([])) // initial load
    const { result } = setup()
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    mockedFetch.mockResolvedValueOnce(undefined) // POST
    mockedFetch.mockResolvedValueOnce(buildListResponse([decision("gid://convictional/ChatMessage/c1")])) // refetch
    await act(async () => {
      await result.current.toggleDecision("gid://convictional/ChatMessage/c1")
    })

    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/ws-1/decisions", {
      method: "POST",
      body: JSON.stringify({ comment_gid: "gid://convictional/ChatMessage/c1" }),
    })
    await waitFor(() => expect(result.current.decisions).toHaveLength(1))
  })

  test("toggleDecision DELETEs the existing decision when already decided", async () => {
    mockedFetch.mockResolvedValueOnce(buildListResponse([decision("gid://convictional/ChatMessage/c1", "d9")]))
    const { result } = setup()
    await waitFor(() => expect(result.current.decisions).toHaveLength(1))

    mockedFetch.mockResolvedValueOnce(undefined) // DELETE
    mockedFetch.mockResolvedValueOnce(buildListResponse([])) // refetch
    await act(async () => {
      await result.current.toggleDecision("gid://convictional/ChatMessage/c1")
    })

    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/ws-1/decisions/d9", { method: "DELETE" })
  })

  test("ignores a re-entrant toggle of the same comment while one is in flight", async () => {
    mockedFetch.mockResolvedValueOnce(buildListResponse([])) // initial load
    const { result } = setup()
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    // Hold the POST open so the second click lands while the first is in flight.
    let resolvePost: () => void = () => {}
    mockedFetch.mockReturnValueOnce(new Promise<void>(resolve => (resolvePost = () => resolve())))
    mockedFetch.mockResolvedValueOnce(buildListResponse([decision("gid://convictional/ChatMessage/c1")])) // refetch

    await act(async () => {
      const first = result.current.toggleDecision("gid://convictional/ChatMessage/c1")
      const second = result.current.toggleDecision("gid://convictional/ChatMessage/c1")
      resolvePost()
      await Promise.all([first, second])
    })

    // The second click was dropped: one POST only (plus initial load and refetch).
    const posts = mockedFetch.mock.calls.filter(([, opts]) => (opts as RequestInit | undefined)?.method === "POST")
    expect(posts).toHaveLength(1)
  })

  test("DECISIONS_CHANGED on the channel refetches the list", async () => {
    mockedFetch.mockResolvedValueOnce(buildListResponse([]))
    const { result } = setup()
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    mockedFetch.mockResolvedValueOnce(buildListResponse([decision("gid://convictional/ChatMessage/c2")]))
    act(() => channelHandler!(Action.DECISIONS_CHANGED, {}))
    await waitFor(() => expect(result.current.decisions).toHaveLength(1))
  })

  test("refetches the list when the socket reconnects", async () => {
    mockedFetch.mockResolvedValueOnce(buildListResponse([]))
    const { result } = setup()
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))

    mockedFetch.mockResolvedValueOnce(buildListResponse([decision("gid://convictional/ChatMessage/c3")]))
    act(() => reconnectListeners.forEach(fn => fn()))
    await waitFor(() => expect(result.current.decisions).toHaveLength(1))
  })

  test("toggleDecision keeps a stable identity across decision changes but reads the latest map", async () => {
    mockedFetch.mockResolvedValueOnce(buildListResponse([])) // initial load
    const { result } = setup()
    await waitFor(() => expect(mockedFetch).toHaveBeenCalledTimes(1))
    const firstToggle = result.current.toggleDecision

    // A channel signal refetches and now reports c1 as decided.
    mockedFetch.mockResolvedValueOnce(buildListResponse([decision("gid://convictional/ChatMessage/c1", "d9")]))
    act(() => channelHandler!(Action.DECISIONS_CHANGED, {}))
    await waitFor(() => expect(result.current.decisions).toHaveLength(1))

    // Identity is unchanged, so memoized message bubbles won't re-render...
    expect(result.current.toggleDecision).toBe(firstToggle)

    // ...yet the stable callback still sees the latest map: toggling c1 now DELETEs.
    mockedFetch.mockResolvedValueOnce(undefined) // DELETE
    mockedFetch.mockResolvedValueOnce(buildListResponse([])) // refetch
    await act(async () => {
      await result.current.toggleDecision("gid://convictional/ChatMessage/c1")
    })
    expect(mockedFetch).toHaveBeenCalledWith("/api/workspaces/ws-1/decisions/d9", { method: "DELETE" })
  })
})
