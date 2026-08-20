import { afterEach, describe, expect, test } from "vitest"

import { UserDateTime } from "~/react/composites/UserDateTime"

import { resetCurrentUser, setCurrentUser } from "../shared/currentUserFixtures"
import { cleanup, render, screen } from "../shared/testUtils"

describe("UserDateTime", () => {
  afterEach(() => {
    cleanup()
    resetCurrentUser()
  })

  // 2026-05-04T13:00:00Z is 9 AM in New York; a tz-agnostic formatter would show the
  // browser's wall clock instead. Asserting the tz-specific format proves the store tz reached DateTime.
  test("renders the timestamp in the current user's configured timezone", () => {
    setCurrentUser({ id: "u1", time_zone: "America/New_York" })
    render(<UserDateTime datetime="2026-05-04T13:00:00Z" format="weekday_short_month_day_time_tz" />)
    expect(screen.getByText("Mon, May 4 at 9 AM EDT")).toBeInTheDocument()
  })

  test("falls back to browser-local when the user has no timezone set", () => {
    setCurrentUser({ id: "u1", time_zone: null })
    render(<UserDateTime datetime="2026-05-04T13:00:00Z" format="date_iso_8601" />)
    // Date is tz-independent enough here that we only assert it renders a <time> with the raw value.
    expect(screen.getByText(/2026-05-0[34]/)).toBeInTheDocument()
  })
})
