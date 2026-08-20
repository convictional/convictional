import { describe, test, expect } from "vitest"
import { formatDateDisplay, formatDateOnly, parseDateOnly } from "../../../app/javascript/shared/datetime"

describe("date-only utilities", () => {
  test("parse, format, and display dates without timezone conversion", () => {
    // Parse ISO date to components
    const parsed = parseDateOnly("2026-03-31")
    expect(parsed).toEqual({ year: 2026, month: 2, day: 31 })

    // Format components back to ISO string
    expect(formatDateOnly(2026, 2, 31)).toBe("2026-03-31")
    expect(formatDateOnly(2026, 0, 5)).toBe("2026-01-05")
    expect(formatDateOnly(2026, 11, 31)).toBe("2026-12-31")

    // Format for human-readable display
    expect(formatDateDisplay(2026, 2, 31)).toBe("Mar 31, 2026")
    expect(formatDateDisplay(2026, 0, 5)).toBe("Jan 05, 2026")
    expect(formatDateDisplay(2026, 11, 25)).toBe("Dec 25, 2026")

    // Verify round-trip works (parse then format)
    const roundTrip = parseDateOnly("2026-03-31")
    expect(formatDateOnly(roundTrip.year, roundTrip.month, roundTrip.day)).toBe("2026-03-31")
  })
})
