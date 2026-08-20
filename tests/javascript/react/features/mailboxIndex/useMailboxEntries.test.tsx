import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type {
  MailboxEntryListItem,
  MailboxEntryListResponse,
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
    target: { stream: string; params: Record<string, unknown>; extraParams?: Record<string, unknown> } | null,
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

import { QueryClientProvider } from "@tanstack/react-query"
import { renderHook as rtlRenderHook } from "@testing-library/react"
import type { ReactNode } from "react"

import { act, createTestQueryClient, renderHookWithClient, waitFor } from "../../shared/testUtils"
import { apiFetch } from "../../../../../app/javascript/react/shared/apiFetch"
import { useMailboxEntries } from "../../../../../app/javascript/react/features/mailboxIndex/hooks/useMailboxEntries"
import { OPTIMISTIC_GUARD_MS } from "../../../../../app/javascript/react/features/mailboxIndex/optimisticMerge"
import {
  type MailboxEntriesData,
  mailboxEntriesQueryKey,
} from "../../../../../app/javascript/react/shared/queries/mailboxEntries"
import type { QueryClient } from "@tanstack/react-query"

// The channel merge writes the cache synchronously; the observer re-render that
// updates result.current is deferred (React Query notifies on a later tick). Read
// the cache directly so these merge assertions are deterministic without waitFor
// (which for a "stays archived" case would pass on the pre-merge value).
function cachedEntry(client: QueryClient, id: string) {
  const data = client.getQueryData<MailboxEntriesData>(mailboxEntriesQueryKey("inbox", "newest"))
  return data?.pages.flatMap(page => page.entries).find(entry => entry.id === id)
}

const mockApiFetch = vi.mocked(apiFetch)

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

function makeResponse(
  entries: MailboxEntryListItem[],
  overrides: Partial<MailboxEntryListResponse> = {}
): MailboxEntryListResponse {
  return {
    entries,
    next_cursor: null,
    has_more: false,
    synced_at: "2026-05-01T00:00:00Z",
    ...overrides,
  }
}

beforeEach(() => {
  channelHandlers.clear()
  reconnectListeners.clear()
  mockApiFetch.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe("useMailboxEntries", () => {
  test("loads initial page and exposes visible entries", async () => {
    const entry = makeEntry()
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.visibleEntries).toHaveLength(1)
    expect(result.current.visibleEntries[0].id).toBe("e1")
  })

  test("paginates via loadMore using next_cursor", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeResponse([makeEntry({ id: "e1" })], { next_cursor: "cursor-2", has_more: true })
    )

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.hasMore).toBe(true)

    mockApiFetch.mockResolvedValueOnce(makeResponse([makeEntry({ id: "e2" })], { next_cursor: null, has_more: false }))
    act(() => {
      result.current.loadMore()
    })

    await waitFor(() => expect(result.current.entries).toHaveLength(2))
    expect(result.current.entries.map(e => e.id)).toEqual(["e1", "e2"])
    expect(result.current.hasMore).toBe(false)
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
    expect(mockApiFetch.mock.lastCall?.[0]).toContain("cursor=cursor-2")
  })

  // Pages are appended with setQueryData for exactly this reason: fetchNextPage
  // resolves to the pages it snapshotted when the fetch started, so an archive
  // performed while the sentinel was loading page 2 came back on screen a moment
  // later — the very thing that made archiving look broken after a soft navigation
  // into the inbox (the list re-pages, so a page is almost always in flight).
  test("an optimistic archive during an in-flight loadMore is not clobbered by the appended page", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeResponse([makeEntry({ id: "e1" })], { next_cursor: "cursor-2", has_more: true })
    )

    const { result, client } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    let resolvePage2: ((value: MailboxEntryListResponse) => void) | undefined
    const page2 = new Promise<MailboxEntryListResponse>(resolve => {
      resolvePage2 = resolve
    })
    mockApiFetch.mockReturnValueOnce(page2 as Promise<MailboxEntryListResponse>)
    act(() => {
      result.current.loadMore()
    })

    // Archive lands while page 2 is still in flight.
    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.archive("e1")
    })
    expect(cachedEntry(client, "e1")?.is_archived).toBe(true)

    await act(async () => {
      resolvePage2!(makeResponse([makeEntry({ id: "e2" })]))
      await page2
    })

    await waitFor(() => expect(result.current.entries).toHaveLength(2))
    expect(cachedEntry(client, "e1")?.is_archived).toBe(true)
    expect(result.current.visibleEntries.map(e => e.id)).toEqual(["e2"])
  })

  test("view/sort change loads the new key without blanking", async () => {
    mockApiFetch.mockResolvedValueOnce(makeResponse([makeEntry({ id: "inbox-1", title: "Inbox" })]))

    const client = createTestQueryClient()
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    )
    const { result, rerender } = rtlRenderHook(
      ({ view }: { view: "inbox" | "archived" }) => useMailboxEntries("user-1", view, "newest"),
      { wrapper, initialProps: { view: "inbox" as "inbox" | "archived" } }
    )
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.entries[0].title).toBe("Inbox")

    mockApiFetch.mockResolvedValueOnce(makeResponse([makeEntry({ id: "arch-1", title: "Archived" })]))
    act(() => {
      rerender({ view: "archived" })
    })

    // keepPreviousData keeps the prior list visible (no spinner) while the new key fetches.
    expect(result.current.loading).toBe(false)
    expect(result.current.entries[0].title).toBe("Inbox")

    await waitFor(() => expect(result.current.entries[0].title).toBe("Archived"))
    expect(result.current.loading).toBe(false)
  })

  test("optimistic archive updates entry, hides from inbox visibility", async () => {
    const entry = makeEntry()
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.archive("e1")
    })

    await waitFor(() => expect(result.current.entries[0].is_archived).toBe(true))
    // The inbox view filters out archived entries.
    expect(result.current.visibleEntries).toHaveLength(0)
  })

  test("unread view drops an entry once it is marked read", async () => {
    const entry = makeEntry() // is_unread: true by default
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "unread", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.visibleEntries).toHaveLength(1)

    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.markRead("e1")
    })

    await waitFor(() => expect(result.current.entries[0].is_unread).toBe(false))
    // The unread view filters out entries that have been read (mark_read fires no sync).
    expect(result.current.visibleEntries).toHaveLength(0)
  })

  test("optimistic archive rolls back and flashes on API error", async () => {
    const entry = makeEntry()
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockRejectedValueOnce(new Error("boom"))
    await act(async () => {
      await expect(result.current.mutations.archive("e1")).rejects.toThrow("boom")
    })

    // Rollback restores the pre-mutation state and clears the mutatedAt stamp.
    await waitFor(() => expect(result.current.entries[0].is_archived).toBe(false))
    expect(result.current.entries[0].mutatedAt).toBeUndefined()
  })

  // The recency-window merge rule against an optimistically-archived (mutatedAt-
  // stamped) local entry. The reconciliation no longer compares the browser stamp
  // to the server's synced_at (cross-clock) — a freshly-stamped local copy wins for
  // OPTIMISTIC_GUARD_MS regardless of the sync's synced_at, and only stale stamps
  // yield to the server. These cases pin both directions plus the #9130 races.
  test("channel-merge: an in-flight optimistic archive survives a concurrent sync with a far-future synced_at (#9130)", async () => {
    const entry = makeEntry({ is_archived: false })
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry], { synced_at: "2026-05-01T00:00:00Z" }))

    const { result, client } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.archive("e1")
    })
    await waitFor(() => expect(result.current.entries[0].is_archived).toBe(true))

    // A stale sync stamped after the optimistic action (synced_at far in the future
    // to prove it's NOT the clock comparison keeping the entry) must not un-archive
    // it: mutatedAt is recent, so the local optimistic copy wins.
    const handler = channelHandlers.get("mailbox_sync")!
    act(() => {
      handler("updated", {
        type: "entries",
        entries: [makeEntry({ is_archived: false })],
        synced_at: "2999-01-01T00:00:00Z",
      })
    })

    expect(cachedEntry(client, "e1")?.is_archived).toBe(true)
  })

  test("channel-merge: an older sync also keeps a within-window optimistic archive", async () => {
    const entry = makeEntry({ is_archived: false })
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry], { synced_at: "2026-05-01T00:00:00Z" }))

    const { result, client } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.archive("e1")
    })
    await waitFor(() => expect(result.current.entries[0].is_archived).toBe(true))

    const handler = channelHandlers.get("mailbox_sync")!
    act(() => {
      handler("updated", {
        type: "entries",
        entries: [makeEntry({ is_archived: false })],
        synced_at: "2000-01-01T00:00:00Z",
      })
    })

    expect(cachedEntry(client, "e1")?.is_archived).toBe(true)
  })

  test("channel-merge: rapid multi-archive — a single coalesced sync doesn't un-archive either entry (#9130)", async () => {
    mockApiFetch.mockResolvedValueOnce(
      makeResponse([makeEntry({ id: "e1" }), makeEntry({ id: "e2" })], { synced_at: "2026-05-01T00:00:00Z" })
    )

    const { result, client } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValue(undefined)
    await act(async () => {
      await result.current.mutations.archive("e1")
      await result.current.mutations.archive("e2")
    })
    await waitFor(() => expect(result.current.visibleEntries).toHaveLength(0))

    // One coalesced broadcast listing both entries as un-archived (far-future
    // synced_at) must leave both archived — both stamps are recent.
    const handler = channelHandlers.get("mailbox_sync")!
    act(() => {
      handler("updated", {
        type: "entries",
        entries: [makeEntry({ id: "e1", is_archived: false }), makeEntry({ id: "e2", is_archived: false })],
        synced_at: "2999-01-01T00:00:00Z",
      })
    })

    expect(cachedEntry(client, "e1")?.is_archived).toBe(true)
    expect(cachedEntry(client, "e2")?.is_archived).toBe(true)
  })

  test("channel-merge: a sync adopts the server copy once the optimistic stamp ages past the guard window", async () => {
    // Drive the merge clock with a Date.now spy (the fix reconciles against
    // Date.now() at merge time). Archive stamps mutatedAt = 1000; the merge then
    // sees a clock aged one tick past the window, so the stamp is stale.
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(1000)
    const entry = makeEntry({ is_archived: false })
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry], { synced_at: "2026-05-01T00:00:00Z" }))

    const { result, client } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.archive("e1")
    })
    await waitFor(() => expect(result.current.entries[0].is_archived).toBe(true))

    // Age the clock past the guard window, then a genuine new-activity sync (entry
    // un-archived) is adopted because the optimistic stamp is now stale.
    nowSpy.mockReturnValue(1000 + OPTIMISTIC_GUARD_MS + 1)
    const handler = channelHandlers.get("mailbox_sync")!
    act(() => {
      handler("updated", {
        type: "entries",
        entries: [makeEntry({ is_archived: false })],
        synced_at: "2099-01-01T00:00:00Z",
      })
    })

    expect(cachedEntry(client, "e1")?.is_archived).toBe(false)
  })

  test("first-page-only merge: pages 2+ are not reordered by a push", async () => {
    mockApiFetch.mockResolvedValueOnce(makeResponse([makeEntry({ id: "e1" })], { next_cursor: "c2", has_more: true }))
    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makeResponse([makeEntry({ id: "e2", title: "Page 2" })]))
    act(() => {
      result.current.loadMore()
    })
    await waitFor(() => expect(result.current.entries).toHaveLength(2))

    const handler = channelHandlers.get("mailbox_sync")!
    act(() => {
      handler("updated", {
        type: "entries",
        entries: [makeEntry({ id: "e1", title: "Page 1 updated" })],
        synced_at: "2099-01-01T00:00:00Z",
      })
    })

    // Page 1 entry updated by the push; the page-2 entry is untouched.
    await waitFor(() => expect(result.current.entries[0].title).toBe("Page 1 updated"))
    expect(result.current.entries[1].id).toBe("e2")
    expect(result.current.entries[1].title).toBe("Page 2")
  })

  test("reconnect refetches page 1 without flashing the spinner", async () => {
    const entry = makeEntry()
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(mockApiFetch).toHaveBeenCalledTimes(1)

    let resolveRefetch: ((value: MailboxEntryListResponse) => void) | undefined
    const refetchPromise = new Promise<MailboxEntryListResponse>(resolve => {
      resolveRefetch = resolve
    })
    mockApiFetch.mockReturnValueOnce(refetchPromise as Promise<MailboxEntryListResponse>)

    act(() => {
      reconnectListeners.forEach(cb => cb())
    })

    // Refetch is in flight but the prior list stays visible — loading must
    // remain false so EntryList doesn't switch to the spinner branch.
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
    expect(result.current.loading).toBe(false)
    expect(result.current.entries).toHaveLength(1)

    await act(async () => {
      resolveRefetch!(makeResponse([makeEntry({ title: "After reconnect" })]))
      await refetchPromise
    })

    expect(result.current.loading).toBe(false)
    await waitFor(() => expect(result.current.entries[0].title).toBe("After reconnect"))
  })

  test("reconnect preserves locally-mutated entries over server response", async () => {
    const entry = makeEntry({ is_archived: false })
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry], { synced_at: "2026-05-01T00:00:00Z" }))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    // Local optimistic archive — stamps mutatedAt = Date.now().
    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await result.current.mutations.archive("e1")
    })
    await waitFor(() => expect(result.current.entries[0].is_archived).toBe(true))

    // Reconnect refetch returns an older snapshot where the entry is still
    // un-archived. The mutatedAt > synced_at rule must keep the local copy.
    mockApiFetch.mockResolvedValueOnce(
      makeResponse([makeEntry({ is_archived: false })], { synced_at: "2026-04-30T00:00:00Z" })
    )

    act(() => {
      reconnectListeners.forEach(cb => cb())
    })
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(3))
    await waitFor(() => expect(result.current.entries[0].is_archived).toBe(true))
  })

  test("subscription re-arm (remount within gcTime) runs a merge-aware page-1 refetch", async () => {
    const client = createTestQueryClient()
    mockApiFetch.mockResolvedValueOnce(
      makeResponse([makeEntry({ is_archived: false })], { synced_at: "2026-05-01T00:00:00Z" })
    )

    const first = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"), client)
    await waitFor(() => expect(first.result.current.loading).toBe(false))

    // Optimistic archive before navigating away — must survive the re-arm.
    mockApiFetch.mockResolvedValueOnce(undefined)
    await act(async () => {
      await first.result.current.mutations.archive("e1")
    })
    await waitFor(() => expect(first.result.current.entries[0].is_archived).toBe(true))
    expect(mockApiFetch).toHaveBeenCalledTimes(2)

    // Navigate away (unmount); the cache survives (gcTime: Infinity).
    first.unmount()

    // Remount within gcTime: the cold useInfiniteQuery won't refetch, so the
    // re-arm catch-up fires a merge-aware page-1 refetch returning an older
    // snapshot. The in-flight optimistic archive must be preserved.
    mockApiFetch.mockResolvedValueOnce(
      makeResponse([makeEntry({ is_archived: false })], { synced_at: "2026-04-30T00:00:00Z" })
    )
    const second = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"), client)

    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(3))
    await waitFor(() => expect(second.result.current.entries[0].is_archived).toBe(true))
  })

  test("first mount does not double-fetch (cold cache skips the catch-up)", async () => {
    mockApiFetch.mockResolvedValueOnce(makeResponse([makeEntry()]))
    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))
    // Only the initial useInfiniteQuery fetch; the re-arm catch-up is skipped
    // because the cache was cold at mount.
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })

  test("channel message updates entries without issuing a refetch", async () => {
    const entry = makeEntry({ title: "Original" })
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(mockApiFetch).toHaveBeenCalledTimes(1)

    const handler = channelHandlers.get("mailbox_sync")!
    act(() => {
      handler("updated", {
        type: "entries",
        entries: [makeEntry({ title: "Updated by channel" })],
        synced_at: "2099-01-01T00:00:00Z",
      })
    })

    await waitFor(() => expect(result.current.entries[0].title).toBe("Updated by channel"))
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })

  test("resetToFirstPage refetch keeps loading false while existing entries are on screen", async () => {
    const entry = makeEntry({ id: "e1", title: "First" })
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    // Set up a never-resolving response so we can observe `loading` while the
    // refetch is in flight.
    let resolveRefetch: ((value: MailboxEntryListResponse) => void) | undefined
    const refetchPromise = new Promise<MailboxEntryListResponse>(resolve => {
      resolveRefetch = resolve
    })
    mockApiFetch.mockReturnValueOnce(refetchPromise as Promise<MailboxEntryListResponse>)

    act(() => {
      result.current.resetToFirstPage()
    })

    // While the request is in flight, we already have entries on screen — the
    // hook must not flip `loading` back to true.
    expect(result.current.loading).toBe(false)
    expect(result.current.entries).toHaveLength(1)

    await act(async () => {
      resolveRefetch!(makeResponse([makeEntry({ id: "e1", title: "Refreshed" })]))
      await refetchPromise
    })

    expect(result.current.loading).toBe(false)
    await waitFor(() => expect(result.current.entries[0].title).toBe("Refreshed"))
  })

  test("channel-merge accepts newer sync that wasn't locally mutated", async () => {
    const entry = makeEntry({ is_unread: true })
    mockApiFetch.mockResolvedValueOnce(makeResponse([entry]))

    const { result } = renderHookWithClient(() => useMailboxEntries("user-1", "inbox", "newest"))
    await waitFor(() => expect(result.current.loading).toBe(false))

    const handler = channelHandlers.get("mailbox_sync")!
    act(() => {
      handler("updated", {
        type: "entries",
        entries: [makeEntry({ is_unread: false })],
        synced_at: "2099-01-01T00:00:00Z",
      })
    })

    await waitFor(() => expect(result.current.entries[0].is_unread).toBe(false))
  })
})
