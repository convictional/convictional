import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", () => ({ apiFetch: vi.fn() }))
vi.mock("~/react/shared/hooks/useChannel", () => ({ useChannel: vi.fn() }))
// useScheduledResearchData reads the current user id (for the scheduled_research
// topic) via useCurrentUser; stub it so the hook isn't entangled with the store
// or an extra /api/users/me fetch in these data-flow tests.
vi.mock("~/react/shared/hooks/useCurrentUser", () => ({
  useCurrentUser: () => ({ user: { id: "user-1" }, clientConfig: null, loading: false, error: null }),
}))
vi.mock("~/channels/client", () => ({ getChannelsClient: () => null }))

import { apiFetch } from "~/react/shared/apiFetch"
import { useScheduledResearchData } from "~/react/features/research/scheduled/hooks/useScheduledResearchData"
import {
  ScheduledResearchFrequency,
  type ScheduledResearch,
  type ScheduledResearchListResponse,
} from "~/react/features/research/scheduled/types"

import { deferred } from "../../../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)

function makeItem(overrides: Partial<ScheduledResearch> = {}): ScheduledResearch {
  return {
    id: "sr-1",
    title: "Weekly digest",
    prompt: "Summarize",
    frequency: ScheduledResearchFrequency.WEEKLY,
    hour: 9,
    day_of_week: "monday",
    schedule_description: "Weekly on Monday",
    next_run_at: null,
    last_delivered_at: null,
    preparation_failed_at: null,
    created_at: "2026-06-01T00:00:00Z",
    ...overrides,
  }
}

function makePage(
  items: ScheduledResearch[],
  pagination: Partial<Pick<ScheduledResearchListResponse, "next_cursor" | "has_more">> = {}
): ScheduledResearchListResponse {
  return {
    scheduled_researches: items,
    next_cursor: null,
    has_more: false,
    ...pagination,
  }
}

function calledUrl(callIndex: number): URL {
  return new URL(mockApiFetch.mock.calls[callIndex][0] as string, "http://test.local")
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

describe("useScheduledResearchData", () => {
  it("loads the first page on mount", async () => {
    mockApiFetch.mockResolvedValue(makePage([makeItem({ id: "a" }), makeItem({ id: "b" })]))

    const { result } = renderHook(() => useScheduledResearchData())
    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.items.map(s => s.id)).toEqual(["a", "b"])
    expect(calledUrl(0).pathname).toBe("/api/scheduled_research")
  })

  it("applyCreated prepends, applyUpdated replaces in place, applyDeleted removes", async () => {
    mockApiFetch.mockResolvedValue(makePage([makeItem({ id: "a", title: "Old" })]))

    const { result } = renderHook(() => useScheduledResearchData())
    await waitFor(() => expect(result.current.loading).toBe(false))

    act(() => result.current.applyCreated(makeItem({ id: "b" })))
    expect(result.current.items.map(s => s.id)).toEqual(["b", "a"])

    act(() => result.current.applyUpdated(makeItem({ id: "a", title: "New" })))
    expect(result.current.items.find(s => s.id === "a")?.title).toBe("New")

    act(() => result.current.applyDeleted("b"))
    expect(result.current.items.map(s => s.id)).toEqual(["a"])
  })

  it("refetches once (coalesced) when applyUpdated targets an unknown id", async () => {
    mockApiFetch.mockResolvedValueOnce(makePage([makeItem({ id: "a" })]))

    const { result } = renderHook(() => useScheduledResearchData())
    await waitFor(() => expect(result.current.loading).toBe(false))

    const pending = deferred<ScheduledResearchListResponse>()
    mockApiFetch.mockReturnValueOnce(pending.promise)

    act(() => {
      result.current.applyUpdated(makeItem({ id: "unknown" }))
      result.current.applyUpdated(makeItem({ id: "unknown" }))
    })
    // Both unknown-id events coalesce into a single refetch.
    expect(mockApiFetch).toHaveBeenCalledTimes(2)

    await act(async () => {
      pending.resolve(makePage([makeItem({ id: "a" }), makeItem({ id: "unknown" })]))
    })
    expect(result.current.items.map(s => s.id)).toEqual(["a", "unknown"])
  })

  it("ignores a stale loadMore response superseded by refetch (new abort guard)", async () => {
    mockApiFetch.mockResolvedValueOnce(makePage([makeItem({ id: "a" })], { next_cursor: "c1", has_more: true }))

    const { result } = renderHook(() => useScheduledResearchData())
    await waitFor(() => expect(result.current.loading).toBe(false))

    const stale = deferred<ScheduledResearchListResponse>()
    const fresh = deferred<ScheduledResearchListResponse>()
    mockApiFetch.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise)

    act(() => result.current.loadMore())
    act(() => {
      void result.current.refetch()
    })

    await act(async () => {
      fresh.resolve(makePage([makeItem({ id: "fresh" })]))
    })
    await act(async () => {
      stale.resolve(makePage([makeItem({ id: "stale" })]))
    })

    expect(result.current.items.map(s => s.id)).toEqual(["fresh"])
  })
})
