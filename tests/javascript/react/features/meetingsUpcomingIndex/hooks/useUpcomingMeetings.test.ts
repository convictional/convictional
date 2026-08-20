import { act, renderHook, waitFor } from "@testing-library/react"
import dayjs from "dayjs"
import { beforeEach, describe, expect, it, vi } from "vitest"

vi.mock("~/react/shared/apiFetch", async () => {
  const actual = await vi.importActual<typeof import("~/react/shared/apiFetch")>("~/react/shared/apiFetch")
  return { ...actual, apiFetch: vi.fn() }
})

import { apiFetch } from "~/react/shared/apiFetch"
// Importing the hook also extends dayjs with the timezone plugin (via DateTime),
// so dayjs(...).tz(...) is available in the start-of-day assertion below.
import { useUpcomingMeetings } from "~/react/features/meetingsUpcomingIndex/hooks/useUpcomingMeetings"

import { makeListPage, makeMeeting } from "../../../shared/meetingsFixtures"

const mockApiFetch = vi.mocked(apiFetch)
const TZ = "America/New_York"

function calledUrl(callIndex: number): URL {
  return new URL(mockApiFetch.mock.calls[callIndex][0] as string, "http://test.local")
}

beforeEach(() => {
  mockApiFetch.mockReset()
})

describe("useUpcomingMeetings query building", () => {
  it("requests from the start of today in the user tz, member-scoped, declined included", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([]))

    renderHook(() => useUpcomingMeetings(TZ))
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))

    const url = calledUrl(0)
    expect(url.pathname).toBe("/api/meetings")
    expect(url.searchParams.get("sort")).toBe("scheduled_at_asc")
    // Parity-critical defaults: `member` restores the legacy creator/collaborator
    // scope (no org-shared leakage), and declined meetings stay in the list so
    // they render struck-through rather than vanishing.
    expect(url.searchParams.get("scope")).toBe("member")
    expect(url.searchParams.get("include_declined")).toBe("true")

    const after = url.searchParams.get("scheduled_after")
    expect(after).not.toBeNull()
    // Midnight in the user's configured tz, not the runner's local tz.
    expect(
      dayjs(after as string)
        .tz(TZ)
        .format("HH:mm:ss")
    ).toBe("00:00:00")
  })
})

describe("useUpcomingMeetings refresh", () => {
  it("refetches when the tab becomes visible", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([]))

    renderHook(() => useUpcomingMeetings(TZ))
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
    })
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(2))
  })

  it("stops listening for visibility changes after unmount", async () => {
    mockApiFetch.mockResolvedValue(makeListPage([]))

    const { unmount } = renderHook(() => useUpcomingMeetings(TZ))
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1))

    unmount()
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })

  it("does not refetch on visibility once the list has been paginated", async () => {
    // A refetch rebuilds from page 1, so refetching after the user scrolled
    // would discard loaded pages and their scroll position.
    mockApiFetch.mockResolvedValueOnce(
      makeListPage([makeMeeting({ id: "a" })], { next_cursor: "cursor-1", has_more: true })
    )
    const { result } = renderHook(() => useUpcomingMeetings(TZ))
    await waitFor(() => expect(result.current.loading).toBe(false))

    mockApiFetch.mockResolvedValueOnce(makeListPage([makeMeeting({ id: "b" })], { has_more: false }))
    act(() => {
      result.current.loadMore()
    })
    await waitFor(() => expect(result.current.loadingMore).toBe(false))
    expect(mockApiFetch).toHaveBeenCalledTimes(2)

    act(() => {
      document.dispatchEvent(new Event("visibilitychange"))
    })
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
  })
})
