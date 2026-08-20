import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { createElement, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  type MailboxEntryNavigation,
  useMailboxEntryNavigation,
} from "~/react/composites/MailboxActionBar/useMailboxEntryNavigation"
import { neighborHref, parseMailboxNavigationContext } from "~/react/shared/mailboxNavigation"
import { type MailboxViewEntriesData, mailboxViewEntriesQueryKey } from "~/react/shared/queries/mailboxViewEntries"
import {
  GENERATION_STALL_MS,
  type MailboxViewIdentifier,
  type MailboxViewIndexData,
  mailboxViewIndexQueryKey,
} from "~/react/shared/queries/mailboxViewIndex"
import type { MailboxEntry, MailboxEntryListResponse, ViewSection } from "~/react/shared/types"

const apiFetch = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({ apiFetch }))

// The focus branch reads the current user (channel subscribe param) and installs a
// channel subscription; neither needs a real provider for these cache-driven tests.
const channelHandlers = vi.hoisted(() => [] as ((action: string, data: Record<string, unknown>) => void)[])
// Tracks the latest subscription target so tests can assert we stay subscribed (target
// non-null) across a regeneration. Mirrors the real useChannel: a null target is "not
// subscribed", so we only register a handler when the target is present.
const lastChannelTarget = vi.hoisted(() => ({ current: null as unknown }))
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: { id: "u1" }, clientConfig: null, loading: false, error: null }),
}))
vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: (target: unknown, _resource: unknown, onMessage: (a: string, d: Record<string, unknown>) => void) => {
    lastChannelTarget.current = target
    if (target !== null) channelHandlers.push(onMessage)
  },
}))

function entry(id: string, href: string, { archived = false }: { archived?: boolean } = {}) {
  return {
    id,
    resource_type: "Post" as const,
    href,
    title: null,
    preview: null,
    sender_display: null,
    last_activity_at: "2026-07-20T00:00:00Z",
    is_unread: false,
    is_archived: archived,
    is_snoozed: false,
    snoozed_until: null,
    is_assigned_to_me: false,
    is_shared: false,
    email: null,
    chat: null,
    post: null,
    goal: null,
  }
}

function page(entries: ReturnType<typeof entry>[], nextCursor: string | null): MailboxEntryListResponse {
  return { entries, has_more: nextCursor !== null, next_cursor: nextCursor, synced_at: "2026-07-20T00:00:00Z" }
}

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
}

function setShowUrl(search: string) {
  window.history.pushState({}, "", `/posts/abc${search}`)
}

// `visible` flips true from the parsed URL context alone, before the list query
// resolves — so callers wait on a neighbor href (the signal that data landed).
async function renderNav(
  entryId: string,
  settled: (nav: MailboxEntryNavigation) => boolean
): Promise<{ current: () => MailboxEntryNavigation }> {
  const { result } = renderHook(() => useMailboxEntryNavigation({ mailboxEntryId: entryId }), { wrapper: wrapper() })
  await waitFor(() => expect(settled(result.current)).toBe(true))
  return { current: () => result.current }
}

const IDENTIFIER: MailboxViewIdentifier = { viewId: "v1", template: null, goalId: null }
const FOCUS_RETURN = "%2F%3Fmailbox_view_id%3Dv1" // /?mailbox_view_id=v1

function section(title: string, ids: string[]): ViewSection {
  return { title, description: "", mailbox_entry_ids: ids, goal: null }
}

function indexData(overrides: Partial<MailboxViewIndexData>): MailboxViewIndexData {
  return {
    active: {
      kind: "view",
      id: "v1",
      title: "V",
      view_request: null,
      channel_id: "v1",
      requires_goals: false,
      layout: "grouped",
    },
    allViews: [],
    sections: [],
    entryIds: [],
    generating: false,
    hadCachedSections: true,
    hydratedFromPartial: false,
    layout: "grouped",
    isNotFound: false,
    hasGoalsForView: false,
    eligibleEntryCount: null,
    consideredEntryCount: null,
    ...overrides,
  }
}

function byId(...ids: string[]): Record<string, MailboxEntry> {
  const map: Record<string, MailboxEntry> = {}
  for (const id of ids) map[id] = entry(id, `/posts/${id}?mailbox_entry_id=${id}`) as MailboxEntry
  return map
}

// Seed a warm focus-mode cache (index + entry bodies) into a fresh client, exactly
// as a boosted navigation from the list would leave it, then render against it.
function renderFocusNav(entryId: string, index: MailboxViewIndexData, bodies: Record<string, MailboxEntry>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  client.setQueryData(mailboxViewIndexQueryKey(IDENTIFIER), index)
  client.setQueryData<MailboxViewEntriesData>(mailboxViewEntriesQueryKey(IDENTIFIER), {
    byId: bodies,
    hydratedCount: Object.keys(bodies).length,
  })
  const wrap = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)
  const { result } = renderHook(() => useMailboxEntryNavigation({ mailboxEntryId: entryId }), { wrapper: wrap })
  return { current: () => result.current, client }
}

beforeEach(() => {
  apiFetch.mockReset()
  channelHandlers.length = 0
  lastChannelTarget.current = null
})

afterEach(() => {
  window.history.pushState({}, "", "/")
})

describe("parseMailboxNavigationContext", () => {
  it("resolves the main mailbox return_to to inbox + sort", () => {
    expect(parseMailboxNavigationContext("?return_to=%2F")).toEqual({
      kind: "inbox",
      view: "inbox",
      sort: "newest",
      returnTo: "/",
    })
    expect(parseMailboxNavigationContext("?return_to=%2F%3Fsort%3Doldest")).toEqual({
      kind: "inbox",
      view: "inbox",
      sort: "oldest",
      returnTo: "/?sort=oldest",
    })
  })

  it("resolves focus-mode return_to to a view/template identifier", () => {
    expect(parseMailboxNavigationContext("?return_to=%2F%3Fmailbox_view_id%3Dv1")).toEqual({
      kind: "focus",
      identifier: { viewId: "v1", template: null, goalId: null },
      returnTo: "/?mailbox_view_id=v1",
    })
    expect(parseMailboxNavigationContext("?return_to=%2F%3Fmailbox_view_template%3Dby_goal%26goal_id%3Dg9")).toEqual({
      kind: "focus",
      identifier: { viewId: null, template: "by_goal", goalId: "g9" },
      returnTo: "/?mailbox_view_template=by_goal&goal_id=g9",
    })
  })

  it("returns null for other lists, missing, off-site, or unknown return_to", () => {
    expect(parseMailboxNavigationContext("")).toBeNull()
    // Only the main mailbox (/) and focus modes are navigable — the other lists are not.
    expect(parseMailboxNavigationContext("?return_to=%2Funread%3Fsort%3Doldest")).toBeNull()
    expect(parseMailboxNavigationContext("?return_to=%2Farchived")).toBeNull()
    expect(parseMailboxNavigationContext("?return_to=%2Fsent")).toBeNull()
    expect(parseMailboxNavigationContext("?return_to=%2Fassigned_to_me")).toBeNull()
    expect(parseMailboxNavigationContext("?return_to=%2F%2Fevil.com")).toBeNull()
    expect(parseMailboxNavigationContext("?return_to=%2Fposts%2F123")).toBeNull()
  })
})

describe("neighborHref", () => {
  it("stamps the list return_to while preserving the entry's own params", () => {
    expect(neighborHref("/posts/9?mailbox_entry_id=e9", "/unread?sort=oldest")).toBe(
      "/posts/9?mailbox_entry_id=e9&return_to=%2Funread%3Fsort%3Doldest"
    )
  })

  it("leaves dead links untouched", () => {
    expect(neighborHref("#", "/")).toBe("#")
  })
})

describe("useMailboxEntryNavigation — main inbox", () => {
  it("is hidden when the entry wasn't opened from a mailbox list", () => {
    setShowUrl("?mailbox_entry_id=e1")
    const { result } = renderHook(() => useMailboxEntryNavigation({ mailboxEntryId: "e1" }), { wrapper: wrapper() })
    expect(result.current.visible).toBe(false)
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it("computes prev/next neighbors for a middle entry", async () => {
    apiFetch.mockResolvedValue(page([entry("e1", "/posts/1"), entry("e2", "/posts/2"), entry("e3", "/posts/3")], null))
    setShowUrl("?mailbox_entry_id=e2&return_to=%2F")
    const nav = await renderNav("e2", n => n.nextHref !== null)
    expect(nav.current().prevHref).toBe("/posts/1?return_to=%2F")
    expect(nav.current().nextHref).toBe("/posts/3?return_to=%2F")
    expect(nav.current().loadingNext).toBe(false)
    expect(nav.current().positionLabel).toBeNull()
  })

  it("disables the arrow with no neighbor at each end", async () => {
    apiFetch.mockResolvedValue(page([entry("e1", "/posts/1"), entry("e2", "/posts/2")], null))

    setShowUrl("?mailbox_entry_id=e1&return_to=%2F")
    const first = await renderNav("e1", n => n.nextHref !== null)
    expect(first.current().prevHref).toBeNull()
    expect(first.current().nextHref).toBe("/posts/2?return_to=%2F")

    setShowUrl("?mailbox_entry_id=e2&return_to=%2F")
    const last = await renderNav("e2", n => n.prevHref !== null)
    expect(last.current().nextHref).toBeNull()
    expect(last.current().prevHref).toBe("/posts/1?return_to=%2F")
  })

  it("skips an archived entry when walking the inbox", async () => {
    apiFetch.mockResolvedValue(
      page([entry("e1", "/posts/1"), entry("e2", "/posts/2", { archived: true }), entry("e3", "/posts/3")], null)
    )
    setShowUrl("?mailbox_entry_id=e1&return_to=%2F")
    const nav = await renderNav("e1", n => n.nextHref !== null)
    // e2 is archived ⇒ the inbox skips it, so e1's next is e3.
    expect(nav.current().nextHref).toBe("/posts/3?return_to=%2F")
    expect(nav.current().prevHref).toBeNull()
  })

  it("fetches the next page to resolve a trailing neighbor at the loaded boundary", async () => {
    apiFetch.mockImplementation((url: string) => {
      const cursor = new URL(url, "http://local").searchParams.get("cursor")
      return Promise.resolve(
        cursor === "c1"
          ? page([entry("e3", "/posts/3")], null)
          : page([entry("e1", "/posts/1"), entry("e2", "/posts/2")], "c1")
      )
    })
    setShowUrl("?mailbox_entry_id=e2&return_to=%2F")
    const nav = await renderNav("e2", n => n.nextHref !== null)
    expect(nav.current().nextHref).toBe("/posts/3?return_to=%2F")
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })

  // Every page has more and none contains the target — the unbounded cold-load case.
  // `land` decides when each page resolves, the axis that matters for the walk: a page
  // that resolves before the render which started it commits interleaves differently
  // from one that lands on a later macrotask.
  async function expectPagingStopsAtCap(land: (p: MailboxEntryListResponse) => Promise<MailboxEntryListResponse>) {
    apiFetch.mockImplementation((url: string) => {
      const cursor = new URL(url, "http://local").searchParams.get("cursor")
      const n = cursor ? Number(cursor) : 0
      return land(page([entry(`e${n}`, `/posts/${n}`)], String(n + 1)))
    })
    setShowUrl("?mailbox_entry_id=missing&return_to=%2F")
    const { result } = renderHook(() => useMailboxEntryNavigation({ mailboxEntryId: "missing" }), {
      wrapper: wrapper(),
    })
    // Page 1 (initial) + 4 look-ahead pages (cap = 5 loaded pages), then it halts.
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(5))
    // Give any errant extra fetch a chance to fire, then confirm the cap held.
    await new Promise(resolve => setTimeout(resolve, 20))
    expect(apiFetch).toHaveBeenCalledTimes(5)
    expect(result.current.prevHref).toBeNull()
    expect(result.current.nextHref).toBeNull()
  }

  it("stops paging at the look-ahead cap when a cold-linked entry never appears", async () => {
    await expectPagingStopsAtCap(p => new Promise(resolve => setTimeout(() => resolve(p), 0)))
  })

  it("keeps walking when each page resolves before its own render commits", async () => {
    // A page served from a warm HTTP cache resolves before React commits the render that
    // started it, so the walk has to step off the page count landing in the cache: an
    // in-flight flag that flips on and back off within a single render pass leaves the
    // effect's dependencies unchanged, stalling the walk a page short with dead arrows.
    await expectPagingStopsAtCap(p => Promise.resolve(p))
  })
})

describe("useMailboxEntryNavigation — focus modes", () => {
  it("walks a grouped view across section boundaries with a section-title label", () => {
    setShowUrl(`?mailbox_entry_id=e3&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "grouped",
      sections: [section("Blockers", ["e1", "e2", "e3"]), section("FYI", ["e4", "e5"])],
      entryIds: ["e1", "e2", "e3", "e4", "e5"],
    })
    const nav = renderFocusNav("e3", index, byId("e1", "e2", "e3", "e4", "e5"))
    expect(nav.current().visible).toBe(true)
    expect(nav.current().prevHref).toBe(`/posts/e2?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
    // Next crosses into the FYI section.
    expect(nav.current().nextHref).toBe(`/posts/e4?mailbox_entry_id=e4&return_to=${FOCUS_RETURN}`)
    expect(nav.current().positionLabel).toEqual({ name: "Blockers", position: 3, total: 3 })
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it("relabels to the new section after crossing the boundary", () => {
    setShowUrl(`?mailbox_entry_id=e4&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "grouped",
      sections: [section("Blockers", ["e1", "e2", "e3"]), section("FYI", ["e4", "e5"])],
      entryIds: ["e1", "e2", "e3", "e4", "e5"],
    })
    const nav = renderFocusNav("e4", index, byId("e3", "e4", "e5"))
    expect(nav.current().positionLabel).toEqual({ name: "FYI", position: 1, total: 2 })
  })

  it("labels a ranked sort with its name and position within the whole sort", () => {
    setShowUrl(`?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "ranked",
      active: {
        kind: "view",
        id: "v1",
        title: "By priority",
        view_request: null,
        channel_id: "v1",
        requires_goals: false,
        layout: "ranked",
      },
      sections: [section("", ["e1", "e2", "e3", "e4"])],
      entryIds: ["e1", "e2", "e3", "e4"],
    })
    const nav = renderFocusNav("e2", index, byId("e1", "e2", "e3"))
    expect(nav.current().positionLabel).toEqual({ name: "By priority", position: 2, total: 4 })
    expect(nav.current().prevHref).toBe(`/posts/e1?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    expect(nav.current().nextHref).toBe(`/posts/e3?mailbox_entry_id=e3&return_to=${FOCUS_RETURN}`)
  })

  it("excludes an archived entry from a ranked sort's position, total, and walk", () => {
    setShowUrl(`?mailbox_entry_id=e3&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "ranked",
      sections: [section("", ["e1", "e2", "e3", "e4"])],
      entryIds: ["e1", "e2", "e3", "e4"],
    })
    // e2 was archived from the list; its body carries is_archived, so it drops from the
    // count and the walk just as it does from the rendered list.
    const bodies = {
      ...byId("e1", "e3", "e4"),
      e2: entry("e2", "/posts/e2?mailbox_entry_id=e2", { archived: true }) as MailboxEntry,
    }
    const nav = renderFocusNav("e3", index, bodies)
    expect(nav.current().positionLabel).toEqual({ name: "V", position: 2, total: 3 })
    // Prev skips the archived e2, landing on e1.
    expect(nav.current().prevHref).toBe(`/posts/e1?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    expect(nav.current().nextHref).toBe(`/posts/e4?mailbox_entry_id=e4&return_to=${FOCUS_RETURN}`)
  })

  it("excludes an archived entry from a grouped section's position and total", () => {
    setShowUrl(`?mailbox_entry_id=e3&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "grouped",
      sections: [section("Blockers", ["e1", "e2", "e3"]), section("FYI", ["e4", "e5"])],
      entryIds: ["e1", "e2", "e3", "e4", "e5"],
    })
    const bodies = {
      ...byId("e1", "e3", "e4", "e5"),
      e2: entry("e2", "/posts/e2?mailbox_entry_id=e2", { archived: true }) as MailboxEntry,
    }
    const nav = renderFocusNav("e3", index, bodies)
    // Blockers held [e1, e2, e3]; with e2 archived, e3 is 2 of 2.
    expect(nav.current().positionLabel).toEqual({ name: "Blockers", position: 2, total: 2 })
  })

  it("disables the boundary arrow at the ends of the view", () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({ layout: "ranked", sections: [section("", ["e1", "e2"])], entryIds: ["e1", "e2"] })
    const nav = renderFocusNav("e1", index, byId("e1", "e2"))
    expect(nav.current().prevHref).toBeNull()
    expect(nav.current().nextHref).toBe(`/posts/e2?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
  })

  it("stays hidden on a cold miss (view never generated)", () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({ hadCachedSections: false, sections: [], entryIds: [] })
    const nav = renderFocusNav("e1", index, {})
    expect(nav.current().visible).toBe(false)
    expect(apiFetch).not.toHaveBeenCalled()
  })

  it("surfaces arrows for a cold-miss view that streamed to completion (never set hadCachedSections)", () => {
    // A view generated live from a cold miss clears `generating` on `complete` but never sets
    // hadCachedSections — the list doesn't re-read the index after a live stream. Navigating in
    // (boosted, sharing the warm cache) must still walk the settled, populated order.
    setShowUrl(`?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      hadCachedSections: false,
      generating: false,
      layout: "grouped",
      sections: [section("Blockers", ["e1", "e2", "e3"])],
      entryIds: ["e1", "e2", "e3"],
    })
    const nav = renderFocusNav("e2", index, byId("e1", "e2", "e3"))
    expect(nav.current().visible).toBe(true)
    expect(nav.current().prevHref).toBe(`/posts/e1?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    expect(nav.current().nextHref).toBe(`/posts/e3?mailbox_entry_id=e3&return_to=${FOCUS_RETURN}`)
    expect(nav.current().positionLabel).toEqual({ name: "Blockers", position: 2, total: 3 })
  })

  it("is visible but generating on a mid-generation partial", () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "ranked",
      generating: true,
      hydratedFromPartial: true,
      sections: [section("", ["e1", "e2"])],
      entryIds: ["e1", "e2"],
    })
    const nav = renderFocusNav("e1", index, byId("e1", "e2"))
    expect(nav.current().visible).toBe(true)
    expect(nav.current().generating).toBe(true)
  })

  it("refetches the authoritative index when generation completes", () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "ranked",
      generating: true,
      hydratedFromPartial: true,
      sections: [section("", ["e1", "e2"])],
      entryIds: ["e1", "e2"],
    })
    const nav = renderFocusNav("e1", index, byId("e1", "e2"))
    const invalidate = vi.spyOn(nav.client, "invalidateQueries")
    // The (mocked) channel handler was registered while generating; a `complete`
    // event must trigger a refetch of the index cache.
    channelHandlers.forEach(handler => handler("updated", { type: "complete" }))
    expect(invalidate).toHaveBeenCalledWith({ queryKey: mailboxViewIndexQueryKey(IDENTIFIER) })
  })

  it("drops the current entry from the cached order when archived", () => {
    setShowUrl(`?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "grouped",
      sections: [section("Blockers", ["e1", "e2", "e3"])],
      entryIds: ["e1", "e2", "e3"],
    })
    const nav = renderFocusNav("e2", index, byId("e1", "e2", "e3"))
    nav.current().markCurrentArchived()
    const updated = nav.client.getQueryData<MailboxViewIndexData>(mailboxViewIndexQueryKey(IDENTIFIER))
    expect(updated?.entryIds).toEqual(["e1", "e3"])
    expect(updated?.sections[0].mailbox_entry_ids).toEqual(["e1", "e3"])
  })

  it("offers no navigation target while generating so triage falls back to the source list", () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "ranked",
      generating: true,
      hydratedFromPartial: true,
      sections: [section("", ["e1", "e2"])],
      entryIds: ["e1", "e2"],
    })
    // e2's body is cached, so without the generating guard nextHref would resolve.
    const nav = renderFocusNav("e1", index, byId("e1", "e2"))
    expect(nav.current().generating).toBe(true)
    expect(nav.current().prevHref).toBeNull()
    expect(nav.current().nextHref).toBeNull()
  })

  it("hides when the current entry is not in the cached order", () => {
    setShowUrl(`?mailbox_entry_id=eX&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "grouped",
      sections: [section("Blockers", ["e1", "e2"])],
      entryIds: ["e1", "e2"],
    })
    const nav = renderFocusNav("eX", index, byId("e1", "e2"))
    expect(nav.current().visible).toBe(false)
  })

  it("stops the next spinner once the neighbor lookup settles even if it returns nothing", async () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({ layout: "ranked", sections: [section("", ["e1", "e2"])], entryIds: ["e1", "e2"] })
    // e2's body isn't cached and the lookup resolves without it (filtered out server-side).
    apiFetch.mockResolvedValue({ entries: [] })
    const nav = renderFocusNav("e1", index, byId("e1"))
    expect(nav.current().loadingNext).toBe(true)
    await waitFor(() => expect(nav.current().loadingNext).toBe(false))
    expect(nav.current().nextHref).toBeNull()
  })

  it("merges fetched neighbor bodies into the shared entries cache for reuse", async () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({ layout: "ranked", sections: [section("", ["e1", "e2"])], entryIds: ["e1", "e2"] })
    apiFetch.mockResolvedValue({ entries: [entry("e2", "/posts/e2?mailbox_entry_id=e2")] })
    const nav = renderFocusNav("e1", index, byId("e1"))
    await waitFor(() => expect(nav.current().nextHref).toBe(`/posts/e2?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`))
    const shared = nav.client.getQueryData<MailboxViewEntriesData>(mailboxViewEntriesQueryKey(IDENTIFIER))
    expect(shared?.byId.e2).toBeDefined()
    // Cursor untouched — a read-through, not a page load.
    expect(shared?.hydratedCount).toBe(1)
  })

  it("resolveNextHref hydrates a not-yet-loaded neighbor so the archive advance doesn't bounce to the list", async () => {
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({ layout: "ranked", sections: [section("", ["e1", "e2"])], entryIds: ["e1", "e2"] })
    // e2's body is not cached; archiving must still resolve its href rather than fall back to the list.
    apiFetch.mockResolvedValue({ entries: [entry("e2", "/posts/e2?mailbox_entry_id=e2")] })
    const nav = renderFocusNav("e1", index, byId("e1"))
    await expect(nav.current().resolveNextHref()).resolves.toBe(
      `/posts/e2?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`
    )
  })
})

function indexResponse(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    all_views: [],
    active: {
      kind: "view",
      id: "v1",
      title: "V",
      view_request: null,
      channel_id: "v1",
      requires_goals: false,
      layout: "ranked",
    },
    cached_sections: [section("", ["e1", "e2"])],
    cached_entry_ids: ["e1", "e2"],
    generating: false,
    has_goals_for_view: false,
    is_not_found: false,
    eligible_entry_count: null,
    considered_entry_count: null,
    ...overrides,
  }
}

describe("useMailboxEntryNavigation — focus generation recovery", () => {
  it("surfaces arrows after navigating into a still-generating cold-miss view once complete arrives", async () => {
    // Opened an entry from a view generating from scratch: no cached order yet (hadCachedSections
    // false), so the arrows start hidden. The hook subscribes because a partial is streaming; when
    // `complete` arrives (the server re-announces it on (re)subscribe) it refetches the settled
    // index and the arrows appear.
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const index = indexData({
      layout: "ranked",
      generating: true,
      hadCachedSections: false,
      sections: [section("", ["e1", "e2"])],
      entryIds: ["e1", "e2"],
    })
    apiFetch.mockResolvedValue(indexResponse())
    const nav = renderFocusNav("e1", index, byId("e1", "e2"))
    expect(nav.current().visible).toBe(false)

    await act(async () => {
      channelHandlers.at(-1)?.("updated", { type: "complete" })
    })

    await waitFor(() => expect(nav.current().visible).toBe(true))
    expect(nav.current().generating).toBe(false)
    expect(nav.current().nextHref).toBe(`/posts/e2?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
  })

  it("stays subscribed through a regeneration so a later complete still recovers the arrows", async () => {
    // A settled view starts regenerating: the refetch returns a cold miss (ranked caches nothing
    // mid-generation), which empties the order and hides the arrows. The subscription must persist
    // (not drop with the emptied order) so the new generation's `complete` still reaches us.
    setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
    const settled = indexData({ layout: "ranked", sections: [section("", ["e1", "e2"])], entryIds: ["e1", "e2"] })
    let indexResp: Record<string, unknown> = indexResponse({
      cached_sections: null,
      cached_entry_ids: [],
      generating: true,
    })
    apiFetch.mockImplementation((url: string) =>
      Promise.resolve(url.includes("/api/mailbox_views") ? indexResp : { entries: [] })
    )
    const nav = renderFocusNav("e1", settled, byId("e1", "e2"))
    expect(nav.current().visible).toBe(true)

    await act(async () => {
      channelHandlers.at(-1)?.("updated", { type: "regenerating", attempt: 1 })
    })
    await waitFor(() => expect(nav.current().visible).toBe(false))
    // The clobbered order looks like a cold direct load, but the latch keeps us subscribed.
    expect(lastChannelTarget.current).not.toBeNull()

    indexResp = indexResponse()
    await act(async () => {
      channelHandlers.at(-1)?.("updated", { type: "complete" })
    })
    await waitFor(() => expect(nav.current().visible).toBe(true))
    expect(nav.current().nextHref).toBe(`/posts/e2?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
  })

  describe("watchdog backstop", () => {
    beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }))
    afterEach(() => vi.useRealTimers())

    it("force-clears a dead generation after a stall without refetching (no ranked clobber)", async () => {
      // A generation that never signals `complete` (crashed task; the mocked channel fires nothing)
      // would otherwise spin "Organizing…" forever. The watchdog force-clears `generating` locally so
      // the arrows enable over the cached order — and must NOT refetch, since a mid-generation ranked
      // GET would clobber the streamed partial.
      setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
      const index = indexData({
        layout: "ranked",
        generating: true,
        hydratedFromPartial: true,
        sections: [section("", ["e1", "e2"])],
        entryIds: ["e1", "e2"],
      })
      const nav = renderFocusNav("e1", index, byId("e1", "e2"))
      expect(nav.current().generating).toBe(true)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(GENERATION_STALL_MS)
      })

      await waitFor(() => expect(nav.current().generating).toBe(false))
      expect(nav.current().nextHref).toBe(`/posts/e2?mailbox_entry_id=e2&return_to=${FOCUS_RETURN}`)
      expect(apiFetch).not.toHaveBeenCalled()
    })

    it("re-arms on channel events so a healthy but slow stream is not force-cleared", async () => {
      // The show page never reconciles progress deltas into the index cache, so the backstop must
      // re-arm on the channel events themselves — otherwise a generation slower than the stall window
      // would trip prematurely and enable the arrows over a non-final order.
      setShowUrl(`?mailbox_entry_id=e1&return_to=${FOCUS_RETURN}`)
      const index = indexData({
        layout: "ranked",
        generating: true,
        hydratedFromPartial: true,
        sections: [section("", ["e1", "e2"])],
        entryIds: ["e1", "e2"],
      })
      const nav = renderFocusNav("e1", index, byId("e1", "e2"))

      // Almost stall, then a progress event re-arms the timer; almost stall again — never trips.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(GENERATION_STALL_MS - 1)
      })
      await act(async () => {
        channelHandlers.at(-1)?.("updated", { type: "entry_scored", entry_id: "e1", score: 1, rank: 0 })
      })
      await act(async () => {
        await vi.advanceTimersByTimeAsync(GENERATION_STALL_MS - 1)
      })
      expect(nav.current().generating).toBe(true)

      // Channel goes silent → the backstop finally trips.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1)
      })
      await waitFor(() => expect(nav.current().generating).toBe(false))
      expect(apiFetch).not.toHaveBeenCalled()
    })
  })
})
