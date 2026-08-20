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

type ChannelHandler = (action: ChannelEventAction, data: Record<string, unknown>) => void
type ChannelTarget = { stream: string; params: Record<string, string>; extraParams?: Record<string, string> } | null
let capturedHandler: ChannelHandler | null = null
// Capture the mailbox_sync subscription (which drives the "N new" banner) to assert it mounts for an
// active view and carries only the view identity — no client-held cache state.
let syncTarget: ChannelTarget = null
let syncHandler: ChannelHandler | null = null

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (_target: ChannelTarget, resource: unknown, handler: ChannelHandler) => {
    if (resource === ChannelEventResource.MAILBOX_VIEW) capturedHandler = handler
    if (resource === ChannelEventResource.MAILBOX_SYNC) {
      syncTarget = _target
      syncHandler = handler
    }
  },
}))

vi.mock("../../../../../app/javascript/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"

const mockApiFetch = vi.mocked(apiFetch)

function makeEntry(id: string, lastActivityAt = "2026-05-01T00:00:00Z"): MailboxEntryListItem {
  return {
    id,
    resource_type: "Chat",
    href: `/chats/${id}`,
    title: `Thread ${id}`,
    preview: null,
    sender_display: null,
    last_activity_at: lastActivityAt,
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

const RANKED_ACTIVE: ActiveMailboxView = {
  kind: "template",
  id: "template:priority",
  title: "Priority",
  view_request: null,
  channel_id: "template:priority",
  requires_goals: false,
  layout: "ranked",
}

function mockStreamingShow() {
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
      const response: MailboxViewIndexResponse = {
        all_views: [],
        active: RANKED_ACTIVE,
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
      const response: MailboxEntryLookupResponse = {
        entries: ids.map(id => makeEntry(id)),
        next_cursor: null,
        has_more: false,
      }
      return Promise.resolve(response)
    }
    return Promise.resolve(undefined)
  })
}

function mockCacheHitShow(orderedIds: string[]) {
  mockApiFetch.mockImplementation((url: string) => {
    if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
      const response: MailboxViewIndexResponse = {
        all_views: [],
        active: RANKED_ACTIVE,
        // A ranked cache hit is one untitled section already in the server's authoritative order.
        cached_sections: [{ title: "", description: "", mailbox_entry_ids: orderedIds, goal: null }],
        cached_entry_ids: orderedIds,
        generating: false,
        has_goals_for_view: true,
        is_not_found: false,
      }
      return Promise.resolve(response)
    }
    if (typeof url === "string" && url.startsWith("/api/mailbox_entries/lookup?ids=")) {
      const ids = Array.from(new URL(`https://x${url}`).searchParams.getAll("ids"))
      return Promise.resolve({ entries: ids.map(id => makeEntry(id)), next_cursor: null, has_more: false })
    }
    return Promise.resolve(undefined)
  })
}

async function fire(payload: MailboxViewPayload) {
  if (!capturedHandler) throw new Error("channel handler was not captured")
  await act(async () => {
    capturedHandler!(ChannelEventAction.UPDATE, payload as unknown as Record<string, unknown>)
  })
}

function rankedIds(result: { current: { sections: { mailbox_entry_ids: string[] }[] } }): string[] {
  return result.current.sections[0]?.mailbox_entry_ids ?? []
}

function renderRanked() {
  return renderHook(() =>
    useMailboxView({ initialViewId: null, initialTemplate: "priority", initialGoalId: null, userId: "user-1" })
  )
}

beforeEach(() => {
  queryClient.clear()
  mockApiFetch.mockReset()
  capturedHandler = null
  syncTarget = null
  syncHandler = null
})

afterEach(cleanup)

describe("useMailboxView ranked streaming", () => {
  test("entry_scored deltas build one flat section ordered by score desc", async () => {
    mockStreamingShow()
    const { result } = renderRanked()
    await waitFor(() => {
      expect(result.current.active?.layout).toBe("ranked")
      if (!capturedHandler) throw new Error("not subscribed yet")
    })

    await fire({ type: "entry_scored", entry_id: "e1", score: 0.5, rank: 0 })
    await fire({ type: "entry_scored", entry_id: "e2", score: 0.9, rank: 1 })
    await fire({ type: "entry_scored", entry_id: "e3", score: 0.7, rank: 2 })

    // Highest score first; a single ranked section (no per-score section frames).
    await waitFor(() => expect(rankedIds(result)).toEqual(["e2", "e3", "e1"]))
    expect(result.current.sections.length).toBe(1)
    expect(result.current.sections[0].title).toBe("")

    // The batched sentinel tail (candidates the LLM never scored) sorts last, in rank order.
    await fire({ type: "entries_scored", entry_ids: ["e4", "e5"], ranks: [3, 4], score: -1 })
    await waitFor(() => expect(rankedIds(result)).toEqual(["e2", "e3", "e1", "e4", "e5"]))
  })

  test("equal scores break the tie by the server's recency rank, stable across hydration", async () => {
    // Rank order is the OPPOSITE of id order: if the client ever tie-broke by id (the old
    // pre-hydration fallback), it would render ["e1", "e2"] then swap. With the rank ordinal
    // streamed alongside the score, the order is correct immediately and never reshuffles.
    mockStreamingShow()
    const { result } = renderRanked()
    await waitFor(() => {
      expect(result.current.active?.layout).toBe("ranked")
      if (!capturedHandler) throw new Error("not subscribed yet")
    })

    // e2 has the lower (more recent) rank, so despite equal scores it ranks ahead of e1.
    await fire({ type: "entry_scored", entry_id: "e1", score: 0.5, rank: 1 })
    await fire({ type: "entry_scored", entry_id: "e2", score: 0.5, rank: 0 })

    // Correct order holds before any entry has hydrated...
    expect(rankedIds(result)).toEqual(["e2", "e1"])

    // ...and stays put once /lookup resolves and entriesById fills in (the regression: a re-sort
    // here used to swap equal-score rows from id order to last_activity_at order).
    await waitFor(() => {
      expect(result.current.entriesById.e1).toBeDefined()
      expect(result.current.entriesById.e2).toBeDefined()
    })
    expect(rankedIds(result)).toEqual(["e2", "e1"])
  })

  test("a cache hit renders the whole ranked list in one shot (no deltas)", async () => {
    mockCacheHitShow(["b", "a", "c"])
    const { result } = renderRanked()

    await waitFor(() => expect(result.current.loading).toBe(false))
    // Server order preserved verbatim — the client does not re-sort a cached ranked section.
    expect(rankedIds(result)).toEqual(["b", "a", "c"])
    expect(result.current.isGenerating).toBe(false)
  })

  test("the banner subscribes for an active view without echoing cache state, and live counts arrive", async () => {
    mockStreamingShow()
    const { result } = renderRanked()
    await waitFor(() => {
      expect(result.current.isGenerating).toBe(true)
      if (!capturedHandler) throw new Error("not subscribed yet")
    })

    // The "N new" banner subscription is live as soon as the view is active — even mid-generation,
    // before any cache exists — and names only the view. No cached_at/cached_entry_ids round-trip;
    // the server counts against its own cache record.
    expect(syncTarget?.extraParams).toEqual({ mailbox_view_mode: "true", view_id: "template:priority" })

    // Live new-mail counts (server-computed) reach the banner.
    await act(async () => {
      syncHandler?.(ChannelEventAction.UPDATE, { type: "new_messages", count: 3 })
    })
    expect(result.current.newMessagesCount).toBe(3)
  })
})

describe("useMailboxView generation watchdog", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
  afterEach(() => vi.useRealTimers())

  test("a stalled generation (no events) surfaces an error instead of spinning forever", async () => {
    mockStreamingShow()
    const { result } = renderRanked()
    await waitFor(() => expect(result.current.isGenerating).toBe(true))

    // No section/delta/complete ever arrives (the bug: a generation that died server-side without
    // broadcasting). Advancing past the stall window must give up rather than spin indefinitely.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })

    expect(result.current.isGenerating).toBe(false)
    expect(result.current.errorMessage).toMatch(/taking longer than expected/i)
  })

  test("a progress event re-arms the watchdog so a slow-but-streaming generation does not error", async () => {
    mockStreamingShow()
    const { result } = renderRanked()
    await waitFor(() => expect(result.current.isGenerating).toBe(true))

    // Almost stall, then a delta arrives and resets the window; a second near-stall must NOT error.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29_000)
    })
    await fire({ type: "entry_scored", entry_id: "e1", score: 0.5, rank: 0 })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(29_000)
    })
    expect(result.current.errorMessage).toBeNull()
    expect(result.current.isGenerating).toBe(true)

    // Now let it genuinely stall past the window from the last event.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })
    expect(result.current.errorMessage).toMatch(/taking longer than expected/i)
  })

  test("a completed generation clears the watchdog (no late error)", async () => {
    mockStreamingShow()
    const { result } = renderRanked()
    await waitFor(() => expect(result.current.isGenerating).toBe(true))

    await fire({ type: "entry_scored", entry_id: "e1", score: 0.5, rank: 0 })
    await fire({ type: "complete" })
    await waitFor(() => expect(result.current.isGenerating).toBe(false))

    // Well past the stall window — a cleared watchdog must not retroactively flag an error.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000)
    })
    expect(result.current.errorMessage).toBeNull()
  })

  test("a never-resolving generating partial surfaces the watchdog error", async () => {
    // A stale generating=true partial (e.g. a failed generation whose cache lingers and which the
    // subscribe path never refreshes, since it only re-announces `complete` for a *settled* cache).
    // With no live stream and no `complete` ever arriving, the watchdog trips and surfaces the error
    // instead of spinning on "Organizing…" forever.
    mockApiFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
        const response: MailboxViewIndexResponse = {
          all_views: [],
          active: RANKED_ACTIVE,
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: ["a", "b"], goal: null }],
          cached_entry_ids: ["a", "b"],
          generating: true,
          has_goals_for_view: true,
          is_not_found: false,
        }
        return Promise.resolve(response)
      }
      if (typeof url === "string" && url.startsWith("/api/mailbox_entries/lookup?ids=")) {
        const ids = Array.from(new URL(`https://x${url}`).searchParams.getAll("ids"))
        return Promise.resolve({ entries: ids.map(id => makeEntry(id)), next_cursor: null, has_more: false })
      }
      return Promise.resolve(undefined)
    })

    const { result } = renderRanked()
    await waitFor(() => expect(result.current.isGenerating).toBe(true))
    // Entries render from the partial; spinner is up.
    expect(rankedIds(result)).toEqual(["a", "b"])

    // No stream and no `complete` ever arrive — the stall window elapses and the watchdog errors.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000)
    })
    await waitFor(() => expect(result.current.isGenerating).toBe(false))
    expect(result.current.errorMessage).toMatch(/taking longer than expected/i)
  })
})

describe("useMailboxView partial cache (refresh mid-sort)", () => {
  // A refresh during generation now returns a partial cache (generating=true): the entries render
  // immediately instead of blanking, and the view stays in the generating state until `complete`.
  function mockPartialThenFinalShow(partialIds: string[], finalIds: string[]) {
    let showCalls = 0
    mockApiFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
        showCalls += 1
        // First load is the partial; the reconcile after `complete` gets the authoritative final.
        const generating = showCalls === 1
        const ids = generating ? partialIds : finalIds
        const response: MailboxViewIndexResponse = {
          all_views: [],
          active: RANKED_ACTIVE,
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: ids, goal: null }],
          cached_entry_ids: ids,
          generating,
          has_goals_for_view: true,
          is_not_found: false,
        }
        return Promise.resolve(response)
      }
      if (typeof url === "string" && url.startsWith("/api/mailbox_entries/lookup?ids=")) {
        const ids = Array.from(new URL(`https://x${url}`).searchParams.getAll("ids"))
        return Promise.resolve({ entries: ids.map(id => makeEntry(id)), next_cursor: null, has_more: false })
      }
      return Promise.resolve(undefined)
    })
  }

  test("renders the partial order immediately and keeps the generating spinner up", async () => {
    mockPartialThenFinalShow(["a", "b", "c"], ["c", "b", "a"])
    const { result } = renderRanked()

    await waitFor(() => expect(result.current.loading).toBe(false))
    // Entries are on screen (not blank) even though generation hasn't finished.
    expect(rankedIds(result)).toEqual(["a", "b", "c"])
    expect(result.current.isGenerating).toBe(true)
  })

  test("a sparse live delta does not shrink the partial; complete reconciles to the final order", async () => {
    mockPartialThenFinalShow(["a", "b", "c"], ["c", "b", "a"])
    const { result } = renderRanked()
    await waitFor(() => {
      expect(rankedIds(result)).toEqual(["a", "b", "c"])
      if (!capturedHandler) throw new Error("not subscribed yet")
    })

    // A single post-refresh score must NOT rebuild the list down to just that id — the server's
    // partial (all candidates) stays put until the authoritative order arrives.
    await fire({ type: "entry_scored", entry_id: "c", score: 0.99 })
    expect(rankedIds(result)).toEqual(["a", "b", "c"])

    // Completion triggers a quiet refetch that loads the final ordering and drops the spinner.
    await fire({ type: "complete" })
    await waitFor(() => {
      expect(rankedIds(result)).toEqual(["c", "b", "a"])
      expect(result.current.isGenerating).toBe(false)
    })
  })
})

describe("useMailboxView partial cache (refresh mid-sort)", () => {
  // A refresh during generation now returns a partial cache (generating=true): the entries render
  // immediately instead of blanking, and the view stays in the generating state until `complete`.
  function mockPartialThenFinalShow(partialIds: string[], finalIds: string[]) {
    let showCalls = 0
    mockApiFetch.mockImplementation((url: string) => {
      if (typeof url === "string" && url.startsWith("/api/mailbox_views")) {
        showCalls += 1
        // First load is the partial; the reconcile after `complete` gets the authoritative final.
        const generating = showCalls === 1
        const ids = generating ? partialIds : finalIds
        const response: MailboxViewIndexResponse = {
          all_views: [],
          active: RANKED_ACTIVE,
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: ids, goal: null }],
          cached_entry_ids: ids,
          generating,
          has_goals_for_view: true,
          is_not_found: false,
        }
        return Promise.resolve(response)
      }
      if (typeof url === "string" && url.startsWith("/api/mailbox_entries/lookup?ids=")) {
        const ids = Array.from(new URL(`https://x${url}`).searchParams.getAll("ids"))
        return Promise.resolve({ entries: ids.map(id => makeEntry(id)), next_cursor: null, has_more: false })
      }
      return Promise.resolve(undefined)
    })
  }

  test("renders the partial order immediately and keeps the generating spinner up", async () => {
    mockPartialThenFinalShow(["a", "b", "c"], ["c", "b", "a"])
    const { result } = renderRanked()

    await waitFor(() => expect(result.current.loading).toBe(false))
    // Entries are on screen (not blank) even though generation hasn't finished.
    expect(rankedIds(result)).toEqual(["a", "b", "c"])
    expect(result.current.isGenerating).toBe(true)
  })

  test("a sparse live delta does not shrink the partial; complete reconciles to the final order", async () => {
    mockPartialThenFinalShow(["a", "b", "c"], ["c", "b", "a"])
    const { result } = renderRanked()
    await waitFor(() => {
      expect(rankedIds(result)).toEqual(["a", "b", "c"])
      if (!capturedHandler) throw new Error("not subscribed yet")
    })

    // A single post-refresh score must NOT rebuild the list down to just that id — the server's
    // partial (all candidates) stays put until the authoritative order arrives. (rank is ignored on
    // this path, but the payload type requires it.)
    await fire({ type: "entry_scored", entry_id: "c", score: 0.99, rank: 0 })
    expect(rankedIds(result)).toEqual(["a", "b", "c"])

    // Completion triggers a quiet refetch that loads the final ordering and drops the spinner.
    await fire({ type: "complete" })
    await waitFor(() => {
      expect(rankedIds(result)).toEqual(["c", "b", "a"])
      expect(result.current.isGenerating).toBe(false)
    })
  })
})
