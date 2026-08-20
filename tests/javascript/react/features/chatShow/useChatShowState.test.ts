import { act, renderHook, waitFor } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { ChatMetadata } from "../../../../../app/javascript/react/features/chatShow/types"
import { setCurrentUser } from "../../shared/currentUserFixtures"
import { queryClient } from "../../../../../app/javascript/react/shared/queryClient"

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: Record<string, unknown> | null
    constructor(status: number, body: Record<string, unknown> | null = null) {
      const detail = body?.detail
      const message = (typeof detail === "string" ? detail : null) || `Request failed with status ${status}`
      super(message)
      this.status = status
      this.body = body
    }
  },
}))

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: vi.fn(),
}))

// useChat owns the messages useQuery now; catch-up only handles reconnect/re-arm.
vi.mock("../../../../../app/javascript/react/shared/hooks/useCatchUpMessages", () => ({
  useCatchUpMessages: vi.fn(() => ({ catchUp: vi.fn() })),
}))

let capturedOnNewMessage: ((msg: { user: { id: string } }) => void) | undefined
vi.mock("../../../../../app/javascript/react/shared/hooks/useChatMessageSubscription", () => ({
  useChatMessageSubscription: (
    _chatId: string | null,
    _workspaceId: string | null,
    _setMessages: unknown,
    options?: { onNewMessage?: (msg: { user: { id: string } }) => void }
  ) => {
    capturedOnNewMessage = options?.onNewMessage
  },
}))

vi.mock("~/channels/client", () => ({
  getChannelsClient: () => null,
}))

vi.mock("~/shared/flash", () => ({
  showFlash: vi.fn(),
}))

import { apiFetch, ApiError } from "../../../../../app/javascript/react/shared/apiFetch"
import { useChatShowState } from "../../../../../app/javascript/react/features/chatShow/useChatShowState"

const mockApiFetch = vi.mocked(apiFetch)

function makeMetadata(overrides: Partial<ChatMetadata> = {}): ChatMetadata {
  return {
    chat_id: "chat-1",
    workspace_id: "ws-1",
    chat_title: "Alice",
    type: "dm",
    is_group_chat: false,
    group_id: null,
    collaborators: [
      { id: "m1", user: { id: "u1", display_name: "Alice", picture: null } },
      { id: "m2", user: { id: "u2", display_name: "Me", picture: null } },
    ],
    supports_mentions: false,
    last_read_at: null,
    unread_message_count: 0,
    mailbox: {
      id: "entry-1",
      is_unread: true,
      is_archived: false,
      is_snoozed: false,
      snoozed_until: null,
    },
    ...overrides,
  }
}

const emptyMessages = { messages: [], next_cursor: null, has_more: false }

beforeEach(() => {
  setCurrentUser({ id: "u2", display_name: "Me" })
})

afterEach(() => {
  // metadata + messages live in the singleton Query cache now; clear so a chat's
  // state doesn't leak into the next test.
  queryClient.clear()
  vi.clearAllMocks()
})

describe("useChatShowState", () => {
  test("metadata reference stays stable across unrelated state updates (memo contract)", async () => {
    // memo(ChatHeader) in ChatShow.tsx only avoids re-renders if `metadata` keeps
    // the same identity across non-metadata state changes. This test pins that
    // contract: if a future change starts rebuilding metadata on every update
    // (e.g. merging live member events into a fresh object), the memo silently
    // stops helping — and this assertion fires.
    mockApiFetch.mockImplementation((url: string) => {
      if (url === "/api/chats/chat-1") return Promise.resolve(makeMetadata()) as any
      if (url === "/api/chats/chat-1/messages") return Promise.resolve(emptyMessages) as any
      if (url === "/api/mailbox_entries/entry-1/mark_read") return Promise.resolve({}) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    const { result } = renderHook(() => useChatShowState("chat-1"))

    await waitFor(() => expect(result.current.metadata).not.toBeNull())
    const initialMetadata = result.current.metadata

    act(() => result.current.setEditingMessageId("msg-1"))
    expect(result.current.metadata).toBe(initialMetadata)

    act(() => result.current.setDraftContent("hello"))
    expect(result.current.metadata).toBe(initialMetadata)

    act(() =>
      result.current.setReplyTo({ id: "parent", user_name: "Alice", content_preview: "hey", is_deleted: false })
    )
    expect(result.current.metadata).toBe(initialMetadata)

    act(() => result.current.cancelEdit())
    expect(result.current.metadata).toBe(initialMetadata)
  })

  test("renameChat updates chat_title on success and surfaces conflict error on 422", async () => {
    // Route by URL + method: the metadata GET now passes { signal } (so the old
    // `!options` guard no longer distinguishes it), and background message/mark_read
    // fetches would otherwise consume a mockResolvedValueOnce meant for the PATCH.
    mockApiFetch.mockImplementation((url: string, options?: any) => {
      if (url === "/api/chats/chat-1" && options?.method === "PATCH") {
        const title = JSON.parse(options.body).title
        if (title === "Renamed") {
          return Promise.resolve({ id: "chat-1", name: "Renamed", chat_title: "Renamed" }) as any
        }
        return Promise.reject(new (ApiError as any)(422, { detail: "A group or chat with that name already exists." }))
      }
      if (url === "/api/chats/chat-1") {
        return Promise.resolve(makeMetadata({ type: "multi", chat_title: "Original Title" })) as any
      }
      if (url === "/api/chats/chat-1/messages") return Promise.resolve(emptyMessages) as any
      if (url === "/api/mailbox_entries/entry-1/mark_read") return Promise.resolve({}) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    const { result } = renderHook(() => useChatShowState("chat-1"))
    await waitFor(() => expect(result.current.metadata).not.toBeNull())

    let result1: { error?: string } | undefined
    await act(async () => {
      result1 = await result.current.renameChat("Renamed")
    })
    expect(result1).toEqual({})
    await waitFor(() => expect(result.current.metadata?.chat_title).toBe("Renamed"))

    let result2: { error?: string } | undefined
    await act(async () => {
      result2 = await result.current.renameChat("Taken")
    })
    expect(result2?.error).toBe("A group or chat with that name already exists.")
    // chat_title remains the previous accepted value
    expect(result.current.metadata?.chat_title).toBe("Renamed")
  })

  test("surfaces metadataError when the metadata load fails", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url === "/api/chats/chat-1") return Promise.reject(new (ApiError as any)(404)) as any
      if (url === "/api/chats/chat-1/messages") return Promise.resolve(emptyMessages) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    const { result } = renderHook(() => useChatShowState("chat-1"))

    await waitFor(() => expect(result.current.metadataError).toBe(true))
    expect(result.current.metadata).toBeNull()
  })

  test("marks read on incoming message from another user, on unmount, and on tab refocus", async () => {
    mockApiFetch.mockImplementation((url: string) => {
      if (url === "/api/chats/chat-1") return Promise.resolve(makeMetadata()) as any
      if (url === "/api/chats/chat-1/messages") return Promise.resolve(emptyMessages) as any
      if (url === "/api/mailbox_entries/entry-1/mark_read") return Promise.resolve({}) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true })

    const { result, unmount } = renderHook(() => useChatShowState("chat-1"))
    await waitFor(() => expect(result.current.metadata).not.toBeNull())

    const markReadCalls = () =>
      mockApiFetch.mock.calls.filter(c => c[0] === "/api/mailbox_entries/entry-1/mark_read").length
    await waitFor(() => expect(markReadCalls()).toBeGreaterThanOrEqual(1))
    const initialMarkReads = markReadCalls()

    // Incoming message from another user while visible -> mark_read
    act(() => capturedOnNewMessage?.({ user: { id: "u1" } }))
    expect(markReadCalls()).toBe(initialMarkReads + 1)

    // Self-message -> no mark_read
    act(() => capturedOnNewMessage?.({ user: { id: "u2" } }))
    expect(markReadCalls()).toBe(initialMarkReads + 1)

    // Hidden tab: defer mark_read until visibilitychange
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true })
    act(() => capturedOnNewMessage?.({ user: { id: "u1" } }))
    expect(markReadCalls()).toBe(initialMarkReads + 1)

    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true })
    act(() => document.dispatchEvent(new Event("visibilitychange")))
    expect(markReadCalls()).toBe(initialMarkReads + 2)

    // Unmount -> one final mark_read
    unmount()
    expect(markReadCalls()).toBe(initialMarkReads + 3)
  })
})
