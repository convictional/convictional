import { cleanup, createTestQueryClient, fireEvent, screen, waitFor } from "../../shared/testUtils"
import { renderInMailboxRouter } from "./harness"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MailboxIndex } from "../../../../../app/javascript/react/features/mailboxIndex/MailboxIndex"
import type {
  MailboxEntryListItem,
  MailboxEntryListResponse,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

// These exercise the real @github/hotkey binding: a dispatched `keydown` reaches
// the library's document listener, which synthesizes a click on the hidden
// [data-hotkey] button, which runs the React callback. Nothing about hotkeys is
// stubbed — only the external boundaries (network, websocket, flash) are mocked.

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

// The mailbox island fetches both /api/mailbox_entries (for the list) and
// /api/mailbox_views (to populate the sort dropdown's templates + saved views,
// even when no view is active). URL-dispatching the mock lets each test set up
// the entries response without worrying about call order.
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

// A fresh QueryClient per render keeps each test's entries query isolated; the
// singleton's cache would otherwise let one test's list shadow the next test's
// fetch mock.
function renderMailbox(view: "inbox" | "snoozed" = "inbox") {
  return renderInMailboxRouter(<MailboxIndex view={view} />, {
    initialEntries: [view === "snoozed" ? "/snoozed" : "/"],
    client: createTestQueryClient(),
  })
}

// Press a real key. fireEvent.keyDown dispatches a bubbling KeyboardEvent that
// reaches @github/hotkey's document-level listener, exactly like a real keystroke.
function pressKey(key: string) {
  fireEvent.keyDown(document.body, { key })
}

function hoverActionsForEntry(entryId: string): HTMLElement {
  const row = document.querySelector(`li #mailbox-entry-${entryId}, li[id="mailbox-entry-${entryId}"]`)
  const wrapper = row?.closest("li") ?? document.getElementById(`mailbox-entry-${entryId}`)?.closest("li")
  const actions = wrapper?.querySelector<HTMLElement>("[data-hover-actions]")
  if (!actions) throw new Error(`No hover-actions container for ${entryId}`)
  return actions
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(cleanup)

describe("MailboxIndex snooze hotkey", () => {
  test("pressing b opens the snooze dropdown for the selected entry (not the first one)", async () => {
    const first = makeEntry({ id: "entry-1", title: "First" })
    const second = makeEntry({ id: "entry-2", title: "Second", href: "/chats/2" })
    mockMailboxEndpoints([first, second])

    await renderMailbox()

    await waitFor(() => expect(document.getElementById("mailbox-entry-entry-1")).toBeTruthy())

    // Move selection to the second entry, then trigger the snooze hotkey.
    pressKey("ArrowDown")
    pressKey("b")

    // The dropdown should be open — its presets are portaled into the document.
    await waitFor(() => expect(screen.getByText(/Snooze until/i)).toBeInTheDocument())
    expect(screen.getByText(/Two hours from now/i)).toBeInTheDocument()

    // The selected row's hover-actions container is forced visible; the unselected
    // row's container stays hidden. This is what anchors the floating dropdown
    // for keyboard users who never hovered.
    expect(hoverActionsForEntry("entry-2").className).toMatch(/(^|\s)flex(\s|$)/)
    expect(hoverActionsForEntry("entry-1").className).toMatch(/(^|\s)hidden(\s|$)/)
  })

  test("only one b hotkey trigger exists at the index level (rows don't register duplicates)", async () => {
    mockMailboxEndpoints([makeEntry({ id: "entry-1" }), makeEntry({ id: "entry-2" })])

    await renderMailbox()
    await waitFor(() => expect(document.getElementById("mailbox-entry-entry-1")).toBeTruthy())

    // Per-row SnoozeDropdown triggers must opt out of data-hotkey="b"; otherwise
    // every hidden hover bar fights for the same key and none acts on the
    // selected row. Only the single MailboxIndex-level trigger should register.
    expect(document.querySelectorAll('button[data-hotkey="b"]')).toHaveLength(1)
  })

  test("pressing b on a snoozed entry does not open the dropdown", async () => {
    const snoozed = makeEntry({
      id: "entry-1",
      is_snoozed: true,
      is_archived: true,
      snoozed_until: "2030-01-01T00:00:00Z",
    })
    mockMailboxEndpoints([snoozed])

    // Render the snoozed view so the entry is visible.
    await renderMailbox("snoozed")
    await waitFor(() => expect(document.getElementById("mailbox-entry-entry-1")).toBeTruthy())

    pressKey("b")

    expect(screen.queryByText(/Snooze until/i)).toBeNull()
  })
})
