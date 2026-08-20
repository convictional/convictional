import { afterEach, describe, expect, test } from "vitest"

import { cleanup, createTestQueryClient, render, renderWithClient, screen } from "../../shared/testUtils"
import { ChatEntryBody } from "../../../../../app/javascript/react/features/mailboxIndex/components/entryBodies/ChatEntryBody"
import type {
  ChatEntryDetail,
  MailboxEntry,
  MailboxEntryListItem,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

function makeChatEntry(chat: ChatEntryDetail | null, overrides: Partial<MailboxEntryListItem> = {}): MailboxEntry {
  return {
    id: "c1",
    resource_type: "Chat",
    href: "/chats/1?mailbox_entry_id=c1",
    title: "Launch war room",
    preview: null,
    sender_display: null,
    last_activity_at: "2026-05-01T00:00:00Z",
    is_unread: true,
    is_archived: false,
    is_snoozed: false,
    snoozed_until: null,
    is_assigned_to_me: false,
    is_shared: true,
    email: null,
    chat,
    post: null,
    goal: null,
    ...overrides,
  }
}

function chatDetail(overrides: Partial<ChatEntryDetail> = {}): ChatEntryDetail {
  return {
    is_group_chat: false,
    is_dm: true,
    collaborator_count: 2,
    counterparty: { id: "u1", display_name: "Alice", picture: null },
    last_message_author: null,
    member_avatars: [],
    overflow_count: 0,
    preview_kind: "comment",
    last_comment: null,
    last_comment_author_name: null,
    event_action: null,
    event_details: null,
    event_actor: null,
    ...overrides,
  }
}

afterEach(cleanup)

describe("ChatEntryBody", () => {
  test("renders the last message as an inline author-prefixed preview", () => {
    render(
      <ChatEntryBody
        entry={makeChatEntry(chatDetail({ last_comment: "Hello there", last_comment_author_name: "Alice" }))}
      />
    )
    expect(screen.getByText("Launch war room")).toBeTruthy()
    expect(screen.getByText("Alice:")).toBeTruthy()
    expect(screen.getByText("Hello there")).toBeTruthy()
  })

  test("phrases a rename activity line from the actor and title", () => {
    render(
      <ChatEntryBody
        entry={makeChatEntry(
          chatDetail({
            preview_kind: "activity",
            event_action: "chat_renamed",
            event_details: { title: "Roadmap" },
            event_actor: { id: "u2", display_name: "Ada", picture: null },
          })
        )}
      />
    )
    expect(screen.getByText("Ada renamed the chat to Roadmap")).toBeTruthy()
  })

  test("phrases a decided activity line via the shared cross-resource wording", () => {
    render(
      <ChatEntryBody
        entry={makeChatEntry(
          chatDetail({
            preview_kind: "activity",
            event_action: "decided",
            event_details: null,
            event_actor: { id: "u2", display_name: "Ada", picture: null },
          })
        )}
      />
    )
    // Unified with posts/email through describeCrossResourceActivity (no per-resource drift).
    expect(screen.getByText("Marked as decided")).toBeTruthy()
  })

  test("resolves the added member's name from the org-members cache", () => {
    const client = createTestQueryClient()
    client.setQueryData(["organizationMembers"], {
      users: [{ id: "u9", display_name: "Bob", picture: null }],
      groups: [],
    })
    renderWithClient(
      <ChatEntryBody
        entry={makeChatEntry(
          chatDetail({
            preview_kind: "activity",
            event_action: "chat_collaborator_added",
            event_details: { user_id: "u9" },
            event_actor: { id: "u2", display_name: "Ada", picture: null },
          })
        )}
      />,
      client
    )
    expect(screen.getByText("Ada added Bob")).toBeTruthy()
  })

  test("renders nothing without chat detail", () => {
    const { container } = render(<ChatEntryBody entry={makeChatEntry(null)} />)
    expect(container.firstChild).toBeNull()
  })
})
