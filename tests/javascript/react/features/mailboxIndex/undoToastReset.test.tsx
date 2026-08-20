import { cleanup, createTestQueryClient, fireEvent, waitFor } from "../../shared/testUtils"
import { renderInMailboxRouter } from "./harness"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MailboxIndex } from "../../../../../app/javascript/react/features/mailboxIndex/MailboxIndex"
import type {
  MailboxEntryListItem,
  MailboxEntryListResponse,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

// The undo toast's countdown is a single CSS fill animation that runs for the
// 8s undo window. Successive archives swap `undoable` from entry A to entry B
// without the toast unmounting, so the fill would otherwise keep running from
// wherever it was instead of restarting. MailboxIndex keys <UndoToast> on the
// entry id to force a remount, which restarts the fill from 0. This guards that
// reset: the progress bar must be a NEW DOM node after a second archive.

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
    goal_update: null,
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

// Fresh QueryClient per render so a cached entries query from a prior test can't
// shadow this test's fetch mock (see archiveHotkey.test.tsx for the full note).
function renderMailbox() {
  return renderInMailboxRouter(<MailboxIndex view="inbox" />, { client: createTestQueryClient() })
}

function pressKey(key: string, init: Partial<KeyboardEventInit> = {}) {
  fireEvent.keyDown(document.body, { key, ...init })
}

const barSelector = '[data-test-id="undo-progress-bar"]'

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(cleanup)

describe("undo toast countdown reset", () => {
  test("remounts the countdown bar when a second entry is archived", async () => {
    mockMailboxEndpoints([
      makeEntry({ id: "entry-1", title: "First" }),
      makeEntry({ id: "entry-2", title: "Second", href: "/chats/2" }),
    ])
    const { container } = await renderMailbox()
    await waitFor(() => expect(document.getElementById("mailbox-entry-entry-1")).toBeTruthy())

    // Archive the first entry -> toast appears with its countdown bar.
    pressKey("e")
    let barA: Element | null = null
    await waitFor(() => {
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/mailbox_entries/entry-1/archive",
        expect.objectContaining({ method: "POST" })
      )
      barA = container.querySelector(barSelector)
      expect(barA).not.toBeNull()
    })

    // Archiving entry-1 removes it, so the selection lands on entry-2. Archive it
    // while the toast is still visible.
    pressKey("e")
    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/mailbox_entries/entry-2/archive",
        expect.objectContaining({ method: "POST" })
      )
    )

    // The bar must be a brand-new node (key remount), not the same element still
    // running its half-finished fill. Regression guard for the countdown reset.
    await waitFor(() => {
      const barB = container.querySelector(barSelector)
      expect(barB).not.toBeNull()
      expect(barB).not.toBe(barA)
    })
  })
})
