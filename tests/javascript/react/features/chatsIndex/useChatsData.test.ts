import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { act, renderHookWithClient, waitFor } from "../../shared/testUtils"

import type {
  ChatListItem,
  ChatListResponse,
  Contact,
  ContactListResponse,
} from "../../../../../app/javascript/react/features/chatsIndex/types"

// Chat navigation is typed TanStack nav now. Mock useNavigate so we can assert
// the destination, and useLocation so the hook resolves the current index URL
// (stamped as the new chat's return_to) without a RouterProvider.
const navigateSpy = vi.fn()
vi.mock("@tanstack/react-router", async importActual => ({
  ...(await importActual<typeof import("@tanstack/react-router")>()),
  useNavigate: () => navigateSpy,
  useLocation: (opts?: { select?: (loc: { href: string }) => unknown }) => {
    const location = { href: "/chats", pathname: "/chats", search: "" }
    return opts?.select ? opts.select(location) : location
  },
}))

vi.mock("../../../../../app/javascript/react/shared/apiFetch", () => ({
  apiFetch: vi.fn(),
  ApiError: class extends Error {
    status: number
    body: null
    constructor(status: number) {
      super(`Request failed with status ${status}`)
      this.status = status
      this.body = null
    }
  },
}))

let channelStream: string | null = null
let channelParams: Record<string, unknown> | null = null
vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (target: { stream: string; params: Record<string, unknown> } | null) => {
    channelStream = target?.stream ?? null
    channelParams = target?.params ?? null
  },
}))

const reconnectListeners = new Set<() => void>()
const fakeChannelsClient = {
  on: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.add(cb)
  },
  off: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.delete(cb)
  },
}

vi.mock("../../../../../app/javascript/channels/client", () => ({
  getChannelsClient: () => fakeChannelsClient,
}))

import { apiFetch, ApiError } from "../../../../../app/javascript/react/shared/apiFetch"
import { useChatsData } from "../../../../../app/javascript/react/features/chatsIndex/hooks/useChatsData"

const mockApiFetch = vi.mocked(apiFetch)

function makeChat(overrides: Partial<ChatListItem> = {}): ChatListItem {
  return {
    id: "chat-1",
    type: "dm",
    name: "Alice",
    collaborator_count: 2,
    collaborators: null,
    latest_message: {
      id: "msg-1",
      content: "Hello!",
      created_at: "2026-04-08T12:00:00Z",
      user: { id: "u1", display_name: "Alice", picture: null },
      link_preview: null,
      reactions: {},
      edited_at: null,
      reply_to: null,
    },
    user: { id: "u1", display_name: "Alice", picture: null },
    picture: null,
    is_unread: false,
    is_archived: false,
    snoozed_until: null,
    ...overrides,
  }
}

function makeContact(overrides: Partial<Contact> = {}): Contact {
  return {
    id: "contact-1",
    type: "dm",
    name: "Bob",
    collaborator_count: 2,
    picture: null,
    ...overrides,
  }
}

function mockInitialFetch(
  chatsResponse: Partial<ChatListResponse> = {},
  contactsResponse: Partial<ContactListResponse> = {}
) {
  const chats: ChatListResponse = { chats: [], next_cursor: null, has_more: false, ...chatsResponse }
  const contacts: ContactListResponse = { contacts: [], next_cursor: null, has_more: false, ...contactsResponse }
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/chats/lookup"))
      return Promise.resolve({ matches: [], match_group: null, next_cursor: null, has_more: false }) as any
    if (typeof url === "string" && url.startsWith("/api/chats/contacts")) return Promise.resolve(contacts) as any
    if (typeof url === "string" && url.startsWith("/api/chats")) return Promise.resolve(chats) as any
    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })
}

function mockPaginatedFetch(firstPage: ChatListResponse, pagesByCursor: Record<string, ChatListResponse>) {
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/chats/lookup"))
      return Promise.resolve({ matches: [], match_group: null, next_cursor: null, has_more: false }) as any
    if (typeof url === "string" && url.startsWith("/api/chats/contacts"))
      return Promise.resolve({ contacts: [], next_cursor: null, has_more: false }) as any
    for (const [cursor, page] of Object.entries(pagesByCursor)) {
      if (url === `/api/chats?cursor=${cursor}`) return Promise.resolve(page) as any
    }
    if (typeof url === "string" && url.startsWith("/api/chats")) return Promise.resolve(firstPage) as any
    return Promise.reject(new Error(`Unexpected URL: ${url}`))
  })
}

beforeEach(() => {
  navigateSpy.mockReset()
})

afterEach(() => {
  vi.clearAllMocks()
  reconnectListeners.clear()
})

describe("useChatsData", () => {
  test("initial fetch loads chats and contacts in parallel", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    const bob = makeContact({ id: "contact-1", name: "Bob" })
    mockInitialFetch({ chats: [alice], has_more: true, next_cursor: "cursor1" }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.chats).toHaveLength(1)
    expect(result.current.chats[0].name).toBe("Alice")
    expect(result.current.contacts).toHaveLength(1)
    expect(result.current.contacts[0].name).toBe("Bob")
    expect(result.current.hasMore).toBe(true)
    expect(result.current.error).toBe(false)
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
    expect(channelStream).toBe("chats_index")
    expect(channelParams).toEqual({ organization_id: "org-1" })
  })

  test("fetch error sets error state", async () => {
    mockApiFetch.mockRejectedValue(new Error("Network error"))

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.error).toBe(true)
    expect(result.current.chats).toHaveLength(0)
  })

  test("websocket reconnect refetches chats", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice", is_unread: false })
    mockInitialFetch({ chats: [alice] }, { contacts: [] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    expect(result.current.chats[0].is_unread).toBe(false)
    const initialCalls = mockApiFetch.mock.calls.length

    // Server marks chat unread; broadcast was missed while disconnected.
    const aliceUnread = makeChat({ id: "chat-1", name: "Alice", is_unread: true })
    mockInitialFetch({ chats: [aliceUnread] }, { contacts: [] })

    await act(async () => {
      reconnectListeners.forEach(cb => cb())
    })

    await waitFor(() => {
      expect(result.current.chats[0].is_unread).toBe(true)
    })
    expect(mockApiFetch.mock.calls.length).toBeGreaterThan(initialCalls)
  })

  test("loadMore appends chats and does not re-fetch contacts", async () => {
    const chat1 = makeChat({ id: "chat-1", name: "Alice" })
    const chat2 = makeChat({ id: "chat-2", name: "Charlie" })
    const bob = makeContact({ id: "contact-1", name: "Bob" })

    mockInitialFetch({ chats: [chat1], has_more: true, next_cursor: "cursor1" }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // Set up page 2 response
    const page2: ChatListResponse = { chats: [chat2], next_cursor: null, has_more: false }
    mockApiFetch.mockResolvedValue(page2 as any)

    await act(async () => {
      result.current.loadMore()
    })

    await waitFor(() => {
      expect(result.current.loadingMore).toBe(false)
    })

    expect(result.current.chats).toHaveLength(2)
    expect(result.current.chats[0].name).toBe("Alice")
    expect(result.current.chats[1].name).toBe("Charlie")
    expect(result.current.hasMore).toBe(false)
    // The loadMore call should only fetch chats with cursor, not contacts
    const loadMoreCall = mockApiFetch.mock.calls[2]
    expect(loadMoreCall[0]).toBe("/api/chats?cursor=cursor1")
    // Total calls: 2 initial + 1 loadMore = 3
    expect(mockApiFetch).toHaveBeenCalledTimes(3)
  })

  test("client-side search and group filtering", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice", type: "dm" })
    const engineering = makeChat({ id: "chat-2", name: "Engineering", type: "group" })
    const bob = makeContact({ id: "contact-1", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [alice, engineering] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
    })

    // All items visible by default (chats + divider + Note to self + contacts)
    expect(result.current.visibleItems).toHaveLength(5)
    expect(result.current.visibleItems[2].kind).toBe("contact-divider")

    // Search filters to matching items only
    act(() => result.current.setSearchQuery("ali"))
    expect(result.current.visibleItems).toHaveLength(1)
    expect(result.current.visibleItems[0].kind).toBe("chat")
    if (result.current.visibleItems[0].kind === "chat") {
      expect(result.current.visibleItems[0].chat.name).toBe("Alice")
    }

    // Clear search
    act(() => result.current.setSearchQuery(""))
    expect(result.current.visibleItems).toHaveLength(5)

    // Group filter hides DMs and Note to self
    act(() => result.current.setGroupFilter("groups"))
    expect(result.current.visibleItems).toHaveLength(1)
    if (result.current.visibleItems[0].kind === "chat") {
      expect(result.current.visibleItems[0].chat.name).toBe("Engineering")
    }

    // Back to all
    act(() => result.current.setGroupFilter("all"))
    expect(result.current.visibleItems).toHaveLength(5)
  })

  test("contact divider hidden during search", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    const bob = makeContact({ id: "contact-1", name: "Bob" })

    mockInitialFetch({ chats: [alice] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Divider present when no search
    expect(result.current.visibleItems.some(i => i.kind === "contact-divider")).toBe(true)

    // Search for "bob" — contact matches but no divider
    act(() => result.current.setSearchQuery("bob"))
    expect(result.current.visibleItems).toHaveLength(1)
    expect(result.current.visibleItems[0].kind).toBe("contact")
    expect(result.current.visibleItems.some(i => i.kind === "contact-divider")).toBe(false)
  })

  test("keyboard navigation and selection", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    const engineering = makeChat({ id: "chat-2", name: "Engineering", type: "group" })
    const bob = makeContact({ id: "contact-1", name: "Bob" })

    mockInitialFetch({ chats: [alice, engineering] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // selectableItems: [Alice (chat), Engineering (chat), Note to self (contact), Bob (contact)]
    expect(result.current.selectableItems).toHaveLength(4)
    expect(result.current.selectedIndex).toBe(0)

    // ArrowDown increments to max
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    expect(result.current.selectedIndex).toBe(3)

    // ArrowDown at max clamps
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    expect(result.current.selectedIndex).toBe(3)

    // ArrowUp back to 0
    act(() => result.current.handleKeyDown({ key: "ArrowUp", preventDefault: vi.fn() } as any))
    act(() => result.current.handleKeyDown({ key: "ArrowUp", preventDefault: vi.fn() } as any))
    act(() => result.current.handleKeyDown({ key: "ArrowUp", preventDefault: vi.fn() } as any))
    expect(result.current.selectedIndex).toBe(0)

    // ArrowUp at 0 clamps
    act(() => result.current.handleKeyDown({ key: "ArrowUp", preventDefault: vi.fn() } as any))
    expect(result.current.selectedIndex).toBe(0)

    // Enter on DM chat in browse mode navigates to the chat
    act(() => result.current.handleKeyDown({ key: "Enter", preventDefault: vi.fn() } as any))
    expect(result.current.selectedRecipients).toHaveLength(0)
    expect(navigateSpy).toHaveBeenCalledWith({
      to: "/chats/$chatId",
      params: { chatId: "chat-1" },
      search: { return_to: "/chats" },
    })
  })

  test("Enter on DM contact in browse mode navigates to create chat", async () => {
    const bob = makeContact({ id: "user-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // selectableItems: [Note to self (contact), Bob (contact)]
    expect(result.current.selectableItems).toHaveLength(2)
    expect(result.current.composing).toBe(false)

    // Move past the pinned Note to self entry to land on Bob
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))

    // Mock the create-chat API response
    mockApiFetch.mockResolvedValueOnce({ chat_id: "new-chat-bob", topic_id: "t", type: "dm", name: "Bob" } as any)

    // Enter on DM contact in browse mode navigates (creates/opens the 1:1 chat)
    await act(async () => {
      result.current.handleKeyDown({ key: "Enter", preventDefault: vi.fn() } as any)
    })

    expect(result.current.selectedRecipients).toHaveLength(0)
    expect(result.current.composing).toBe(false)
    expect(navigateSpy).toHaveBeenCalledWith({
      to: "/chats/$chatId",
      params: { chatId: "new-chat-bob" },
      search: { return_to: "/chats" },
    })
  })

  test("Enter on DM contact in compose mode adds recipient chip", async () => {
    const alice = makeContact({ id: "u-alice", name: "Alice", type: "dm" })
    const bob = makeContact({ id: "u-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [] }, { contacts: [alice, bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Enter compose mode by toggling Alice as a recipient
    act(() => {
      result.current.toggleRecipient({ id: "u-alice", name: "Alice", picture: null })
    })
    expect(result.current.composing).toBe(true)

    // Wait for lookup to resolve so compose-looking-up item clears
    await waitFor(() => expect(result.current.lookingUp).toBe(false))

    // In compose mode, selectableItems: [compose-create, Bob] (Alice is already selected)
    // ArrowDown to Bob (index 1), then Enter adds him as a chip
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    act(() => {
      result.current.handleKeyDown({ key: "Enter", preventDefault: vi.fn() } as any)
    })

    expect(result.current.selectedRecipients).toHaveLength(2)
    expect(result.current.selectedRecipients[1].id).toBe("u-bob")
    expect(navigateSpy).not.toHaveBeenCalled()
  })

  test("createChat with selected recipients creates chat", async () => {
    const bob = makeContact({ id: "user-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Add Bob as chip via toggleRecipient (enters compose mode)
    act(() => {
      result.current.toggleRecipient({ id: "user-bob", name: "Bob", picture: null })
    })

    expect(result.current.composing).toBe(true)

    // Wait for lookup to resolve
    await waitFor(() => expect(result.current.lookingUp).toBe(false))

    // Mock the create chat response
    mockApiFetch.mockResolvedValueOnce({ chat_id: "new-chat-123", topic_id: "t", type: "dm", name: "Bob" } as any)

    // Call createChat directly (triggered by the header create button)
    await act(async () => {
      result.current.createChat()
    })

    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith("/api/chats", {
        method: "POST",
        body: JSON.stringify({ recipient_ids: ["user-bob"] }),
      })
    })

    expect(navigateSpy).toHaveBeenCalledWith({
      to: "/chats/$chatId",
      params: { chatId: "new-chat-123" },
      search: { return_to: "/chats" },
    })
  })

  test("Escape clears search and resets selectedIndex", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    const engineering = makeChat({ id: "chat-2", name: "Engineering" })

    mockInitialFetch({ chats: [alice, engineering] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Set search and navigate down
    act(() => result.current.setSearchQuery("eng"))
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))

    // Escape clears search and resets index
    act(() => result.current.handleKeyDown({ key: "Escape", preventDefault: vi.fn() } as any))
    expect(result.current.searchQuery).toBe("")
    expect(result.current.selectedIndex).toBe(0)
  })

  test("Backspace with empty search removes last recipient chip", async () => {
    const alice = makeContact({ id: "u-alice", name: "Alice", type: "dm" })
    const bob = makeContact({ id: "u-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [] }, { contacts: [alice, bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Add two chips via toggleRecipient
    act(() => {
      result.current.toggleRecipient({ id: "u-alice", name: "Alice", picture: null })
    })
    act(() => {
      result.current.toggleRecipient({ id: "u-bob", name: "Bob", picture: null })
    })

    expect(result.current.selectedRecipients).toHaveLength(2)
    expect(result.current.composing).toBe(true)

    // Backspace with empty search removes Bob (last chip)
    act(() => {
      result.current.handleKeyDown({ key: "Backspace", preventDefault: vi.fn() } as any)
    })

    expect(result.current.selectedRecipients).toHaveLength(1)
    expect(result.current.selectedRecipients[0].id).toBe("u-alice")

    // Backspace again removes Alice
    act(() => {
      result.current.handleKeyDown({ key: "Backspace", preventDefault: vi.fn() } as any)
    })

    expect(result.current.selectedRecipients).toHaveLength(0)
    expect(result.current.composing).toBe(false)
  })

  test("selectChat sets navigating state and prevents double navigation", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    mockInitialFetch({ chats: [alice] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.selectChat("chat-1"))
    expect(result.current.navigating).toBe(true)
    expect(result.current.navigatingId).toBe("chat-1")
    expect(navigateSpy).toHaveBeenCalledWith({
      to: "/chats/$chatId",
      params: { chatId: "chat-1" },
      search: { return_to: "/chats" },
    })

    // Second call while navigating is a no-op
    navigateSpy.mockClear()
    act(() => result.current.selectChat("chat-2"))
    expect(navigateSpy).not.toHaveBeenCalled()
    expect(result.current.navigatingId).toBe("chat-1")
  })

  test("selectContact for group sends group_id", async () => {
    mockInitialFetch()

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce({ chat_id: "group-chat-1", topic_id: "t", type: "group", name: "Eng" } as any)

    await act(async () => {
      await result.current.selectContact("group-1", "group")
    })

    expect(mockApiFetch).toHaveBeenCalledWith("/api/chats", {
      method: "POST",
      body: JSON.stringify({ group_id: "group-1" }),
    })
    expect(navigateSpy).toHaveBeenCalledWith({
      to: "/chats/$chatId",
      params: { chatId: "group-chat-1" },
      search: { return_to: "/chats" },
    })
  })

  test("selectContact sets createError on API failure", async () => {
    mockInitialFetch()

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockRejectedValueOnce(new (ApiError as any)(422))

    await act(async () => {
      await result.current.selectContact("user-1", "dm")
    })

    expect(result.current.createError).toBeTruthy()
    expect(result.current.navigating).toBe(false)
    expect(result.current.navigatingId).toBeNull()
  })

  test("selecting 2+ recipients triggers lookup and populates existingMatches", async () => {
    const alice = makeChat({
      id: "chat-1",
      name: "Alice",
      user: { id: "u-alice", display_name: "Alice", picture: null },
    })
    const bob = makeContact({ id: "u-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [alice] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Add Alice as recipient
    act(() => {
      result.current.toggleRecipient({ id: "u-alice", name: "Alice", picture: null })
    })

    // Add Bob as recipient — now 2 selected, triggers lookup
    act(() => {
      result.current.toggleRecipient({ id: "u-bob", name: "Bob", picture: null })
    })

    expect(result.current.lookingUp).toBe(true)
    expect(result.current.selectedRecipients).toHaveLength(2)

    // Mock lookup returns a match (collaborator_count=3 to indicate exact match of 2 recipients + self)
    const matchChat = makeChat({ id: "existing-multi", name: "Alice, Bob", type: "multi", collaborator_count: 3 })
    mockApiFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.startsWith("/api/chats/lookup"))
        return Promise.resolve({ matches: [matchChat], match_group: null, next_cursor: null, has_more: false }) as any
      if (typeof url === "string" && url.startsWith("/api/chats/contacts"))
        return Promise.resolve({ contacts: [], next_cursor: null, has_more: false }) as any
      if (typeof url === "string" && url.startsWith("/api/chats"))
        return Promise.resolve({ chats: [], next_cursor: null, has_more: false }) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    // Wait for debounce + lookup to resolve
    await waitFor(() => {
      expect(result.current.lookingUp).toBe(false)
    })

    expect(result.current.existingMatches).toHaveLength(1)
    expect(result.current.existingMatches[0].id).toBe("existing-multi")
    expect(result.current.exactMatchExists).toBe(true)
  })

  test("Enter on compose-match navigates to that chat", async () => {
    const alice = makeChat({
      id: "chat-1",
      name: "Alice",
      user: { id: "u-alice", display_name: "Alice", picture: null },
    })
    const bob = makeContact({ id: "u-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [alice] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Add two recipients to enter compose mode
    act(() => {
      result.current.toggleRecipient({ id: "u-alice", name: "Alice", picture: null })
    })
    act(() => {
      result.current.toggleRecipient({ id: "u-bob", name: "Bob", picture: null })
    })

    // Mock lookup returns a match
    const matchChat = makeChat({ id: "existing-multi", name: "Alice, Bob", type: "multi", collaborator_count: 3 })
    mockApiFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.startsWith("/api/chats/lookup"))
        return Promise.resolve({ matches: [matchChat], match_group: null, next_cursor: null, has_more: false }) as any
      if (typeof url === "string" && url.startsWith("/api/chats/contacts"))
        return Promise.resolve({ contacts: [], next_cursor: null, has_more: false }) as any
      if (typeof url === "string" && url.startsWith("/api/chats"))
        return Promise.resolve({ chats: [], next_cursor: null, has_more: false }) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    await waitFor(() => expect(result.current.lookingUp).toBe(false))
    expect(result.current.existingMatches[0].id).toBe("existing-multi")

    // First selectable item in compose mode is the compose-match
    expect(result.current.selectableItems[0]?.kind).toBe("compose-match")
    expect(result.current.selectedIndex).toBe(0)

    // Enter navigates to the existing match
    act(() => {
      result.current.handleKeyDown({ key: "Enter", preventDefault: vi.fn() } as any)
    })

    expect(navigateSpy).toHaveBeenCalledWith({
      to: "/chats/$chatId",
      params: { chatId: "existing-multi" },
      search: { return_to: "/chats" },
    })
  })

  test("lookup returning multiple matches surfaces all of them", async () => {
    const bob = makeContact({ id: "u-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.toggleRecipient({ id: "u-bob", name: "Bob", picture: null })
    })

    // DM (exact, collaborator_count=2), multi (superset, collaborator_count=3), and group (superset, collaborator_count=4)
    const dm = makeChat({ id: "dm-1", name: "Bob", type: "dm", collaborator_count: 2 })
    const multi = makeChat({ id: "multi-1", name: "Bob, Carol", type: "multi", collaborator_count: 3 })
    const group = makeChat({ id: "group-1", name: "Crew", type: "group", collaborator_count: 4 })
    mockApiFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.startsWith("/api/chats/lookup"))
        return Promise.resolve({
          matches: [dm, multi, group],
          match_group: null,
          next_cursor: null,
          has_more: false,
        }) as any
      if (typeof url === "string" && url.startsWith("/api/chats/contacts"))
        return Promise.resolve({ contacts: [], next_cursor: null, has_more: false }) as any
      if (typeof url === "string" && url.startsWith("/api/chats"))
        return Promise.resolve({ chats: [], next_cursor: null, has_more: false }) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    await waitFor(() => expect(result.current.lookingUp).toBe(false))

    expect(result.current.existingMatches).toHaveLength(3)
    expect(result.current.exactMatchExists).toBe(true)

    const composeMatches = result.current.visibleItems.filter(i => i.kind === "compose-match")
    expect(composeMatches).toHaveLength(3)
    if (composeMatches[0].kind === "compose-match") {
      expect(composeMatches[0].chat.id).toBe("dm-1")
    }
  })

  test("superset-only matches leave exactMatchExists false", async () => {
    const bob = makeContact({ id: "u-bob", name: "Bob", type: "dm" })

    mockInitialFetch({ chats: [] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => {
      result.current.toggleRecipient({ id: "u-bob", name: "Bob", picture: null })
    })

    // Only a superset chat: user + bob + carol. No DM.
    const multi = makeChat({ id: "multi-1", name: "Bob, Carol", type: "multi", collaborator_count: 3 })
    mockApiFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.startsWith("/api/chats/lookup"))
        return Promise.resolve({ matches: [multi], match_group: null, next_cursor: null, has_more: false }) as any
      if (typeof url === "string" && url.startsWith("/api/chats/contacts"))
        return Promise.resolve({ contacts: [], next_cursor: null, has_more: false }) as any
      if (typeof url === "string" && url.startsWith("/api/chats"))
        return Promise.resolve({ chats: [], next_cursor: null, has_more: false }) as any
      return Promise.reject(new Error(`Unexpected URL: ${url}`))
    })

    await waitFor(() => expect(result.current.lookingUp).toBe(false))

    expect(result.current.existingMatches).toHaveLength(1)
    expect(result.current.exactMatchExists).toBe(false)
  })

  test("setSearchQuery and setGroupFilter reset selectedIndex", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    const engineering = makeChat({ id: "chat-2", name: "Engineering", type: "group" })
    const bob = makeContact({ id: "contact-1", name: "Bob" })

    mockInitialFetch({ chats: [alice, engineering] }, { contacts: [bob] })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    // Navigate down
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    expect(result.current.selectedIndex).toBe(2)

    // setSearchQuery resets
    act(() => result.current.setSearchQuery("x"))
    expect(result.current.selectedIndex).toBe(0)

    // Navigate down again
    act(() => result.current.setSearchQuery(""))
    act(() => result.current.handleKeyDown({ key: "ArrowDown", preventDefault: vi.fn() } as any))
    expect(result.current.selectedIndex).toBe(1)

    // setGroupFilter resets
    act(() => result.current.setGroupFilter("groups"))
    expect(result.current.selectedIndex).toBe(0)
  })

  test("search with hasMore true triggers page walk and finds page-2 chat", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    const nina = makeChat({ id: "chat-2", name: "Nina" })
    const page1: ChatListResponse = { chats: [alice], next_cursor: "cursor1", has_more: true }
    const page2: ChatListResponse = { chats: [nina], next_cursor: null, has_more: false }

    mockPaginatedFetch(page1, { cursor1: page2 })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.setSearchQuery("nina"))

    await waitFor(() => {
      expect(mockApiFetch.mock.calls.map(([url]) => url)).toContain("/api/chats?cursor=cursor1")
    })

    await waitFor(() => {
      expect(result.current.visibleItems.some(i => i.kind === "chat" && i.chat.name === "Nina")).toBe(true)
    })
  })

  test("clearing search query halts the page walk", async () => {
    // With the infinite-query cache, an in-flight page (cursor1) may still land
    // after search clears, but the walk must not continue to the next page —
    // clearing search stops further pagination (the old cancel-and-discard intent).
    const alice = makeChat({ id: "chat-1", name: "Alice" })
    const nina = makeChat({ id: "chat-2", name: "Nina" })
    const page1: ChatListResponse = { chats: [alice], next_cursor: "cursor1", has_more: true }
    const page2: ChatListResponse = { chats: [nina], next_cursor: "cursor2", has_more: true }
    const page3: ChatListResponse = { chats: [], next_cursor: null, has_more: false }

    mockPaginatedFetch(page1, { cursor1: page2, cursor2: page3 })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.setSearchQuery("nina"))
    act(() => result.current.setSearchQuery(""))

    await waitFor(() => expect(result.current.loadingMore).toBe(false))

    expect(mockApiFetch.mock.calls.map(([url]) => url)).not.toContain("/api/chats?cursor=cursor2")
  })

  test("search when hasMore false (all chats loaded) does not trigger fetch", async () => {
    const alice = makeChat({ id: "chat-1", name: "Alice", type: "dm" })
    const engineering = makeChat({ id: "chat-2", name: "Engineering", type: "group" })

    mockInitialFetch({ chats: [alice, engineering], has_more: false, next_cursor: null })

    const { result } = renderHookWithClient(() => useChatsData("org-1", "current-user"))

    await waitFor(() => expect(result.current.loading).toBe(false))

    const callsAfterInit = mockApiFetch.mock.calls.length

    act(() => result.current.setSearchQuery("ali"))

    await waitFor(() => {
      expect(result.current.visibleItems.some(i => i.kind === "chat" && i.chat.name === "Alice")).toBe(true)
    })

    expect(mockApiFetch.mock.calls.length).toBe(callsAfterInit)
  })
})
