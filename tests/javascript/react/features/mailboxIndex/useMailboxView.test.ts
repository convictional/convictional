import { act, renderHook, waitFor } from "../../shared/testUtils"
import { queryClient } from "~/react/shared/queryClient"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type {
  MailboxEntryListItem,
  MailboxEntryLookupResponse,
  MailboxViewIndexResponse,
  MailboxViewSummary,
} from "../../../../../app/javascript/react/features/mailboxIndex/types"

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

const channelHandlers = new Map<string, (action: string, data: Record<string, unknown>) => void>()

vi.mock("../../../../../app/javascript/react/shared/hooks/useChannel", () => ({
  useChannel: (
    target: { stream: string } | null,
    resource: string,
    onMessage: (action: string, data: Record<string, unknown>) => void
  ) => {
    if (target) channelHandlers.set(resource, onMessage)
  },
}))

const reconnectListeners = new Set<() => void>()
const fakeClient = {
  on: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.add(cb)
  },
  off: (event: string, cb: () => void) => {
    if (event === "reconnected") reconnectListeners.delete(cb)
  },
}

vi.mock("../../../../../app/javascript/channels/client", () => ({
  getChannelsClient: () => fakeClient,
}))

vi.mock("../../../../../app/javascript/shared/flash", () => ({ showFlash: vi.fn() }))

import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { useMailboxView } from "../../../../../app/javascript/react/features/mailboxIndex/hooks/useMailboxView"
import { OPTIMISTIC_GUARD_MS } from "../../../../../app/javascript/react/features/mailboxIndex/optimisticMerge"
import {
  type MailboxViewIndexData,
  mailboxViewIndexFromResponse,
  mailboxViewIndexQueryKey,
} from "~/react/shared/queries/mailboxViewIndex"

const mockApiFetch = vi.mocked(apiFetch)

const VIEW_INDEX_KEY = mailboxViewIndexQueryKey({ viewId: "view-1", template: null, goalId: null })

// Fire a mailbox_view channel event at the hook's handler, registered by resource in the mocked
// useChannel above. Action is ignored by the handler, so any string does.
function fireViewEvent(data: Record<string, unknown>) {
  channelHandlers.get("mailbox_view")?.("updated", data)
}

// A view stranded at generating:true: the list rendered a partial (grouped sections or a ranked
// stream) then unmounted mid-generation, so `complete` fired to no one and the cache is frozen
// generating. hydratedFromPartial:false models the cold-miss stream (never a partial cache hit).
function strandedIndex(overrides: Partial<MailboxViewIndexData> = {}): MailboxViewIndexData {
  return {
    ...mailboxViewIndexFromResponse(makeIndexResponse()),
    sections: [{ title: "", description: "", mailbox_entry_ids: ["e1"], goal: null }],
    entryIds: ["e1"],
    generating: true,
    hadCachedSections: false,
    hydratedFromPartial: false,
    ...overrides,
  }
}

function makeEntry(overrides: Partial<MailboxEntryListItem> = {}): MailboxEntryListItem {
  return {
    id: "e1",
    resource_type: "Chat",
    href: "/chats/1",
    title: "Test",
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
      counterparty: null,
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

function makeIndexResponse(overrides: Partial<MailboxViewIndexResponse> = {}): MailboxViewIndexResponse {
  return {
    all_views: [],
    active: {
      kind: "view",
      id: "view-1",
      title: "My View",
      view_request: "everything urgent",
      channel_id: "view-1",
      requires_goals: false,
      // Ranked layout is the paginated path (one flat list matches the flat cached_entry_ids order).
      layout: "ranked",
    },
    cached_sections: [{ title: "Section 1", description: "", mailbox_entry_ids: ["e1"], goal: null }],
    cached_entry_ids: ["e1"],
    generating: false,
    has_goals_for_view: true,
    is_not_found: false,
    eligible_entry_count: null,
    considered_entry_count: null,
    ...overrides,
  }
}

function makeLookupResponse(entries: MailboxEntryListItem[]): MailboxEntryLookupResponse {
  return { entries, next_cursor: null, has_more: false }
}

function makeEntries(ids: string[]): MailboxEntryListItem[] {
  return ids.map(id => makeEntry({ id }))
}

// The `ids` query params in a lookup URL — proves exactly which entries a given fetch requested.
function lookupIds(url: string): string[] {
  return new URL(url, "http://localhost").searchParams.getAll("ids")
}

function pageShow(persisted: boolean) {
  window.dispatchEvent(Object.assign(new Event("pageshow"), { persisted }))
}

function renderView() {
  return renderHook(() =>
    useMailboxView({ initialViewId: "view-1", initialTemplate: null, initialGoalId: null, userId: "user-1" })
  )
}

// Mount loads the view (index) then its visible entries (lookup) — two apiFetch calls.
async function mountWithUnreadEntry() {
  mockApiFetch
    .mockResolvedValueOnce(makeIndexResponse())
    .mockResolvedValueOnce(makeLookupResponse([makeEntry({ id: "e1", is_unread: true })]))
  const view = renderView()
  await waitFor(() => expect(view.result.current.loading).toBe(false))
  expect(view.result.current.entriesById["e1"].is_unread).toBe(true)
  expect(mockApiFetch).toHaveBeenCalledTimes(2)
  return view
}

beforeEach(() => {
  queryClient.clear()
  channelHandlers.clear()
  reconnectListeners.clear()
  mockApiFetch.mockReset()
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe("useMailboxView", () => {
  test("cache hit hydrates only the first page, then loads more on demand", async () => {
    const ids = Array.from({ length: 40 }, (_, i) => `e${i + 1}`)
    mockApiFetch
      .mockResolvedValueOnce(
        makeIndexResponse({
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: ids, goal: null }],
          cached_entry_ids: ids,
        })
      )
      .mockResolvedValueOnce(makeLookupResponse(makeEntries(ids.slice(0, 30))))
    const { result } = renderView()
    await waitFor(() => expect(result.current.loading).toBe(false))

    // Returning to a 40-entry view must not block on one 40-entry lookup: only the first page
    // (30, matching the inbox default page size) is hydrated on mount, with more still to come. Assert
    // the exact ids so a wrong slice offset (e.g. the last 30, or ids 5..34) can't pass on count alone.
    expect(Object.keys(result.current.entriesById)).toHaveLength(30)
    expect(result.current.hasMoreEntries).toBe(true)
    expect(lookupIds(mockApiFetch.mock.calls[1][0] as string)).toEqual(ids.slice(0, 30))

    // Scrolling the sentinel into view hydrates the next page — the remaining 10 ids, nothing after.
    mockApiFetch.mockResolvedValueOnce(makeLookupResponse(makeEntries(ids.slice(30))))
    await act(async () => {
      await result.current.loadMoreEntries()
    })
    expect(Object.keys(result.current.entriesById)).toHaveLength(40)
    expect(result.current.hasMoreEntries).toBe(false)
    expect(lookupIds(mockApiFetch.mock.calls[2][0] as string)).toEqual(ids.slice(30))
  })

  test("a grouped view hydrates every entry in one lookup and shows no load-more sentinel", async () => {
    // Grouped sections index into the flat cached_entry_ids list, so a first-page-only hydration would
    // leave later sections rendering "Nothing in this category". Grouped views hydrate in full instead.
    const ids = Array.from({ length: 30 }, (_, i) => `e${i + 1}`)
    mockApiFetch
      .mockResolvedValueOnce(
        makeIndexResponse({
          active: { ...makeIndexResponse().active!, layout: "grouped" },
          cached_sections: [
            { title: "A", description: "", mailbox_entry_ids: ids.slice(0, 15), goal: null },
            { title: "B", description: "", mailbox_entry_ids: ids.slice(15), goal: null },
          ],
          cached_entry_ids: ids,
        })
      )
      .mockResolvedValueOnce(makeLookupResponse(makeEntries(ids)))
    const { result } = renderView()
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(Object.keys(result.current.entriesById)).toHaveLength(30)
    expect(result.current.hasMoreEntries).toBe(false)
    expect(lookupIds(mockApiFetch.mock.calls[1][0] as string)).toEqual(ids)
  })

  test("keeps the loading skeleton up until cache-hit entries hydrate, not just until the index lands", async () => {
    // Regression guard: loadView must await the entries-by-id lookup before clearing `loading`. If it
    // clears as soon as the index resolves (while the lookup is still in flight) the skeleton is torn
    // down early and MailboxViewSections renders every section empty ("Nothing in this category") for
    // the length of the lookup round-trip. A deferred lookup promise makes that gap observable — with a
    // real (near-instant mocked) lookup the two fetch phases collapse and the flash hides.
    let resolveLookup: ((value: MailboxEntryLookupResponse) => void) | undefined
    const lookup = new Promise<MailboxEntryLookupResponse>(resolve => {
      resolveLookup = resolve
    })
    mockApiFetch
      .mockResolvedValueOnce(makeIndexResponse())
      .mockReturnValueOnce(lookup as Promise<MailboxEntryLookupResponse>)
    const { result } = renderView()

    // The index resolved and the entry lookup was dispatched, but it hasn't settled — the rows aren't
    // ready, so `loading` must still be true and the store empty.
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))
    expect(result.current.loading).toBe(true)
    expect(result.current.entriesById).toEqual({})

    // Once the lookup lands, loading clears and the row is hydrated together (the bodies query
    // resolving re-renders on the next tick, so wait rather than assert synchronously).
    await act(async () => {
      resolveLookup!(makeLookupResponse([makeEntry({ id: "e1" })]))
      await lookup
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.entriesById["e1"]).toBeDefined()
  })

  test("loadMoreEntries retries the same page after a failed fetch", async () => {
    const ids = Array.from({ length: 40 }, (_, i) => `e${i + 1}`)
    mockApiFetch
      .mockResolvedValueOnce(
        makeIndexResponse({
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: ids, goal: null }],
          cached_entry_ids: ids,
        })
      )
      .mockResolvedValueOnce(makeLookupResponse(makeEntries(ids.slice(0, 30))))
    const { result } = renderView()
    await waitFor(() => expect(result.current.loading).toBe(false))

    // The next page fetch fails: the cursor must not advance and hasMoreEntries must stay true so the
    // sentinel can re-fire, rather than silently skipping ids 31..40 forever.
    mockApiFetch.mockRejectedValueOnce(new Error("boom"))
    await act(async () => {
      await result.current.loadMoreEntries()
    })
    expect(Object.keys(result.current.entriesById)).toHaveLength(30)
    expect(result.current.hasMoreEntries).toBe(true)

    // A retry of the same page succeeds and hydrates the remaining ids.
    mockApiFetch.mockResolvedValueOnce(makeLookupResponse(makeEntries(ids.slice(30))))
    await act(async () => {
      await result.current.loadMoreEntries()
    })
    expect(Object.keys(result.current.entriesById)).toHaveLength(40)
    expect(result.current.hasMoreEntries).toBe(false)
    expect(lookupIds(mockApiFetch.mock.calls[3][0] as string)).toEqual(ids.slice(30))
  })

  test("a page response landing after a view switch is dropped, not merged into the new view", async () => {
    // View A is a ranked cache hit whose first-page lookup is still in flight when the user switches
    // to view B. Switching views changes initialViewId, which re-runs the index load and bumps the
    // hydration request id — so A's still-pending page is now stale. When A's lookup finally resolves
    // it must not write A's entries into B's store, nor leave A's cursor/hasMoreEntries state behind.
    const idsA = Array.from({ length: 30 }, (_, i) => `a${i + 1}`)
    const idsB = ["b1", "b2"]
    const activeA = { ...makeIndexResponse().active!, id: "view-1", channel_id: "view-1" }
    const activeB = { ...makeIndexResponse().active!, id: "view-2", channel_id: "view-2" }
    let resolveA: ((value: MailboxEntryLookupResponse) => void) | undefined
    const firstPageA = new Promise<MailboxEntryLookupResponse>(resolve => {
      resolveA = resolve
    })
    mockApiFetch
      .mockResolvedValueOnce(
        makeIndexResponse({
          active: activeA,
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: idsA, goal: null }],
          cached_entry_ids: idsA,
        })
      )
      .mockReturnValueOnce(firstPageA as Promise<MailboxEntryLookupResponse>)
    const { result, rerender } = renderHook(props => useMailboxView(props), {
      initialProps: {
        initialViewId: "view-1",
        initialTemplate: null as string | null,
        initialGoalId: null as string | null,
        userId: "user-1",
      },
    })
    // A's index resolved but its entry lookup is still pending — hydration hasn't settled.
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))

    // Switch to view B: the initialViewId change re-runs the index load — a fresh index plus a
    // completed 2-entry lookup — and bumps the hydration request id past A's in-flight page.
    mockApiFetch
      .mockResolvedValueOnce(
        makeIndexResponse({
          active: activeB,
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: idsB, goal: null }],
          cached_entry_ids: idsB,
        })
      )
      .mockResolvedValueOnce(makeLookupResponse(makeEntries(idsB)))
    rerender({ initialViewId: "view-2", initialTemplate: null, initialGoalId: null, userId: "user-1" })

    await waitFor(() => expect(result.current.entriesById["b1"]).toBeDefined())
    expect(Object.keys(result.current.entriesById).sort()).toEqual(idsB)

    // A's page resolves last with A's entries — it must be dropped, leaving B's store untouched.
    await act(async () => {
      resolveA!(makeLookupResponse(makeEntries(idsA)))
      await firstPageA
    })
    expect(Object.keys(result.current.entriesById).sort()).toEqual(idsB)
    // A's cursor/hasMore state must not have leaked in: B is a 2-entry view, fully hydrated.
    expect(result.current.hasMoreEntries).toBe(false)
  })

  test("bfcache refresh re-pulls only hydrated entries, not the full cached set", async () => {
    const ids = Array.from({ length: 40 }, (_, i) => `e${i + 1}`)
    mockApiFetch
      .mockResolvedValueOnce(
        makeIndexResponse({
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: ids, goal: null }],
          cached_entry_ids: ids,
        })
      )
      .mockResolvedValueOnce(makeLookupResponse(makeEntries(ids.slice(0, 30))))
    const { result } = renderView()
    await waitFor(() => expect(result.current.loading).toBe(false))

    // Only the first 30 are on screen, so a bfcache restore refreshes those 30 — never all 40.
    mockApiFetch.mockResolvedValueOnce(makeLookupResponse(makeEntries(ids.slice(0, 30))))
    act(() => {
      pageShow(true)
    })
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(3))
    expect(lookupIds(mockApiFetch.mock.calls[2][0] as string)).toEqual(ids.slice(0, 30))
  })

  test("websocket reconnect re-pulls visible entries' read state", async () => {
    const { result } = await mountWithUnreadEntry()

    // While disconnected the entry was opened (marked read server-side). The reconnect
    // refetch should pull the fresh state and flip the row to read.
    mockApiFetch.mockResolvedValueOnce(makeLookupResponse([makeEntry({ id: "e1", is_unread: false })]))
    act(() => {
      reconnectListeners.forEach(cb => cb())
    })

    await waitFor(() => expect(result.current.entriesById["e1"].is_unread).toBe(false))
    expect(mockApiFetch).toHaveBeenCalledTimes(3)
  })

  test("bfcache restore refreshes; a non-persisted pageshow does not", async () => {
    const { result } = await mountWithUnreadEntry()

    // A normal forward navigation (not a bfcache restore) must not trigger a refetch.
    act(() => {
      pageShow(false)
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(2)

    // Browser back via bfcache hands the island back stale — refresh read state.
    mockApiFetch.mockResolvedValueOnce(makeLookupResponse([makeEntry({ id: "e1", is_unread: false })]))
    act(() => {
      pageShow(true)
    })

    await waitFor(() => expect(result.current.entriesById["e1"].is_unread).toBe(false))
    expect(mockApiFetch).toHaveBeenCalledTimes(3)
  })

  test("deleting a view you aren't viewing drops it from the list without reloading", async () => {
    const active: MailboxViewSummary = {
      id: "view-1",
      title: "Active",
      view_request: "x",
      layout: "ranked",
      created_at: "2026-06-01T00:00:00Z",
    }
    const other: MailboxViewSummary = { ...active, id: "sort-2", title: "Other" }
    mockApiFetch
      .mockResolvedValueOnce(makeIndexResponse({ all_views: [active, other] }))
      .mockResolvedValueOnce(makeLookupResponse([makeEntry()]))
    const { result } = renderView()
    await waitFor(() => expect(result.current.loading).toBe(false))

    const originalLocation = window.location
    Object.defineProperty(window, "location", { value: { href: "/current" }, writable: true, configurable: true })
    try {
      await act(async () => {
        await result.current.deleteView("sort-2")
      })
      // allViews is sourced from the shared query cache; the observer re-renders on the next tick.
      await waitFor(() => expect(result.current.allViews.map(v => v.id)).toEqual(["view-1"]))
      expect(window.location.href).toBe("/current")
    } finally {
      Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true })
    }
  })

  test("deleting the view currently on screen falls back to the inbox", async () => {
    mockApiFetch
      .mockResolvedValueOnce(makeIndexResponse({ all_views: [] }))
      .mockResolvedValueOnce(makeLookupResponse([makeEntry()]))
    const { result } = renderView()
    await waitFor(() => expect(result.current.loading).toBe(false))

    const originalLocation = window.location
    Object.defineProperty(window, "location", { value: { href: "/current" }, writable: true, configurable: true })
    try {
      // The mounted view (active id "view-1") is the one being deleted.
      await act(async () => {
        await result.current.deleteView("view-1")
      })
      expect(window.location.href).toBe("/")
    } finally {
      Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true })
    }
  })

  test("refreshView posts to the URL-encoded identifier and refetches the index without reloading", async () => {
    mockApiFetch.mockResolvedValueOnce(makeIndexResponse()).mockResolvedValueOnce(makeLookupResponse([makeEntry()]))
    const { result } = renderView()
    await waitFor(() => expect(result.current.loading).toBe(false))

    const reload = vi.fn()
    const originalLocation = window.location
    Object.defineProperty(window, "location", { value: { reload }, writable: true, configurable: true })
    try {
      // A built-in by_goal sort: the colons in the identifier must be encoded so the path reaches
      // the server intact. The endpoint only drops the server cache, so the client has to refetch
      // the index itself to restart generation — a document reload would strand the realm (#8744).
      mockApiFetch.mockResolvedValueOnce(null as unknown as MailboxEntryLookupResponse)
      mockApiFetch.mockResolvedValueOnce(makeIndexResponse({ cached_sections: [], generating: true }))
      await act(async () => {
        await result.current.refreshView("template:by_goal:11111111-1111-1111-1111-111111111111")
      })
      expect(mockApiFetch).toHaveBeenCalledWith(
        "/api/mailbox_views/template%3Aby_goal%3A11111111-1111-1111-1111-111111111111/refresh",
        { method: "POST" }
      )
      await waitFor(() => {
        expect(
          mockApiFetch.mock.calls.filter(([url]) => typeof url === "string" && url.startsWith("/api/mailbox_views?"))
        ).toHaveLength(2)
      })
      expect(result.current.isGenerating).toBe(true)
      expect(reload).not.toHaveBeenCalled()
    } finally {
      Object.defineProperty(window, "location", { value: originalLocation, writable: true, configurable: true })
    }
  })

  test("refresh preserves an entry whose optimistic mutation is recent at merge time", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1000)
    const { result } = await mountWithUnreadEntry()

    // A refresh starts but its response is still in flight.
    let resolveRefresh: ((value: MailboxEntryLookupResponse) => void) | undefined
    const refreshPromise = new Promise<MailboxEntryLookupResponse>(resolve => {
      resolveRefresh = resolve
    })
    mockApiFetch.mockReturnValueOnce(refreshPromise as Promise<MailboxEntryLookupResponse>)
    act(() => {
      reconnectListeners.forEach(cb => cb())
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(3)

    // After the refresh started, the user marks the entry read (mutatedAt = 2000).
    nowSpy.mockReturnValue(2000)
    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.markRead("e1")
    })
    // The optimistic patch lands in the shared bodies cache; the observer re-renders on the next tick.
    await waitFor(() => expect(result.current.entriesById["e1"].is_unread).toBe(false))

    // The stale refresh response (entry still unread) lands last. The merge keys on
    // Date.now() at merge time (2000): the stamp is recent (2000 - 2000 = 0 < the
    // guard window), so the local optimistic mark-read wins and is not clobbered.
    await act(async () => {
      resolveRefresh!(makeLookupResponse([makeEntry({ id: "e1", is_unread: true })]))
      await refreshPromise
    })
    expect(result.current.entriesById["e1"].is_unread).toBe(false)
  })

  test("refresh adopts the server copy once the optimistic stamp ages past the guard window", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1000)
    const { result } = await mountWithUnreadEntry()

    let resolveRefresh: ((value: MailboxEntryLookupResponse) => void) | undefined
    const refreshPromise = new Promise<MailboxEntryLookupResponse>(resolve => {
      resolveRefresh = resolve
    })
    mockApiFetch.mockReturnValueOnce(refreshPromise as Promise<MailboxEntryLookupResponse>)
    act(() => {
      reconnectListeners.forEach(cb => cb())
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(3)

    // Mark read (mutatedAt = 2000).
    nowSpy.mockReturnValue(2000)
    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.markRead("e1")
    })
    await waitFor(() => expect(result.current.entriesById["e1"].is_unread).toBe(false))

    // Advance the clock past the guard window before the stale lookup resolves. At
    // merge time the stamp is too old (2000 + guard + 1 - 2000 > guard), so the
    // window is bounded: the server copy wins and the entry reverts to unread.
    nowSpy.mockReturnValue(2000 + OPTIMISTIC_GUARD_MS + 1)
    await act(async () => {
      resolveRefresh!(makeLookupResponse([makeEntry({ id: "e1", is_unread: true })]))
      await refreshPromise
    })
    await waitFor(() => expect(result.current.entriesById["e1"].is_unread).toBe(true))
  })

  test("a superseded refresh response is dropped (request-id guard)", async () => {
    const { result } = await mountWithUnreadEntry()

    // Two refreshes overlap (bfcache restore landing alongside a WS reconnect).
    let resolveFirst: ((value: MailboxEntryLookupResponse) => void) | undefined
    let resolveSecond: ((value: MailboxEntryLookupResponse) => void) | undefined
    const first = new Promise<MailboxEntryLookupResponse>(resolve => {
      resolveFirst = resolve
    })
    const second = new Promise<MailboxEntryLookupResponse>(resolve => {
      resolveSecond = resolve
    })
    mockApiFetch
      .mockReturnValueOnce(first as Promise<MailboxEntryLookupResponse>)
      .mockReturnValueOnce(second as Promise<MailboxEntryLookupResponse>)

    act(() => {
      reconnectListeners.forEach(cb => cb()) // request 1
      pageShow(true) // request 2 (latest)
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(4)

    // The latest request settles first with the fresh (read) state (observer re-renders next tick).
    await act(async () => {
      resolveSecond!(makeLookupResponse([makeEntry({ id: "e1", is_unread: false })]))
      await second
    })
    await waitFor(() => expect(result.current.entriesById["e1"].is_unread).toBe(false))

    // The superseded request settles later with stale (unread) state — must be ignored.
    await act(async () => {
      resolveFirst!(makeLookupResponse([makeEntry({ id: "e1", is_unread: true })]))
      await first
    })
    expect(result.current.entriesById["e1"].is_unread).toBe(false)
  })

  test("recovers a ranked view stranded at generating:true when the server re-announces complete", async () => {
    // The list streamed a ranked partial (just e1) then unmounted mid-generation; generation's own
    // `complete` fired to no one and the cache is frozen at generating:true with only e1. On
    // resubscribe the server re-announces `complete`; the hook must reconcile to the authoritative
    // cached order (e1, e2) rather than sitting on "Organizing…" — and must NOT clobber the order to
    // empty (the ranked-refetch trap the coordinated fix exists to avoid).
    queryClient.setQueryData(VIEW_INDEX_KEY, strandedIndex({ layout: "ranked" }))
    mockApiFetch.mockImplementation(async (url: unknown) => {
      const u = String(url)
      if (u.includes("/api/mailbox_entries/lookup")) return makeLookupResponse(makeEntries(["e1", "e2"]))
      if (u.startsWith("/api/mailbox_views"))
        return makeIndexResponse({
          cached_sections: [{ title: "", description: "", mailbox_entry_ids: ["e1", "e2"], goal: null }],
          cached_entry_ids: ["e1", "e2"],
          generating: false,
        })
      throw new Error(`unexpected fetch: ${u}`)
    })

    const { result } = renderView()
    expect(result.current.isGenerating).toBe(true)

    await act(async () => {
      fireViewEvent({ type: "complete" })
    })

    await waitFor(() => expect(result.current.isGenerating).toBe(false))
    expect(mockApiFetch.mock.calls.some(([url]) => String(url).startsWith("/api/mailbox_views"))).toBe(true)
    expect(result.current.sections[0].mailbox_entry_ids).toEqual(["e1", "e2"])
    expect(result.current.entriesById["e1"]).toBeDefined()
    expect(result.current.entriesById["e2"]).toBeDefined()
  })

  test("recovers a grouped view stranded at generating:true on complete", async () => {
    queryClient.setQueryData(VIEW_INDEX_KEY, strandedIndex({ layout: "grouped" }))
    mockApiFetch.mockImplementation(async (url: unknown) => {
      const u = String(url)
      if (u.includes("/api/mailbox_entries/lookup")) return makeLookupResponse(makeEntries(["e1", "e2", "e3"]))
      if (u.startsWith("/api/mailbox_views"))
        return makeIndexResponse({
          active: { ...makeIndexResponse().active!, layout: "grouped" },
          cached_sections: [
            { title: "A", description: "", mailbox_entry_ids: ["e1", "e2"], goal: null },
            { title: "B", description: "", mailbox_entry_ids: ["e3"], goal: null },
          ],
          cached_entry_ids: ["e1", "e2", "e3"],
          generating: false,
        })
      throw new Error(`unexpected fetch: ${u}`)
    })

    const { result } = renderView()
    expect(result.current.isGenerating).toBe(true)

    await act(async () => {
      fireViewEvent({ type: "complete" })
    })

    await waitFor(() => expect(result.current.isGenerating).toBe(false))
    // Grouped hydrates every id in one lookup, so both settled sections render in full.
    expect(result.current.sections.map(s => s.mailbox_entry_ids)).toEqual([["e1", "e2"], ["e3"]])
    expect(Object.keys(result.current.entriesById).sort()).toEqual(["e1", "e2", "e3"])
  })

  test("a settled view does not refetch on a redundant complete", async () => {
    // The server re-announces `complete` on every resubscribe to a settled cache. A view that's
    // already settled (generating:false) must treat it as a no-op — no index refetch, no churn.
    const { result } = await mountWithUnreadEntry()
    expect(result.current.isGenerating).toBe(false)
    const callsBefore = mockApiFetch.mock.calls.length

    await act(async () => {
      fireViewEvent({ type: "complete" })
    })

    expect(result.current.isGenerating).toBe(false)
    expect(mockApiFetch.mock.calls.length).toBe(callsBefore)
  })
})
