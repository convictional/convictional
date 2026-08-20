import { act, cleanup, fireEvent, waitFor, within } from "../../shared/testUtils"
import { renderInMailboxRouter } from "./harness"
import { queryClient } from "~/react/shared/queryClient"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MailboxIndex } from "../../../../../app/javascript/react/features/mailboxIndex/MailboxIndex"
import type {
  ActiveMailboxView,
  MailboxEntryListItem,
  MailboxEntryLookupResponse,
  MailboxSyncPayload,
  MailboxViewIndexResponse,
  ViewSection,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"
import { ChannelEventAction, ChannelEventResource } from "../../../../../app/javascript/types/channels"

vi.mock("@github/hotkey", () => ({
  install: vi.fn(),
  uninstall: vi.fn(),
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
  errorMessage: (e: unknown, fallback: string) => (e instanceof Error ? e.message : fallback),
}))

// Capture the sync handler so a test can drive the live new-messages count (and thus the banner).
type ChannelHandler = (action: ChannelEventAction, data: Record<string, unknown>) => void
const channelSubscriptions = new Map<string, ChannelHandler>()

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (target: { stream: string; params: Record<string, string>; extraParams?: Record<string, string> } | null, resource: string, onMessage: ChannelHandler) => {
    if (target) channelSubscriptions.set(resource, onMessage)
  },
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

const ACTIVE_VIEW: ActiveMailboxView = {
  kind: "template",
  id: "template:by_goals",
  title: "By goals",
  view_request: null,
  channel_id: "template:by_goals",
  requires_goals: false,
}

const SECTION: ViewSection = {
  title: "Sales",
  description: "",
  mailbox_entry_ids: ["entry-1"],
  goal: null,
}

function mockViewModeEndpoints(entries: MailboxEntryListItem[], coverage: Partial<MailboxViewIndexResponse> = {}) {
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
      const response: MailboxViewIndexResponse = {
        all_views: [],
        active: ACTIVE_VIEW,
        cached_sections: [{ ...SECTION, mailbox_entry_ids: entries.map(e => e.id) }],
        cached_entry_ids: entries.map(e => e.id),
        generating: false,
        has_goals_for_view: true,
        is_not_found: false,
        ...coverage,
      }
      return Promise.resolve(response)
    }
    if (typeof url === "string" && url.startsWith("/api/mailbox_entries/lookup?ids=")) {
      const response: MailboxEntryLookupResponse = { entries, next_cursor: null, has_more: false }
      return Promise.resolve(response)
    }
    if (typeof url === "string" && url === "/api/users/me") {
      return Promise.resolve({
        id: "current-user",
        display_name: "Current User",
        picture: null,
        client_config: { klipy_api_key: null },
      })
    }
    return Promise.resolve(undefined)
  })
}

function renderViewMailbox() {
  return renderInMailboxRouter(<MailboxIndex view="inbox" mailbox_view_template="by_goals" />, {
    initialEntries: ["/?mailbox_view_template=by_goals"],
  })
}

function findHotkeyButton(key: string): HTMLButtonElement {
  const el = document.querySelector<HTMLButtonElement>(`button[data-hotkey="${key}"]`)
  if (!el) throw new Error(`No button[data-hotkey="${key}"] in DOM`)
  return el
}

function findRefreshButton(): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll("button")).find(b => b.textContent?.trim() === "Refresh")
}

async function fireSyncEvent(payload: MailboxSyncPayload) {
  const onMessage = channelSubscriptions.get(ChannelEventResource.MAILBOX_SYNC)
  if (!onMessage) throw new Error("sync handler was not captured")
  await act(async () => {
    onMessage(ChannelEventAction.UPDATE, payload as unknown as Record<string, unknown>)
  })
}

beforeEach(() => {
  // The view order + bodies live in the shared query cache now, so clear it between tests (mirrors the
  // sibling useMailboxView / streaming suites) — otherwise a warm cache from a prior test is served.
  queryClient.clear()
  mockApiFetch.mockReset()
  channelSubscriptions.clear()
})

afterEach(cleanup)

// Regression: when a mailbox view is active, entries are sourced from
// useMailboxView.entriesById rather than the inbox firstPage. Mutations must
// reach into that store so the row visually reflects archive/mark-read,
// otherwise the optimistic update vanishes and the user thinks the action
// silently failed.
describe("MailboxIndex actions in view mode", () => {
  test("hover-action archive updates the rendered row and posts to the API", async () => {
    mockViewModeEndpoints([makeEntry({ id: "entry-1" })])

    await renderViewMailbox()

    const row = await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      if (!el) throw new Error("entry row not rendered yet")
      return el
    })
    expect(row.dataset.isArchived).toBe("false")

    const archiveCallsBefore = mockApiFetch.mock.calls.filter(
      ([url]) => typeof url === "string" && url.includes("/archive")
    ).length

    // The action bar mounts only while the row is hovered. React synthesizes
    // onMouseEnter from a native mouseover, so fire that to reveal the actions.
    fireEvent.mouseOver(row)
    fireEvent.click(within(row).getByLabelText("Archive"))

    // Archived entries should be optimistically removed from the view —
    // they're excluded from the next server regeneration, so the UI should
    // mirror that immediately rather than leave a stale row in place.
    await waitFor(() => {
      expect(document.querySelector('[data-test-id="mailbox-entry-entry-1"]')).toBeNull()
    })

    const archiveCallsAfter = mockApiFetch.mock.calls.filter(
      ([url]) => typeof url === "string" && url.includes("/api/mailbox_entries/entry-1/archive")
    ).length
    expect(archiveCallsAfter).toBe(archiveCallsBefore + 1)
  })

  test("hover-action mark-read updates the rendered row and posts to the API", async () => {
    mockViewModeEndpoints([makeEntry({ id: "entry-1", is_unread: true })])

    await renderViewMailbox()

    const row = await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      if (!el) throw new Error("entry row not rendered yet")
      return el
    })
    expect(row.dataset.isUnread).toBe("true")

    // The action bar mounts only while the row is hovered.
    fireEvent.mouseOver(row)
    fireEvent.click(within(row).getByLabelText("Mark read"))

    await waitFor(() => {
      const updated = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      expect(updated?.dataset.isUnread).toBe("false")
    })

    expect(
      mockApiFetch.mock.calls.some(
        ([url]) => typeof url === "string" && url === "/api/mailbox_entries/entry-1/mark_read"
      )
    ).toBe(true)
  })

  // Regression: when a view is active, the inbox-entries list endpoint must
  // not be hit. The visible rows come from useMailboxView.entriesById (the
  // lookup fetch); the standard view/sort fetch is wasted work and we
  // explicitly disable useMailboxEntries' initial load in that case.
  test("does not fetch the inbox entries list when a view is active", async () => {
    mockViewModeEndpoints([makeEntry({ id: "entry-1" })])

    await renderViewMailbox()

    await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      if (!el) throw new Error("entry row not rendered yet")
    })

    const inboxListCalls = mockApiFetch.mock.calls.filter(([url]) => {
      if (typeof url !== "string") return false
      if (!url.startsWith("/api/mailbox_entries")) return false
      return !url.startsWith("/api/mailbox_entries/lookup")
    })
    expect(inboxListCalls).toEqual([])
  })

  test("archive hotkey (e) targets the entry from the view sections", async () => {
    mockViewModeEndpoints([makeEntry({ id: "entry-1" })])

    await renderViewMailbox()

    await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      if (!el) throw new Error("entry row not rendered yet")
    })

    fireEvent.click(findHotkeyButton("e"))

    await waitFor(() => {
      expect(document.querySelector('[data-test-id="mailbox-entry-entry-1"]')).toBeNull()
    })

    expect(
      mockApiFetch.mock.calls.some(
        ([url]) => typeof url === "string" && url === "/api/mailbox_entries/entry-1/archive"
      )
    ).toBe(true)
  })

  // Regression: the "new conversations not included" banner shows for built-in template sorts
  // (kind "template", id "template:..."), not just saved views. Its Refresh button must fire for
  // them — the original bug was a `kind === "view"` guard that made the click a silent no-op.
  test("refresh button on a template sort posts to the encoded identifier without reloading", async () => {
    mockViewModeEndpoints([makeEntry({ id: "entry-1" })])

    await renderViewMailbox()
    await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      if (!el) throw new Error("entry row not rendered yet")
    })

    // The banner is hidden until the live count is positive — drive it with a sync event.
    await fireSyncEvent({ type: "new_messages", view_id: ACTIVE_VIEW.channel_id, count: 3 })
    const refreshButton = await waitFor(() => {
      const el = findRefreshButton()
      if (!el) throw new Error("Refresh button not rendered")
      return el
    })

    const reload = vi.fn()
    const originalLocation = window.location
    Object.defineProperty(window, "location", { value: { reload }, writable: true, configurable: true })
    try {
      await act(async () => {
        fireEvent.click(refreshButton)
      })
      await waitFor(() => {
        expect(
          mockApiFetch.mock.calls.some(
            ([url]) => typeof url === "string" && url === "/api/mailbox_views/template%3Aby_goals/refresh"
          )
        ).toBe(true)
      })
      expect(reload).not.toHaveBeenCalled()
    } finally {
      Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true })
    }
  })

  // Regression (#9245): working an inbox larger than the generation slice emptied the view while the
  // remainder stayed unreachable — refresh was only offered when new mail arrived.
  test("clearing every organized item prompts a refresh when the inbox has more", async () => {
    mockViewModeEndpoints([makeEntry({ id: "entry-1" })], {
      eligible_entry_count: 300,
      considered_entry_count: 250,
    })

    await renderViewMailbox()
    await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      if (!el) throw new Error("entry row not rendered yet")
    })

    expect(findRefreshButton()).toBeUndefined()

    fireEvent.click(findHotkeyButton("e"))

    await waitFor(() => {
      if (!findRefreshButton()) throw new Error("Refresh button not rendered")
    })
    expect(document.body.textContent).toContain("You've cleared everything here")
  })

  test("clearing the view stays silent when generation covered the whole inbox", async () => {
    mockViewModeEndpoints([makeEntry({ id: "entry-1" })], {
      eligible_entry_count: 1,
      considered_entry_count: 1,
    })

    await renderViewMailbox()
    await waitFor(() => {
      const el = document.querySelector<HTMLElement>('[data-test-id="mailbox-entry-entry-1"]')
      if (!el) throw new Error("entry row not rendered yet")
    })

    fireEvent.click(findHotkeyButton("e"))

    await waitFor(() => {
      expect(document.querySelector('[data-test-id="mailbox-entry-entry-1"]')).toBeNull()
    })
    expect(findRefreshButton()).toBeUndefined()
  })
})
