import { cleanup, waitFor } from "../../shared/testUtils"
import { renderInMailboxRouter } from "./harness"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { MailboxIndex } from "../../../../../app/javascript/react/features/mailboxIndex/MailboxIndex"
import type {
  ActiveMailboxView,
  MailboxEntryLookupResponse,
  MailboxViewIndexResponse,
  ViewSection,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

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

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: () => {},
}))

vi.mock("../../../../../app/javascript/channels/client", () => ({
  getChannelsClient: () => ({ on: () => {}, off: () => {} }),
}))

vi.mock("../../../../../app/javascript/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"

const mockApiFetch = vi.mocked(apiFetch)

const ACTIVE_VIEW: ActiveMailboxView = {
  kind: "template",
  id: "template:priority",
  title: "Priority",
  view_request: null,
  channel_id: "template:priority",
  requires_goals: false,
}

const SECTION: ViewSection = {
  title: "Sales",
  description: "",
  mailbox_entry_ids: [],
  goal: null,
}

const ORGANIZING_TEXT = "Organizing your inbox..."

function renderViewMailbox() {
  return renderInMailboxRouter(<MailboxIndex view="inbox" mailbox_view_template="priority" />, {
    initialEntries: ["/?mailbox_view_template=priority"],
  })
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

afterEach(cleanup)

// Regression for #8638: pinning a custom sort must show the skeleton loader while the view
// resolves, not the "Organizing your inbox…" text. That text is reserved for genuine progressive
// generation (isGenerating), where results are still being organized.
describe("MailboxIndex view loading state", () => {
  test("shows the skeleton (not Organizing) while a pinned sort's cached results load", async () => {
    // Hold the index request open so we can observe the loading state deterministically.
    let resolveIndex: (response: MailboxViewIndexResponse) => void = () => {}
    const indexPromise = new Promise<MailboxViewIndexResponse>(resolve => {
      resolveIndex = resolve
    })
    mockApiFetch.mockImplementation((url: string) => {
      if (url.startsWith("/api/mailbox_views")) return indexPromise
      if (url.startsWith("/api/mailbox_entries/lookup")) {
        const response: MailboxEntryLookupResponse = { entries: [], next_cursor: null, has_more: false }
        return Promise.resolve(response)
      }
      return Promise.resolve(undefined)
    })

    await renderViewMailbox()

    // While loading: skeleton is on screen, "Organizing…" is not.
    await waitFor(() => {
      expect(document.querySelector('[data-testid="entry-list-skeleton"]')).not.toBeNull()
    })
    expect(document.body.textContent).not.toContain(ORGANIZING_TEXT)

    // Resolve with an already-organized (cached, non-generating) view — the pinned case.
    resolveIndex({
      all_views: [],
      active: ACTIVE_VIEW,
      cached_sections: [SECTION],
      cached_entry_ids: [],
      generating: false,
      has_goals_for_view: true,
      is_not_found: false,
      eligible_entry_count: null,
      considered_entry_count: null,
    } as MailboxViewIndexResponse)

    // Skeleton clears and the "Organizing…" text never appears for a pinned sort.
    await waitFor(() => {
      expect(document.querySelector('[data-testid="entry-list-skeleton"]')).toBeNull()
    })
    expect(document.body.textContent).not.toContain(ORGANIZING_TEXT)
  })
})
