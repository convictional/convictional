import { cleanup, render, screen, fireEvent } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { ChatsIndex } from "../../../../../app/javascript/react/features/chatsIndex/ChatsIndex"
import { setCurrentUser } from "../../shared/currentUserFixtures"
import type { ChatListItem, Contact, GroupFilter } from "../../../../../app/javascript/react/features/chatsIndex/types"
import type { VisibleItem } from "../../../../../app/javascript/react/features/chatsIndex/hooks/useChatsData"

const mockObserve = vi.fn()
const mockDisconnect = vi.fn()

beforeEach(() => {
  mockObserve.mockClear()
  mockDisconnect.mockClear()
  vi.stubGlobal(
    "IntersectionObserver",
    vi.fn(function () {
      return { observe: mockObserve, disconnect: mockDisconnect, unobserve: vi.fn() }
    })
  )
  setCurrentUser({ id: "current-user", display_name: "Me" })
})

vi.mock("../../../../../app/javascript/react/ui/DateTime", () => ({
  DateTime: ({ datetime }: { datetime: string }) => <time dateTime={datetime}>mocked-time</time>,
}))

vi.mock("../../../../../app/javascript/react/ui/Avatar", () => ({
  Avatar: ({ displayName }: { displayName: string }) => <div data-testid="avatar">{displayName}</div>,
}))

const noopFn = () => {}

function makeChat(overrides: Partial<ChatListItem> = {}): ChatListItem {
  return {
    id: "chat-1",
    type: "dm",
    name: "Alice",
    collaborator_count: 2,
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

const defaultHookReturn = {
  // A non-solo org by default: with empty chats and contacts the index renders ChatFirstRun
  // (the first-user nudge) instead of the list, so the list/compose tests below seed one chat.
  chats: [makeChat()] as ChatListItem[],
  contacts: [] as Contact[],
  loading: false,
  loadingMore: false,
  error: false,
  hasMore: false,
  loadMore: noopFn,
  searchQuery: "",
  setSearchQuery: noopFn as (q: string) => void,
  groupFilter: "all" as GroupFilter,
  setGroupFilter: noopFn as (f: GroupFilter) => void,
  visibleItems: [] as VisibleItem[],
  selectableItems: [] as VisibleItem[],
  selectedIndex: 0,
  setSelectedIndex: noopFn as (i: number) => void,
  hoveredIndex: null as number | null,
  setHoveredIndex: noopFn as (i: number | null) => void,
  navigating: false,
  navigatingId: null as string | null,
  createError: null as string | null,
  selectChat: noopFn as (id: string) => void,
  selectContact: noopFn as (id: string, type: "dm" | "group") => Promise<void>,
  createGroupAndOpen: noopFn as (name: string) => Promise<void>,
  inviteTeammate: noopFn as (email: string) => Promise<void>,
  handleKeyDown: noopFn as (e: React.KeyboardEvent) => void,
  composing: false,
  selectedRecipients: [] as { id: string; name: string; picture: string | null }[],
  toggleRecipient: noopFn as (r: { id: string; name: string; picture: string | null }) => void,
  removeRecipient: noopFn as (id: string) => void,
  existingMatches: [] as ChatListItem[],
  existingMatchGroup: null as { id: string; name: string } | null,
  exactMatchExists: false,
  lookingUp: false,
  lookupError: false,
  createChat: noopFn as () => Promise<void>,
  toggleComposeMode: noopFn,
}

vi.mock("../../../../../app/javascript/react/features/chatsIndex/hooks/useChatsData", () => ({
  useChatsData: vi.fn(() => defaultHookReturn),
}))

import { useChatsData } from "../../../../../app/javascript/react/features/chatsIndex/hooks/useChatsData"
const mockUseChatsData = vi.mocked(useChatsData)

function setHookReturn(overrides: Partial<typeof defaultHookReturn>) {
  mockUseChatsData.mockReturnValue({ ...defaultHookReturn, ...overrides })
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe("ChatsIndex", () => {
  test("shows loading skeleton when loading", () => {
    setHookReturn({ loading: true })
    const { container } = render(<ChatsIndex />)
    expect(container.querySelector('[data-testid="chats-list-skeleton"]')).toBeTruthy()
  })

  test("shows error state when error is true", () => {
    setHookReturn({ error: true })
    render(<ChatsIndex />)
    expect(screen.getByText("Something went wrong")).toBeTruthy()
    expect(screen.getByText("Failed to load chats. Please try refreshing the page.")).toBeTruthy()
  })

  test("shows empty search state when no results match search", () => {
    setHookReturn({ searchQuery: "zzz", visibleItems: [], selectableItems: [] })
    render(<ChatsIndex />)
    expect(screen.getByText("No results match your search")).toBeTruthy()
  })

  test("shows empty groups state when filtering groups with none", () => {
    setHookReturn({ groupFilter: "groups", visibleItems: [], selectableItems: [] })
    render(<ChatsIndex />)
    expect(screen.getByText("No group chats yet")).toBeTruthy()
  })

  test("renders chat items from visibleItems", () => {
    const chat = makeChat()
    const items: VisibleItem[] = [{ kind: "chat", chat }]
    setHookReturn({ visibleItems: items, selectableItems: items })
    render(<ChatsIndex />)
    expect(screen.getByRole("link", { name: /Alice/ })).toBeTruthy()
  })

  test("renders contact divider and contacts", () => {
    const chat = makeChat()
    const contact = makeContact()
    const items: VisibleItem[] = [{ kind: "chat", chat }, { kind: "contact-divider" }, { kind: "contact", contact }]
    setHookReturn({ visibleItems: items, selectableItems: items.filter(i => i.kind !== "contact-divider") })
    render(<ChatsIndex />)
    expect(screen.getByText("Contacts")).toBeTruthy()
    expect(screen.getByRole("button", { name: /Bob/ })).toBeTruthy()
  })

  test("shows create error when present", () => {
    const chat = makeChat()
    const items: VisibleItem[] = [{ kind: "chat", chat }]
    setHookReturn({
      createError: "Something went wrong. Please try again.",
      visibleItems: items,
      selectableItems: items,
    })
    render(<ChatsIndex />)
    expect(screen.getByText("Something went wrong. Please try again.")).toBeTruthy()
  })

  test("shows loading-more spinner when loadingMore is true", () => {
    const chat = makeChat()
    const items: VisibleItem[] = [{ kind: "chat", chat }]
    setHookReturn({ visibleItems: items, selectableItems: items, hasMore: true, loadingMore: true })
    const { container } = render(<ChatsIndex />)
    expect(container.querySelectorAll(".loading-spinner").length).toBe(1)
  })

  test("registers the load-more sentinel when hasMore is true", () => {
    const chat = makeChat()
    const items: VisibleItem[] = [{ kind: "chat", chat }]
    setHookReturn({ visibleItems: items, selectableItems: items, hasMore: true })
    render(<ChatsIndex />)
    expect(mockObserve).toHaveBeenCalledTimes(1)
  })

  test("shows composing empty state when all contacts selected", () => {
    setHookReturn({ composing: true, visibleItems: [], selectableItems: [] })
    render(<ChatsIndex />)
    expect(screen.getByText("All contacts selected")).toBeTruthy()
  })

  test("renders group filter dropdown in header", () => {
    setHookReturn({ visibleItems: [], selectableItems: [] })
    render(<ChatsIndex />)
    expect(screen.getByText("All")).toBeTruthy()
  })

  test("renders search input", () => {
    setHookReturn({ visibleItems: [], selectableItems: [] })
    render(<ChatsIndex />)
    expect(screen.getByPlaceholderText("Search...")).toBeTruthy()
  })
})
