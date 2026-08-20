import { cleanup, createTestQueryClient, fireEvent, screen, waitFor } from "../../shared/testUtils"
import { renderInMailboxRouter } from "./harness"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MailboxIndex } from "../../../../../app/javascript/react/features/mailboxIndex/MailboxIndex"
import type {
  MailboxEntryListItem,
  MailboxEntryListResponse,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

// Binding-layer tests for the mailbox's archive ('e') and navigation (arrow)
// hotkeys. Like snoozeHotkey.test.tsx, @github/hotkey is NOT stubbed: a real
// `keydown` exercises the piece that flakes in the browser — key press ->
// @github/hotkey -> synthetic click on the [data-hotkey] element -> React
// callback -> API call. Only the external boundaries (network, websocket, flash)
// are mocked; everything from the keystroke inward runs for real, in jsdom.

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
  errorMessage: (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback),
}))

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: () => {},
}))

vi.mock("../../../../../app/javascript/channels/client", () => ({
  getChannelsClient: () => ({ on: () => {}, off: () => {} }),
}))

vi.mock("../../../../../app/javascript/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"

const mockApiFetch = vi.mocked(apiFetch)

function makeEntry(overrides: Partial<MailboxEntryListItem> = {}): MailboxEntryListItem {
  return {
    id: "entry-1",
    resource_type: "Chat",
    href: "/chats/1",
    title: "Test thread",
    preview: null,
    sender_display: null,
    last_activity_at: "2026-05-01T00:00:00Z",
    is_unread: true,
    is_archived: false,
    is_snoozed: false,
    snoozed_until: null,
    is_assigned_to_me: false,
    is_shared: false,
    email: null,
    chat: {
      is_group_chat: false,
      is_dm: true,
      collaborator_count: 2,
      counterparty: { id: "u1", display_name: "Alice", picture: null },
      last_message_author: null,
      member_avatars: [],
      overflow_count: 0,
      last_comment: null,
      last_comment_author_name: null,
    },
    post: null,
    goal: null,
    ...overrides,
  }
}

function makeResponse(entries: MailboxEntryListItem[]): MailboxEntryListResponse {
  return { entries, next_cursor: null, has_more: false, synced_at: "2026-05-01T00:00:00Z" }
}

function mockMailboxEndpoints(entries: MailboxEntryListItem[]) {
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
      return Promise.resolve({
        all_views: [],
        active: null,
        cached_sections: null,
        cached_entry_ids: [],
        generating: false,
        has_goals_for_view: false,
        is_not_found: false,
      })
    }
    return Promise.resolve(makeResponse(entries))
  })
}

// Use a fresh QueryClient per render. The singleton is shared across the whole
// file, so a cached entries query from a prior test would shadow this test's fetch
// mock and the list would never render.
function renderMailbox() {
  return renderInMailboxRouter(<MailboxIndex view="inbox" />, { client: createTestQueryClient() })
}

// This is the whole trick: press a REAL key. fireEvent.keyDown dispatches a
// bubbling KeyboardEvent that reaches @github/hotkey's document-level listener,
// exactly like a browser keystroke. `key` is the property the library reads.
function pressKey(key: string, init: Partial<KeyboardEventInit> = {}) {
  fireEvent.keyDown(document.body, { key, ...init })
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(cleanup)

describe("MailboxIndex hotkey bindings (real @github/hotkey)", () => {
  test("pressing 'e' archives the selected entry via the API", async () => {
    mockMailboxEndpoints([makeEntry({ id: "entry-1" })])
    await renderMailbox()
    await waitFor(() => expect(document.getElementById("mailbox-entry-entry-1")).toBeTruthy())

    pressKey("e")

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/mailbox_entries/entry-1/archive",
        expect.objectContaining({ method: "POST" })
      )
    )
  })

  test("pressing 'b' opens the snooze dropdown for the selected entry", async () => {
    mockMailboxEndpoints([makeEntry({ id: "entry-1" })])
    await renderMailbox()
    await waitFor(() => expect(document.getElementById("mailbox-entry-entry-1")).toBeTruthy())

    pressKey("b")

    await waitFor(() => expect(screen.getByText(/Snooze until/i)).toBeInTheDocument())
  })

  test("ArrowDown moves selection, so 'e' archives the SECOND entry", async () => {
    mockMailboxEndpoints([
      makeEntry({ id: "entry-1", title: "First" }),
      makeEntry({ id: "entry-2", title: "Second", href: "/chats/2" }),
    ])
    await renderMailbox()
    await waitFor(() => expect(document.getElementById("mailbox-entry-entry-2")).toBeTruthy())

    pressKey("ArrowDown")
    pressKey("e")

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/mailbox_entries/entry-2/archive",
        expect.objectContaining({ method: "POST" })
      )
    )
  })
})
