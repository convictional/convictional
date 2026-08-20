import { act, cleanup, renderHook, waitFor } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
    }
  },
}))

vi.mock("~/shared/flash", () => ({
  showFlash: vi.fn(),
}))

vi.mock("../../../../../app/javascript/react/composites/chat/useChat", () => ({
  useChat: vi.fn(() => ({
    messages: [],
    setMessages: () => {},
    loading: false,
    loadingMore: false,
    hasMore: false,
    nextCursorRef: { current: null },
    sending: false,
    sendError: false,
    claimId: "claim",
    replyTo: null,
    setReplyTo: () => {},
    editingMessageId: null,
    setEditingMessageId: () => {},
    cancelEdit: () => {},
    draftContent: "",
    setDraftContent: () => {},
    composePreview: null,
    dismissComposePreview: () => {},
    lastReadAt: null,
    setLastReadAt: () => {},
    unreadMessageCount: 0,
    setUnreadMessageCount: () => {},
    typingUsers: [],
    loadMore: async () => {},
    sendMessage: async () => {},
    editMessage: async () => {},
    deleteMessage: async () => {},
    toggleReaction: async () => {},
  })),
}))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { queryClient } from "../../../../../app/javascript/react/shared/queryClient"
import { useChatPanelState } from "../../../../../app/javascript/react/features/chatPanel/useChatPanelState"
import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"

const mockApiFetch = vi.mocked(apiFetch)

beforeEach(() => {
  sessionStorage.clear()
  // Default location to a non-chat path so auto-close doesn't fire
  Object.defineProperty(window, "location", {
    value: { pathname: "/" },
    writable: true,
  })
  setCurrentUser({ id: "me", display_name: "Me" })
})

afterEach(() => {
  cleanup()
  resetCurrentUser()
  sessionStorage.clear()
  // mockReset (not clearAllMocks) so any leftover mockResolvedValueOnce queue is
  // drained — otherwise a prior test's queued metadata response bleeds into the
  // next reconcile fetch. Clear the singleton Query cache for the same reason
  // (ensureQueryData with staleTime:Infinity would reuse a prior test's entry).
  mockApiFetch.mockReset()
  vi.clearAllMocks()
  queryClient.clear()
})

const recipient = { id: "u1", displayName: "Alice", picture: null }

describe("useChatPanelState", () => {
  test("openChatPanelForUser POSTs /api/chats and sets chatId/workspaceId/uploadUrl", async () => {
    mockApiFetch
      .mockResolvedValueOnce({
        chat_id: "c1",
        workspace_id: "t1",
        messages: [],
        has_more: false,
        next_cursor: null,
      })
      // Reconciliation GET that fires after the POST resolves.
      .mockResolvedValueOnce({
        workspace_id: "t1",
        chat_title: "Alice",
        type: "dm",
        collaborators: [{ id: "col-1", user: { id: "u1", display_name: "Alice", picture: null } }],
      })

    const { result } = renderHook(() => useChatPanelState())
    await act(async () => {
      await result.current.openChatPanelForUser(recipient)
    })

    expect(mockApiFetch).toHaveBeenCalledWith("/api/chats", expect.objectContaining({ method: "POST" }))
    expect(result.current.panelState).toMatchObject({
      chatId: "c1",
      workspaceId: "t1",
      uploadUrl: "/api/workspaces/t1/attachments",
    })
    expect(result.current.currentUserId).toBe("me")
    expect(result.current.panelState?.display.title).toBe("Alice")
    expect(result.current.panelState?.display.type).toBe("dm")
    expect(result.current.panelState?.display.collaborators[0].user.id).toBe("u1")
  })

  test("re-opening for the same recipient just restores (no extra POST)", async () => {
    mockApiFetch
      .mockResolvedValueOnce({
        chat_id: "c1",
        workspace_id: "t1",
        messages: [],
        has_more: false,
        next_cursor: null,
      })
      .mockResolvedValueOnce({
        workspace_id: "t1",
        chat_title: "Alice",
        type: "dm",
        collaborators: [{ id: "col-1", user: { id: "u1", display_name: "Alice", picture: null } }],
      })
    const { result } = renderHook(() => useChatPanelState())
    await act(async () => {
      await result.current.openChatPanelForUser(recipient)
    })
    // Wait for reconciliation to settle so callsBefore captures both fetches.
    await waitFor(() => expect(result.current.panelState?.incomplete).toBe(false))
    act(() => result.current.minimize())
    const callsBefore = mockApiFetch.mock.calls.length
    await act(async () => {
      await result.current.openChatPanelForUser(recipient)
    })
    expect(mockApiFetch.mock.calls.length).toBe(callsBefore)
    expect(result.current.panelState?.minimized).toBe(false)
  })

  test("openChatPanel skips POST /api/chats and fetches metadata", async () => {
    mockApiFetch.mockResolvedValueOnce({
      workspace_id: "t-x",
      chat_title: "Eng team",
      type: "group",
      collaborators: [
        { id: "col-1", user: { id: "me", display_name: "Me", picture: null } },
        { id: "col-2", user: { id: "u2", display_name: "Bob", picture: null } },
      ],
    })

    const { result } = renderHook(() => useChatPanelState())
    await act(async () => {
      await result.current.openChatPanel("c-x", { title: "Eng" })
    })

    expect(mockApiFetch).not.toHaveBeenCalledWith("/api/chats", expect.objectContaining({ method: "POST" }))
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/chats/c-x", expect.anything()))
    await waitFor(() => expect(result.current.panelState?.display.title).toBe("Eng team"))
    expect(result.current.panelState?.chatId).toBe("c-x")
    expect(result.current.panelState?.display.type).toBe("group")
    expect(result.current.currentUserId).toBe("me")
  })

  test("openChatPanel keeps panel open with loadFailed flag when metadata fetch fails", async () => {
    mockApiFetch.mockRejectedValueOnce(new Error("503"))
    const { result } = renderHook(() => useChatPanelState())
    await act(async () => {
      await result.current.openChatPanel("c-broken", { title: "Maybe Eng" })
    })
    await waitFor(() => expect(result.current.panelState?.loadFailed).toBe(true))
    expect(result.current.panelState?.chatId).toBe("c-broken")
    expect(result.current.panelState?.draftContent).toBe("")
  })

  test("retryLoad clears loadFailed and re-fires metadata fetch", async () => {
    mockApiFetch.mockRejectedValueOnce(new Error("503"))
    const { result } = renderHook(() => useChatPanelState())
    await act(async () => {
      await result.current.openChatPanel("c-broken", { title: "Maybe Eng" })
    })
    await waitFor(() => expect(result.current.panelState?.loadFailed).toBe(true))

    mockApiFetch.mockResolvedValueOnce({
      workspace_id: "t-fixed",
      chat_title: "Recovered",
      type: "dm",
      current_user: { id: "me", display_name: "Me", picture: null },
      collaborators: [{ id: "col-1", user: { id: "u1", display_name: "Alice", picture: null } }],
    })
    act(() => result.current.retryLoad())
    await waitFor(() => expect(result.current.panelState?.display.title).toBe("Recovered"))
    expect(result.current.panelState?.loadFailed).toBe(false)
    expect(result.current.panelState?.incomplete).toBe(false)
  })

  test("open-chat-panel event with kind:'chat' routes through chat path", async () => {
    mockApiFetch.mockResolvedValueOnce({
      workspace_id: "t-y",
      chat_title: "Server team",
      type: "multi",
      current_user: { id: "me", display_name: "Me", picture: null },
      collaborators: [{ id: "col-1", user: { id: "me", display_name: "Me", picture: null } }],
    })
    const { result } = renderHook(() => useChatPanelState())

    await act(async () => {
      window.dispatchEvent(
        new CustomEvent("open-chat-panel", {
          detail: { kind: "chat", chatId: "c-y", title: "Server" },
        })
      )
    })
    expect(result.current.panelState?.chatId).toBe("c-y")
    // The hint is shown until metadata lands; afterwards the real title takes over.
    await waitFor(() => expect(result.current.panelState?.display.title).toBe("Server team"))
  })

  test("open-chat-panel event with kind:'recipient' routes through recipient path", async () => {
    mockApiFetch.mockResolvedValue({
      chat_id: "c1",
      workspace_id: "t1",
      current_user: { id: "me", display_name: "Me", picture: null },
      messages: [],
      has_more: false,
      next_cursor: null,
    })
    renderHook(() => useChatPanelState())

    // Wrong event name: ignored
    act(() => {
      window.dispatchEvent(
        new CustomEvent("open-dm-panel", {
          detail: { kind: "recipient", recipientId: "u1", recipientName: "Alice", recipientPicture: null },
        })
      )
    })
    expect(mockApiFetch).not.toHaveBeenCalled()

    await act(async () => {
      window.dispatchEvent(
        new CustomEvent("open-chat-panel", {
          detail: { kind: "recipient", recipientId: "u1", recipientName: "Alice", recipientPicture: null },
        })
      )
    })
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledWith("/api/chats", expect.anything()))
  })

  test("loadState migrates legacy dm-panel-state to chat-panel-state and removes the legacy key", () => {
    const legacy = {
      chatId: "c-legacy",
      workspaceId: "t-legacy",
      uploadUrl: null,
      currentUserId: null,
      recipient: { id: "u1", displayName: "Alice", picture: null },
      minimized: false,
      draftContent: "leftover",
    }
    sessionStorage.setItem("dm-panel-state", JSON.stringify(legacy))

    const { result } = renderHook(() => useChatPanelState())
    expect(result.current.panelState?.chatId).toBe("c-legacy")
    expect(sessionStorage.getItem("dm-panel-state")).toBeNull()
    expect(sessionStorage.getItem("chat-panel-state")).not.toBeNull()
    expect(result.current.panelState?.display.type).toBe("dm")
    expect(result.current.panelState?.display.collaborators[0].user.id).toBe("u1")
  })

  test("loadState in-shape migration: legacy `recipient` becomes `display`", () => {
    sessionStorage.setItem(
      "chat-panel-state",
      JSON.stringify({
        chatId: "c-legacy",
        workspaceId: "t",
        uploadUrl: null,
        currentUserId: "me",
        recipient: { id: "u9", displayName: "Carol", picture: "/p.jpg" },
        minimized: false,
        draftContent: "",
      })
    )
    // Stub the metadata refetch so currentUserId is treated as already set;
    // we want to assert on the migrated display before any fetch lands.
    mockApiFetch.mockResolvedValue({
      workspace_id: "t",
      chat_title: "Carol",
      type: "dm",
      current_user: { id: "me", display_name: "Me", picture: null },
      collaborators: [{ id: "col-1", user: { id: "u9", display_name: "Carol", picture: "/p.jpg" } }],
    })
    const { result } = renderHook(() => useChatPanelState())
    expect(result.current.panelState?.display.title).toBe("Carol")
    expect(result.current.panelState?.display.type).toBe("dm")
    expect(result.current.panelState?.display.collaborators[0].user.id).toBe("u9")
  })

  test("auto-closes when navigating to /chats/{chatId}", () => {
    sessionStorage.setItem(
      "chat-panel-state",
      JSON.stringify({
        chatId: "c-here",
        workspaceId: "t",
        uploadUrl: null,
        currentUserId: "me",
        currentUserDisplayName: "Me",
        display: {
          title: "Alice",
          type: "dm",
          collaborators: [{ id: "col-1", user: { id: "u1", display_name: "Alice", picture: null } }],
        },
        minimized: false,
        draftContent: "",
      })
    )
    Object.defineProperty(window, "location", {
      value: { pathname: "/chats/c-here" },
      writable: true,
    })
    const { result } = renderHook(() => useChatPanelState())
    expect(result.current.panelState).toBeNull()
  })

  test("minimize/restore/close mutate panelState", async () => {
    mockApiFetch.mockResolvedValueOnce({
      chat_id: "c1",
      workspace_id: "t1",
      current_user: { id: "me", display_name: "Me", picture: null },
      messages: [],
      has_more: false,
      next_cursor: null,
    })
    const { result } = renderHook(() => useChatPanelState())
    await act(async () => {
      await result.current.openChatPanelForUser(recipient)
    })
    act(() => result.current.minimize())
    expect(result.current.panelState?.minimized).toBe(true)
    act(() => result.current.restore())
    expect(result.current.panelState?.minimized).toBe(false)
    act(() => result.current.close())
    expect(result.current.panelState).toBeNull()
  })
})
