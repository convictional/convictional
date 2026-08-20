import { act, cleanup, renderHook, waitFor } from "../../shared/testUtils"
import { queryClient } from "~/react/shared/queryClient"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import { useMailboxView } from "../../../../../app/javascript/react/features/mailboxIndex/hooks/useMailboxView"
import type {
  ActiveMailboxView,
  MailboxEntryListItem,
  MailboxEntryLookupResponse,
  MailboxSyncPayload,
  MailboxViewIndexResponse,
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

// Record subscriptions keyed by resource, but only when there's a live topic —
// matching the guard in useMailboxEntries/useInboxProgress so a captured entry
// means an active subscription. The hook subscribes to both MAILBOX_VIEW
// (sections) and MAILBOX_SYNC (live count); the tests assert against the latter.
type ChannelHandler = (action: ChannelEventAction, data: Record<string, unknown>) => void
const channelSubscriptions = new Map<string, { onMessage: ChannelHandler; params: Record<string, string> }>()

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (
    target: { stream: string; params: Record<string, string>; extraParams?: Record<string, string> } | null,
    resource: string,
    onMessage: ChannelHandler
  ) => {
    if (target) channelSubscriptions.set(resource, { onMessage, params: target.extraParams ?? {} })
  },
}))

vi.mock("../../../../../app/javascript/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"

const mockApiFetch = vi.mocked(apiFetch)

const USER_ID = "user-1"

const ACTIVE_VIEW: ActiveMailboxView = {
  kind: "template",
  id: "template:by_goals",
  title: "By goals",
  view_request: null,
  channel_id: "template:by_goals",
  requires_goals: false,
}

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

// Cache-hit path: the show endpoint returns cached sections. The live-count sync subscription is
// driven off an active view, not any client-held cache state.
function mockCachedShow(overrides?: Partial<MailboxViewIndexResponse>) {
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
      const response: MailboxViewIndexResponse = {
        all_views: [],
        active: ACTIVE_VIEW,
        cached_sections: [{ title: "First", description: "", mailbox_entry_ids: ["entry-0"], goal: null }],
        cached_entry_ids: ["entry-0"],
        generating: false,
        has_goals_for_view: true,
        is_not_found: false,
        eligible_entry_count: 10,
        considered_entry_count: 5,
        ...overrides,
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

async function fireSyncEvent(payload: MailboxSyncPayload) {
  const onMessage = channelSubscriptions.get(ChannelEventResource.MAILBOX_SYNC)?.onMessage
  if (!onMessage) throw new Error("sync handler was not captured")
  await act(async () => {
    onMessage(ChannelEventAction.UPDATE, payload as unknown as Record<string, unknown>)
  })
}

beforeEach(() => {
  queryClient.clear()
  mockApiFetch.mockReset()
  channelSubscriptions.clear()
})

afterEach(cleanup)

describe("useMailboxView live new-messages count", () => {
  test("a new_messages sync payload updates newMessagesCount", async () => {
    mockCachedShow()

    const { result } = renderHook(() =>
      useMailboxView({ initialViewId: null, initialTemplate: "by_goals", userId: USER_ID })
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
      if (!channelSubscriptions.has(ChannelEventResource.MAILBOX_SYNC)) throw new Error("not subscribed yet")
    })

    expect(result.current.newMessagesCount).toBe(0)

    await fireSyncEvent({ type: "new_messages", view_id: ACTIVE_VIEW.channel_id, count: 3 })
    expect(result.current.newMessagesCount).toBe(3)

    // Live: a later push replaces the count rather than accumulating.
    await fireSyncEvent({ type: "new_messages", view_id: ACTIVE_VIEW.channel_id, count: 7 })
    expect(result.current.newMessagesCount).toBe(7)
  })

  test("subscribes to the sync topic as soon as the view is active, even on a cache miss", async () => {
    // Cache miss → no cached order yet. The subscription still mounts: the server counts against its
    // own cache record (returning nothing until one exists), so the banner needs no client baseline.
    mockCachedShow({ cached_sections: null, cached_entry_ids: [] })

    const { result } = renderHook(() =>
      useMailboxView({ initialViewId: null, initialTemplate: "by_goals", userId: USER_ID })
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
      if (!channelSubscriptions.has(ChannelEventResource.MAILBOX_SYNC)) throw new Error("not subscribed yet")
    })

    expect(channelSubscriptions.has(ChannelEventResource.MAILBOX_SYNC)).toBe(true)
  })

  test("the sync subscription targets the user topic in count-only mode, carrying no cache state", async () => {
    mockCachedShow()

    const { result } = renderHook(() =>
      useMailboxView({ initialViewId: null, initialTemplate: "by_goals", userId: USER_ID })
    )

    await waitFor(() => {
      expect(result.current.loading).toBe(false)
      if (!channelSubscriptions.has(ChannelEventResource.MAILBOX_SYNC)) throw new Error("not subscribed yet")
    })

    const sync = channelSubscriptions.get(ChannelEventResource.MAILBOX_SYNC)!
    // `mailbox_view_mode` routes the server's mailbox_sync handler to its count-only branch.
    expect(sync.params.mailbox_view_mode).toBe("true")
    expect(sync.params.view_id).toBe(ACTIVE_VIEW.channel_id)
    // No cache state rides as a subscribe param — the server counts against its own cache record.
    expect(sync.params).not.toHaveProperty("cached_at")
    expect(sync.params).not.toHaveProperty("cached_entry_ids")
  })
})
