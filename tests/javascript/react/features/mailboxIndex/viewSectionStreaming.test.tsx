import { act, cleanup, renderHook, waitFor } from "../../shared/testUtils"
import { queryClient } from "~/react/shared/queryClient"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useMailboxView } from "../../../../../app/javascript/react/features/mailboxIndex/hooks/useMailboxView"
import type {
  ActiveMailboxView,
  MailboxEntryListItem,
  MailboxEntryLookupResponse,
  MailboxViewIndexResponse,
  MailboxViewPayload,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"
import { ChannelEventAction, ChannelEventResource } from "../../../../../app/javascript/types/channels"

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

// Capture the channel handler so the test can fire payloads directly.
type ChannelHandler = (action: ChannelEventAction, data: Record<string, unknown>) => void
let capturedHandler: ChannelHandler | null = null

// The hook subscribes to two channels (MAILBOX_VIEW for sections, MAILBOX_SYNC
// for the live new-messages count). Capture only the MAILBOX_VIEW handler so the
// sync subscription doesn't clobber the section handler this test fires against.
vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (
    _target: { stream: string; params: Record<string, string>; extraParams?: Record<string, string> } | null,
    resource: unknown,
    handler: ChannelHandler
  ) => {
    if (resource === ChannelEventResource.MAILBOX_VIEW) capturedHandler = handler
  },
}))

vi.mock("../../../../../app/javascript/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"

const mockApiFetch = vi.mocked(apiFetch)

function makeEntry(id: string): MailboxEntryListItem {
  return {
    id,
    resource_type: "Chat",
    href: `/chats/${id}`,
    title: `Thread ${id}`,
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

// Cache miss path → useMailboxView enters the streaming state, where channel
// `section` payloads drive the sections array.
function mockStreamingShow() {
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
      const response: MailboxViewIndexResponse = {
        all_views: [],
        active: ACTIVE_VIEW,
        cached_sections: null,
        cached_entry_ids: [],
        generating: false,
        has_goals_for_view: true,
        is_not_found: false,
      }
      return Promise.resolve(response)
    }
    if (typeof url === "string" && url.startsWith("/api/mailbox_entries/lookup?ids=")) {
      const ids = Array.from(new URL(`https://x${url}`).searchParams.getAll("ids"))
      const response: MailboxEntryLookupResponse = { entries: ids.map(makeEntry), next_cursor: null, has_more: false }
      return Promise.resolve(response)
    }
    return Promise.resolve(undefined)
  })
}

async function fireChannelEvent(payload: MailboxViewPayload) {
  if (!capturedHandler) throw new Error("channel handler was not captured")
  await act(async () => {
    capturedHandler!(ChannelEventAction.UPDATE, payload as unknown as Record<string, unknown>)
  })
}

beforeEach(() => {
  queryClient.clear()
  mockApiFetch.mockReset()
  capturedHandler = null
})

afterEach(cleanup)

// Regression: the LLM stream can fill a later section's title before an
// earlier one, so the server (mailbox_views.py:120-129) may broadcast a higher
// section_index before a lower one. Prior to the fix in useMailboxView.ts, the
// sections updater did `[...prev]` which converts the resulting sparse holes
// to explicit `undefined` on the next push, causing
// `MailboxIndex.tsx:76` (flatMap on sections) to crash with
// "Cannot read properties of undefined (reading 'mailbox_entry_ids')".
// See Sentry DECIDE-90D.
describe("useMailboxView section streaming", () => {
  test("out-of-order section payloads do not produce undefined entries in sections", async () => {
    mockStreamingShow()

    const { result } = renderHook(() =>
      useMailboxView({ initialViewId: null, initialTemplate: "by_goals", initialGoalId: null, userId: "user-1" })
    )

    await waitFor(() => {
      expect(result.current.active).not.toBeNull()
      expect(result.current.loading).toBe(false)
      if (!capturedHandler) throw new Error("not subscribed yet")
    })

    // Section 1 arrives first (server gated section 0 because it had no title yet).
    await fireChannelEvent({
      type: "section",
      section_index: 1,
      section: { title: "Later", description: "", mailbox_entry_ids: ["entry-1"], goal: null },
    })

    // Length-2 sparse array: index 0 is a hole, index 1 holds the section.
    // flatMap/map on sparse arrays skips holes, so no consumer crashes.
    expect(result.current.sections.length).toBe(2)
    expect(0 in result.current.sections).toBe(false)
    expect(result.current.sections[1]).toEqual({
      title: "Later",
      description: "",
      mailbox_entry_ids: ["entry-1"],
      goal: null,
    })

    // The bug-trigger: a second section update that, pre-fix, used array spread
    // and converted the hole at index 0 into an explicit `undefined`. Verify
    // every slot is either a hole or a real section — never an `undefined` value.
    await fireChannelEvent({
      type: "section",
      section_index: 2,
      section: { title: "Even later", description: "", mailbox_entry_ids: ["entry-2"], goal: null },
    })

    expect(result.current.sections.length).toBe(3)
    expect(0 in result.current.sections).toBe(false)
    expect(result.current.sections[1]?.mailbox_entry_ids).toEqual(["entry-1"])
    expect(result.current.sections[2]?.mailbox_entry_ids).toEqual(["entry-2"])

    // Sections rendered by consumers via flatMap — must yield only the two
    // real sections, never trip on an `undefined` slot.
    const allIds = result.current.sections.flatMap(s => s.mailbox_entry_ids)
    expect(allIds).toEqual(["entry-1", "entry-2"])

    // Finally section 0 fills in the hole.
    await fireChannelEvent({
      type: "section",
      section_index: 0,
      section: { title: "First", description: "", mailbox_entry_ids: ["entry-0"], goal: null },
    })

    expect(result.current.sections.length).toBe(3)
    expect(result.current.sections.flatMap(s => s.mailbox_entry_ids)).toEqual(["entry-0", "entry-1", "entry-2"])
  })
})
