import { cleanup, render, screen } from "../../shared/testUtils"
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest"

import type { CalendarResponse } from "~/react/shared/types"

import { resetCurrentUser, setCurrentUser } from "../../shared/currentUserFixtures"

const calendarRef = { current: null as CalendarResponse | null }

vi.mock("~/react/shared/hooks/useCalendarConnection", () => ({
  useCalendarConnection: () => ({ calendar: calendarRef.current, loading: false }),
}))

vi.mock("~/react/features/meetingsUpcomingIndex/hooks/useUpcomingMeetings", () => ({
  // Always resolved with an empty list: these cases exercise the 0-meetings
  // empty-state branches.
  useUpcomingMeetings: () => ({
    meetings: [],
    loading: false,
    loadingMore: false,
    error: false,
    hasMore: false,
    loadMore: () => {},
  }),
}))

import { MeetingsUpcomingIndex } from "~/react/features/meetingsUpcomingIndex/MeetingsUpcomingIndex"

function makeCalendar(overrides: Partial<CalendarResponse> = {}): CalendarResponse {
  return {
    calendar_connected: true,
    provider: "google",
    preference: "all",
    calendar_user_id: "cal-1",
    is_google_authenticated: true,
    ...overrides,
  }
}

beforeEach(() => {
  // The component reads the viewer's timezone from useCurrentUser; seed the
  // store so it doesn't fall through to a real /api/users/me fetch.
  setCurrentUser({ id: "u1", time_zone: "UTC" })
})

afterEach(() => {
  cleanup()
  calendarRef.current = null
  resetCurrentUser()
})

describe("MeetingsUpcomingIndex", () => {
  test("gates the empty meetings state on the calendar provider", () => {
    // Microsoft (non-Google) user with no meetings: recording isn't available,
    // so explain that instead of the generic empty state.
    calendarRef.current = makeCalendar({ is_google_authenticated: false, provider: "microsoft" })
    const { rerender } = render(<MeetingsUpcomingIndex googleCalendarLoginUrl="/google" />)
    expect(screen.getByText("Meeting recording is available for Google accounts.")).toBeTruthy()
    expect(screen.queryByText("No upcoming meetings")).toBeNull()

    // Google user with no meetings: the original empty state shows.
    calendarRef.current = makeCalendar({ is_google_authenticated: true })
    rerender(<MeetingsUpcomingIndex googleCalendarLoginUrl="/google" />)
    expect(screen.getByText("No upcoming meetings")).toBeTruthy()
    expect(screen.queryByText("Meeting recording is available for Google accounts.")).toBeNull()
  })

  test("shows the connect-calendar first-run prompt for a Google user who hasn't connected", () => {
    // Not connected yet, but Google-authed: the first-run prompt takes over instead
    // of the empty state, so nothing reads as "you have no meetings".
    calendarRef.current = makeCalendar({ calendar_connected: false, is_google_authenticated: true })
    const { rerender } = render(<MeetingsUpcomingIndex googleCalendarLoginUrl="/google" />)
    expect(screen.getByText("Turn every meeting into knowledge")).toBeTruthy()
    expect(screen.getByRole("button", { name: /Connect Calendar/ })).toBeTruthy()
    expect(screen.queryByText("No upcoming meetings")).toBeNull()

    // Once connected, the prompt gives way to the meetings list / empty state.
    calendarRef.current = makeCalendar({ calendar_connected: true })
    rerender(<MeetingsUpcomingIndex googleCalendarLoginUrl="/google" />)
    expect(screen.queryByText("Turn every meeting into knowledge")).toBeNull()
  })
})
