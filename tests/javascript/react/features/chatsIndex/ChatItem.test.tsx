import { cleanup, render, screen, fireEvent } from "@testing-library/react"
import { afterEach, describe, expect, test, vi } from "vitest"

import { ChatItem } from "../../../../../app/javascript/react/features/chatsIndex/components/ChatItem"
import type { ChatListItem } from "../../../../../app/javascript/react/features/chatsIndex/types"

vi.mock("../../../../../app/javascript/react/ui/DateTime", () => ({
  DateTime: ({ datetime, className }: { datetime: string; className?: string }) => (
    <time dateTime={datetime} className={className}>
      mocked-time
    </time>
  ),
}))

vi.mock("../../../../../app/javascript/react/ui/Avatar", () => ({
  Avatar: ({ displayName }: { displayName: string }) => <div data-testid="avatar">{displayName}</div>,
}))

function makeChat(overrides: Partial<ChatListItem> = {}): ChatListItem {
  return {
    id: "chat-1",
    type: "dm",
    name: "Alice",
    collaborator_count: 2,
    collaborators: null,
    latest_message: {
      id: "msg-1",
      content: "Hey there!",
      created_at: "2026-04-08T12:00:00Z",
      user: { id: "u1", display_name: "Alice Smith", picture: null },
      link_preview: null,
      reactions: {},
      edited_at: null,
      reply_to: null,
    },
    user: { id: "u1", display_name: "Alice Smith", picture: null },
    picture: null,
    is_unread: false,
    is_archived: false,
    snoozed_until: null,
    ...overrides,
  }
}

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderChatItem(chat = makeChat(), props: Partial<Parameters<typeof ChatItem>[0]> = {}) {
  const defaults = {
    isSelected: false,
    isHovered: false,
    isNavigating: false,
    navigatingDisabled: false,
    onSelect: vi.fn(),
    onHover: vi.fn(),
  }
  return { ...defaults, ...render(<ChatItem chat={chat} {...defaults} {...props} />) }
}

describe("ChatItem", () => {
  test("renders chat name, message preview, and author first name", () => {
    renderChatItem()
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.getByText("Hey there!")).toBeTruthy()
    expect(screen.getByText("Alice:")).toBeTruthy()
  })

  test("renders relative time for latest message", () => {
    renderChatItem()
    expect(screen.getByText("mocked-time")).toBeTruthy()
  })

  test("shows unread indicator when chat is unread", () => {
    const { container } = renderChatItem(makeChat({ is_unread: true }))
    expect(container.querySelector(".bg-info-content")).toBeTruthy()
  })

  test("hides unread indicator when chat is read", () => {
    const { container } = renderChatItem(makeChat({ is_unread: false }))
    expect(container.querySelector(".bg-info-content")).toBeNull()
  })

  test("renders group icon, member count, and last sender avatar for group chats", () => {
    renderChatItem(makeChat({ type: "group", name: "Engineering", collaborator_count: 5 }))
    expect(screen.getByText("Engineering")).toBeTruthy()
    expect(screen.getByText("5")).toBeTruthy()
    expect(screen.getByTestId("avatar")).toBeTruthy()
  })

  test("collapses whitespace and markdown hard breaks to single spaces in preview", () => {
    renderChatItem(
      makeChat({
        latest_message: {
          id: "msg-1",
          content: "First line\\\nsecond line   with    spaces",
          created_at: "2026-04-08T12:00:00Z",
          user: { id: "u1", display_name: "Alice Smith", picture: null },
          link_preview: null,
        },
      })
    )
    expect(screen.getByText("First line second line with spaces")).toBeTruthy()
  })

  test("strips markdown bold and mention syntax from the preview", () => {
    renderChatItem(
      makeChat({
        latest_message: {
          id: "msg-1",
          content: "**bold** @[Alice]",
          created_at: "2026-04-08T12:00:00Z",
          user: { id: "u1", display_name: "Alice Smith", picture: null },
          link_preview: null,
        },
      })
    )
    const link = screen.getByRole("link")
    expect(link.textContent).toContain("bold")
    expect(link.textContent).not.toContain("**")
    expect(link.textContent).not.toContain("@[")
  })

  test("renders nothing for message when latest_message is null", () => {
    renderChatItem(makeChat({ latest_message: null }))
    expect(screen.getByText("Alice")).toBeTruthy()
    expect(screen.queryByText("mocked-time")).toBeNull()
  })

  test("calls onSelect when clicked", () => {
    const onSelect = vi.fn()
    renderChatItem(makeChat(), { onSelect })
    fireEvent.click(screen.getByText("Alice"))
    expect(onSelect).toHaveBeenCalledOnce()
  })

  test("calls onHover when mouse enters", () => {
    const onHover = vi.fn()
    renderChatItem(makeChat(), { onHover })
    fireEvent.mouseEnter(screen.getByRole("link"))
    expect(onHover).toHaveBeenCalledOnce()
  })

  test("shows spinner when navigating", () => {
    const { container } = renderChatItem(makeChat(), { isNavigating: true })
    expect(container.querySelector(".loading-spinner")).toBeTruthy()
  })

  test("applies selected styling", () => {
    renderChatItem(makeChat(), { isSelected: true })
    expect(screen.getByRole("link").className).toContain("bg-base-200")
  })

  test("renders stacked avatars and member count for multi chats", () => {
    renderChatItem(
      makeChat({
        type: "multi",
        name: "Alice, Bob, Charlie",
        collaborator_count: 3,
        collaborators: [
          { id: "m1", user: { id: "u1", display_name: "Alice", picture: null } },
          { id: "m2", user: { id: "u2", display_name: "Bob", picture: null } },
          { id: "m3", user: { id: "u3", display_name: "Charlie", picture: null } },
        ],
        user: null,
      })
    )
    expect(screen.getByText("Alice, Bob, Charlie")).toBeTruthy()
    expect(screen.getByText("3")).toBeTruthy()
    expect(screen.getAllByTestId("avatar")).toHaveLength(2)
    expect(screen.getByText("+1")).toBeTruthy()
  })

  test("shows +N overflow for multi chats with many members", () => {
    renderChatItem(
      makeChat({
        type: "multi",
        name: "Team Chat",
        collaborator_count: 5,
        collaborators: [
          { id: "m1", user: { id: "u1", display_name: "Alice", picture: null } },
          { id: "m2", user: { id: "u2", display_name: "Bob", picture: null } },
          { id: "m3", user: { id: "u3", display_name: "Charlie", picture: null } },
          { id: "m4", user: { id: "u4", display_name: "Diana", picture: null } },
          { id: "m5", user: { id: "u5", display_name: "Eve", picture: null } },
        ],
        user: null,
      })
    )
    expect(screen.getByText("+3")).toBeTruthy()
    expect(screen.getByText("5")).toBeTruthy()
  })
})
