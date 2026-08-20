import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { createElement, type ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useMailboxView } from "~/react/features/mailboxIndex/hooks/useMailboxView"
import { type MailboxViewIndexData, mailboxViewIndexQueryKey } from "~/react/shared/queries/mailboxViewIndex"
import type { MailboxEntryLookupResponse, MailboxViewIndexResponse, ViewSection } from "~/react/shared/types"
import { ChannelEventResource } from "~/types/channels"

// useMailboxView writes the focus-mode index (structure/ordering/generation status) into a shared
// Query cache (`["mailboxViewIndex", …]`), split from the entry bodies because the order is eager
// (the full id set at once) while bodies hydrate lazily. The broader behavioral contract (hydration,
// pagination, streaming, watchdog, delete/refresh) is covered by the sibling useMailboxView /
// rankedSortStreaming / viewSectionStreaming suites; these tests cover the shared cache specifically:
// that it holds the authoritative order, and that its `generating` flag only flips false once the full
// final order is present (so any reader of the order can trust it as complete, never mid-generation).

const apiFetch = vi.hoisted(() => vi.fn())
vi.mock("~/react/shared/apiFetch", () => ({
  apiFetch,
  errorMessage: (_e: unknown, fallback: string) => fallback,
}))

vi.mock("~/channels/client", () => ({ getChannelsClient: () => null }))

const channels = vi.hoisted(() => ({ handlers: {} as Record<string, (action: string, data: unknown) => void> }))
vi.mock("~/react/shared/hooks/useChannel", () => ({
  useChannel: (target: unknown, resource: string, onMessage: (action: string, data: unknown) => void) => {
    if (target) channels.handlers[resource] = onMessage
  },
}))

function entry(id: string) {
  return {
    id,
    resource_type: "Post" as const,
    href: `/posts/${id}`,
    title: null,
    preview: null,
    sender_display: null,
    last_activity_at: "2026-07-20T00:00:00Z",
    is_unread: false,
    is_archived: false,
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

function section(title: string, ids: string[]): ViewSection {
  return { title, description: "", mailbox_entry_ids: ids, goal: null }
}

function viewIndex(
  overrides: Partial<MailboxViewIndexResponse> & { layout?: "grouped" | "ranked" } = {}
): MailboxViewIndexResponse {
  const { layout = "grouped", ...rest } = overrides
  return {
    all_views: [],
    active: {
      kind: "template",
      id: "template:needs_reply",
      title: "Needs a reply",
      view_request: null,
      channel_id: "template:needs_reply",
      requires_goals: false,
      layout,
    },
    cached_sections: null,
    cached_entry_ids: [],
    generating: false,
    has_goals_for_view: true,
    is_not_found: false,
    eligible_entry_count: null,
    considered_entry_count: null,
    ...rest,
  }
}

function mockApi(view: MailboxViewIndexResponse) {
  apiFetch.mockImplementation((url: string): Promise<unknown> => {
    if (url.startsWith("/api/mailbox_views")) return Promise.resolve(view)
    if (url.startsWith("/api/mailbox_entries/lookup")) {
      const ids = new URLSearchParams(url.split("?")[1] ?? "").getAll("ids")
      const response: MailboxEntryLookupResponse = { entries: ids.map(entry), has_more: false, next_cursor: null }
      return Promise.resolve(response)
    }
    return Promise.resolve({})
  })
}

let client: QueryClient
const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children)

const TEMPLATE = "needs_reply"
const KEY = mailboxViewIndexQueryKey({ viewId: null, template: TEMPLATE, goalId: null })

function renderView() {
  return renderHook(
    () => useMailboxView({ initialViewId: null, initialTemplate: TEMPLATE, initialGoalId: null, userId: "u1" }),
    { wrapper }
  )
}

function fireView(payload: Record<string, unknown>) {
  return act(async () => {
    channels.handlers[ChannelEventResource.MAILBOX_VIEW]?.("event", payload)
  })
}

function cached(): MailboxViewIndexData | undefined {
  return client.getQueryData<MailboxViewIndexData>(KEY)
}

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  apiFetch.mockReset()
  channels.handlers = {}
})

afterEach(() => {
  client.clear()
})

describe("useMailboxView shared index cache", () => {
  it("publishes a settled grouped view's flat order to the shared cache", async () => {
    mockApi(
      viewIndex({ cached_sections: [section("A", ["1", "2"])], cached_entry_ids: ["1", "2"], generating: false })
    )
    const { result } = renderView()

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(cached()?.entryIds).toEqual(["1", "2"])
    expect(cached()?.sections).toHaveLength(1)
    expect(cached()?.generating).toBe(false)
  })

  it("holds generating with the partial order during a grouped stream, and the full order on complete", async () => {
    mockApi(viewIndex({ cached_sections: null, cached_entry_ids: [] }))
    const { result } = renderView()

    // Cache miss with an active view: generating is asserted up front (no empty flash).
    await waitFor(() => expect(cached()?.generating).toBe(true))

    await fireView({ type: "section", section_index: 0, section: section("A", ["1", "2"]) })
    await waitFor(() => expect(cached()?.entryIds).toEqual(["1", "2"]))
    expect(cached()?.generating).toBe(true)

    // The navigation invariant: generating flips false only once the full final order is in the cache.
    await fireView({ type: "complete" })
    await waitFor(() => expect(cached()?.generating).toBe(false))
    expect(cached()?.entryIds).toEqual(["1", "2"])
  })

  it("orders a ranked stream by (score, rank, id) in the cache and freezes it on complete", async () => {
    mockApi(viewIndex({ layout: "ranked", cached_sections: null, cached_entry_ids: [] }))
    const { result } = renderView()
    await waitFor(() => expect(cached()?.generating).toBe(true))
    expect(result.current.isGenerating).toBe(true)

    await fireView({ type: "entry_scored", entry_id: "a", score: 5, rank: 2 })
    await fireView({ type: "entry_scored", entry_id: "b", score: 9, rank: 1 })
    await waitFor(() => expect(cached()?.entryIds).toEqual(["b", "a"]))

    // Batched sentinel tail for everything the LLM never scored.
    await fireView({ type: "entries_scored", entry_ids: ["c"], ranks: [5], score: 0 })
    await waitFor(() => expect(cached()?.entryIds).toEqual(["b", "a", "c"]))

    await fireView({ type: "complete" })
    await waitFor(() => expect(cached()?.generating).toBe(false))
    expect(cached()?.entryIds).toEqual(["b", "a", "c"])
  })
})
