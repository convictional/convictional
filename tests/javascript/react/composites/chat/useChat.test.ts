import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
    }
  },
}))

vi.mock("~/channels/client", () => ({
  getChannelsClient: vi.fn(() => null),
}))

vi.mock("~/shared/flash", () => ({
  showFlash: vi.fn(),
}))

let capturedOnNewMessage: ((msg: { user: { id: string } }) => void) | undefined
let capturedIsAtTail: (() => boolean) | undefined
vi.mock("~/react/shared/hooks/useChatMessageSubscription", () => ({
  useChatMessageSubscription: (
    _chatId: string | null,
    _workspaceId: string | null,
    _setMessages: unknown,
    options?: {
      onNewMessage?: (msg: { user: { id: string } }) => void
      isAtTail?: () => boolean
    }
  ) => {
    capturedOnNewMessage = options?.onNewMessage
    capturedIsAtTail = options?.isAtTail
  },
}))

vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: vi.fn(),
}))

// The initial message load is owned by useChat's useQuery now; useCatchUpMessages
// only handles the reconnect/re-arm catch-up merge, which these tests don't drive.
// A no-op mock keeps it from touching the (fake) channels client on mount.
vi.mock("~/react/shared/hooks/useCatchUpMessages", () => ({
  useCatchUpMessages: () => ({ catchUp: vi.fn() }),
}))

vi.mock("~/react/composites/confirmationDialog/confirm", () => ({
  confirm: vi.fn(() => Promise.resolve(true)),
}))

import { getChannelsClient } from "~/channels/client"
import { apiFetch } from "~/react/shared/apiFetch"
import { useChat } from "~/react/composites/chat/useChat"
import { act, renderHookWithClient, waitFor } from "../../shared/testUtils"

const mockApiFetch = vi.mocked(apiFetch)
const mockGetChannelsClient = vi.mocked(getChannelsClient)

// The cache value is the MessageListResponse-shaped window; this is the default
// response for the initial (no-cursor) tail load that useQuery fires on mount.
const EMPTY_PAGE = { messages: [], next_cursor: null, has_more: false }

beforeEach(() => {
  mockApiFetch.mockResolvedValue(EMPTY_PAGE as never)
})

afterEach(() => {
  vi.clearAllMocks()
  mockGetChannelsClient.mockReturnValue(null)
  capturedOnNewMessage = undefined
  capturedIsAtTail = undefined
})

const baseArgs = {
  chatId: "c1",
  workspaceId: "w1",
  currentUserId: "u-me",
  currentUserDisplayName: "Me",
  mailboxEntryId: "entry-1",
}

function makeMessage(id: string, userId: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    content: "hi",
    created_at: "2026-01-01T00:00:00Z",
    edited_at: null,
    reactions: {},
    user: { id: userId, display_name: userId, picture: null },
    link_preview: null,
    reply_to: null,
    ...overrides,
  }
}

function renderChat(args = baseArgs) {
  return renderHookWithClient(() => useChat(args))
}

describe("useChat", () => {
  test("chatId === null is a complete no-op (no network calls)", async () => {
    const { result } = renderHookWithClient(() =>
      useChat({
        chatId: null,
        workspaceId: null,
        currentUserId: null,
        currentUserDisplayName: null,
        markReadOnOpen: true,
        enableTyping: true,
      })
    )
    expect(mockApiFetch).not.toHaveBeenCalled()
    expect(result.current.messages).toEqual([])
    expect(result.current.loading).toBe(false)
  })

  test("initial tail load populates messages, loading, and hasMore from the query", async () => {
    mockApiFetch.mockResolvedValue({ messages: [makeMessage("m1", "u1")], next_cursor: "c", has_more: true } as never)
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.messages.map(m => m.id)).toEqual(["m1"])
    expect(result.current.hasMore).toBe(true)
  })

  test("sendMessage POSTs, appends, rotates claimId, clears replyTo", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))
    const initialClaimId = result.current.claimId

    act(() => result.current.setReplyTo({ id: "p1", user_name: "x", content_preview: "x", is_deleted: false }))
    mockApiFetch.mockResolvedValueOnce({ message: makeMessage("m1", "u-me") } as never)
    await act(async () => {
      await result.current.sendMessage("hello")
    })
    expect(mockApiFetch).toHaveBeenCalledWith("/api/chats/c1/messages", expect.objectContaining({ method: "POST" }))
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["m1"]))
    expect(result.current.claimId).not.toBe(initialClaimId)
    expect(result.current.replyTo).toBeNull()
  })

  test("editMessage PATCHes and replaces in place", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce({ message: makeMessage("m1", "u-me") } as never)
    await act(async () => {
      await result.current.sendMessage("hi")
    })
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["m1"]))

    mockApiFetch.mockResolvedValueOnce({ message: makeMessage("m1", "u-me", { content: "edited" }) } as never)
    await act(async () => {
      await result.current.editMessage("m1", "edited", null, [])
    })
    expect(mockApiFetch).toHaveBeenLastCalledWith(
      "/api/chats/c1/messages/m1",
      expect.objectContaining({ method: "PATCH" })
    )
    await waitFor(() => expect(result.current.messages[0].content).toBe("edited"))
  })

  test("deleteMessage confirms, DELETEs, removes from list", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce({ message: makeMessage("m1", "u-me") } as never)
    await act(async () => {
      await result.current.sendMessage("hi")
    })
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["m1"]))

    mockApiFetch.mockResolvedValueOnce({} as never)
    await act(async () => {
      await result.current.deleteMessage("m1")
    })
    expect(mockApiFetch).toHaveBeenLastCalledWith(
      "/api/chats/c1/messages/m1",
      expect.objectContaining({ method: "DELETE" })
    )
    await waitFor(() => expect(result.current.messages).toEqual([]))
  })

  test("toggleReaction optimistically uses currentUserDisplayName fallback empty string", async () => {
    const { result } = renderChat({ ...baseArgs, currentUserDisplayName: null })
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce({ message: makeMessage("m1", "u-me") } as never)
    await act(async () => {
      await result.current.sendMessage("hi")
    })
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["m1"]))

    let resolveReaction: (v: unknown) => void = () => {}
    mockApiFetch.mockReturnValueOnce(
      new Promise(resolve => {
        resolveReaction = resolve
      }) as never
    )
    act(() => {
      void result.current.toggleReaction("m1", "+1")
    })
    // Optimistic chip uses display_name "" since currentUserDisplayName is null
    await waitFor(() => expect(result.current.messages[0].reactions["+1"]).toEqual([{ id: "u-me", display_name: "" }]))

    resolveReaction({ message: makeMessage("m1", "u-me") })
    await waitFor(() => expect(result.current.messages[0].reactions).toEqual({}))
  })

  test("typing broadcast names the chat topic via broadcastTo(stream, params, payload)", async () => {
    const broadcastTo = vi.fn()
    mockGetChannelsClient.mockReturnValue({ broadcastTo } as never)

    const { result } = renderChat({ ...baseArgs, enableTyping: true })
    act(() => result.current.setDraftContent("typing…"))

    expect(broadcastTo).toHaveBeenCalledWith(
      "chat",
      { chat_id: "c1", workspace_id: "w1" },
      expect.objectContaining({ type: "typing", is_typing: true })
    )
  })

  test("setDraftContent clears sendError", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockRejectedValueOnce(new Error("nope"))
    await act(async () => {
      await result.current.sendMessage("hi")
    })
    expect(result.current.sendError).toBe(true)
    act(() => result.current.setDraftContent("typing"))
    expect(result.current.sendError).toBe(false)
  })

  test("sendMessage uses the content parameter, not React draftContent state", async () => {
    // Locks in the contract that send-on-Enter delivers the latest character
    // typed: with the debounced view plugin, draftContent state can lag the
    // actual editor doc, so the body must come from the parameter passed by
    // the caller (which serializes the live doc at send time).
    const { result } = renderChat({ ...baseArgs, initialDraft: "stale state" })
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce({ message: makeMessage("m1", "u-me") } as never)
    await act(async () => {
      await result.current.sendMessage("fresh content typed at send time")
    })

    const postCall = mockApiFetch.mock.calls.find(
      c => c[0] === "/api/chats/c1/messages" && (c[1] as { method?: string })?.method === "POST"
    )
    expect(postCall).toBeDefined()
    const body = JSON.parse(postCall![1]!.body as string) as { content: string }
    expect(body.content).toBe("fresh content typed at send time")
  })

  test("markReadOnOpen=true POSTs /mark_read once chatId+currentUserId are set, again on unmount", async () => {
    mockApiFetch.mockResolvedValue({} as never)
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true })

    const { unmount } = renderChat({ ...baseArgs, markReadOnOpen: true })
    await waitFor(() =>
      expect(
        mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length
      ).toBeGreaterThanOrEqual(1)
    )
    const before = mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length
    unmount()
    expect(mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length).toBe(
      before + 1
    )
  })

  test("markReadOnOpen does NOT fire while currentUserId is null", () => {
    mockApiFetch.mockResolvedValue({} as never)
    renderChat({ ...baseArgs, currentUserId: null, currentUserDisplayName: null, markReadOnOpen: true })
    expect(mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length).toBe(0)
  })

  test("jumpToMessage replaces messages with the window, sets older cursor, sets atTail from at_tail", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    const window = [makeMessage("a", "u1"), makeMessage("anchor", "u2"), makeMessage("b", "u1")]
    mockApiFetch.mockResolvedValueOnce({
      messages: window,
      next_cursor: "older-cursor",
      has_more: true,
      at_tail: false,
    } as never)

    let returned: unknown
    await act(async () => {
      returned = await result.current.jumpToMessage("anchor")
    })

    expect(mockApiFetch).toHaveBeenCalledWith("/api/chats/c1/messages/around/anchor")
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["a", "anchor", "b"]))
    expect(result.current.hasMore).toBe(true)
    // The window's older cursor feeds loadMore unchanged: paginating older now
    // requests that cursor.
    mockApiFetch.mockResolvedValueOnce({ messages: [], next_cursor: null, has_more: false } as never)
    await act(async () => {
      await result.current.loadMore()
    })
    expect(mockApiFetch).toHaveBeenCalledWith("/api/chats/c1/messages?cursor=older-cursor")
    // at_tail false → the live tail is not loaded → forward pagination is armed
    expect(result.current.atTail).toBe(false)
    expect(result.current.hasNewer).toBe(true)
    expect((returned as { messages: { id: string }[] }).messages.map(m => m.id)).toEqual(["a", "anchor", "b"])
  })

  test("jumpToMessage to a window reaching the newest message keeps atTail true", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce({
      messages: [makeMessage("anchor", "u1")],
      next_cursor: null,
      has_more: false,
      at_tail: true,
    } as never)
    await act(async () => {
      await result.current.jumpToMessage("anchor")
    })
    expect(result.current.atTail).toBe(true)
    expect(result.current.hasNewer).toBe(false)
  })

  test("jumpToMessage returns null on error (404) without throwing", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockRejectedValueOnce(new Error("not found"))
    let returned: unknown = "untouched"
    await act(async () => {
      returned = await result.current.jumpToMessage("missing")
    })
    expect(returned).toBeNull()
  })

  test("subscription gate reflects atTail; jumpToLatest reloads the tail and clears the gate", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    // Jump to a historical window (at_tail:false → not at the tail).
    mockApiFetch.mockResolvedValueOnce({
      messages: [makeMessage("old", "u1")],
      next_cursor: "older-cursor",
      has_more: true,
      at_tail: false,
    } as never)
    await act(async () => {
      await result.current.jumpToMessage("old")
    })
    expect(result.current.atTail).toBe(false)
    // The getter passed to the subscription reads the live ref, so the gate is false.
    expect(capturedIsAtTail?.()).toBe(false)

    // jumpToLatest refetches the no-cursor tail page, replaces the list, and
    // restores the gate.
    mockApiFetch.mockResolvedValueOnce({
      messages: [makeMessage("latest", "u2")],
      next_cursor: "tail-cursor",
      has_more: true,
    } as never)
    await act(async () => {
      await result.current.jumpToLatest()
    })
    expect(mockApiFetch).toHaveBeenLastCalledWith("/api/chats/c1/messages", expect.anything())
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["latest"]))
    expect(result.current.atTail).toBe(true)
    expect(capturedIsAtTail?.()).toBe(true)
  })

  test("loadNewer paginates forward from the window to the tail, then resumes at the tail", async () => {
    const { result } = renderChat()
    await waitFor(() => expect(result.current.loading).toBe(false))

    // Jump to a window that isn't caught up.
    mockApiFetch.mockResolvedValueOnce({
      messages: [makeMessage("anchor", "u1")],
      next_cursor: "older-cursor",
      has_more: true,
      at_tail: false,
    } as never)
    await act(async () => {
      await result.current.jumpToMessage("anchor")
    })
    expect(result.current.atTail).toBe(false)
    expect(result.current.hasNewer).toBe(true)

    // First newer page seeds from the window's last id (`after=`) and still has more.
    mockApiFetch.mockResolvedValueOnce({
      messages: [makeMessage("n1", "u2")],
      next_cursor: "newer-cursor",
      has_more: true,
    } as never)
    await act(async () => {
      await result.current.loadNewer()
    })
    expect(mockApiFetch).toHaveBeenLastCalledWith("/api/chats/c1/messages?direction=newer&after=anchor")
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["anchor", "n1"]))
    expect(result.current.atTail).toBe(false)
    expect(result.current.hasNewer).toBe(true)

    // Second newer page follows the returned cursor and reaches the tail.
    mockApiFetch.mockResolvedValueOnce({
      messages: [makeMessage("n2", "u2")],
      next_cursor: null,
      has_more: false,
    } as never)
    await act(async () => {
      await result.current.loadNewer()
    })
    expect(mockApiFetch).toHaveBeenLastCalledWith("/api/chats/c1/messages?direction=newer&cursor=newer-cursor")
    await waitFor(() => expect(result.current.messages.map(m => m.id)).toEqual(["anchor", "n1", "n2"]))
    // Reaching the tail flips atTail back true → live append/merge resume.
    expect(result.current.atTail).toBe(true)
    expect(result.current.hasNewer).toBe(false)
    expect(capturedIsAtTail?.()).toBe(true)
  })

  test("incoming-message mark-read: ignores self, marks other-user while visible, defers when hidden", async () => {
    mockApiFetch.mockResolvedValue({} as never)
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true })

    renderChat({ ...baseArgs, markReadOnOpen: true })
    await waitFor(() => expect(capturedOnNewMessage).toBeDefined())
    const initial = mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length

    // self-message: no extra call
    act(() => capturedOnNewMessage!({ user: { id: "u-me" } }))
    expect(mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length).toBe(initial)

    // other user, visible: fires
    act(() => capturedOnNewMessage!({ user: { id: "u-other" } }))
    expect(mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length).toBe(
      initial + 1
    )

    // hidden tab: defers
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true })
    act(() => capturedOnNewMessage!({ user: { id: "u-other" } }))
    expect(mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length).toBe(
      initial + 1
    )

    // visibilitychange: catches up
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true })
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length).toBe(
      initial + 2
    )
  })
})
