import { describe, expect, test } from "vitest"

import { combineDateTimeToIso, formatDateTime, formatScheduledFor, isoDateInZone } from "~/react/ui/DateTime"

describe("formatDateTime", () => {
  describe("contextual format", () => {
    test("returns time only when the datetime is on the same calendar day", () => {
      const now = new Date(2026, 3, 15, 14, 0, 0) // Apr 15, 2026 2:00 PM local
      const target = new Date(2026, 3, 15, 15, 42, 0) // Apr 15, 2026 3:42 PM local
      const result = formatDateTime(target.toISOString(), "contextual", { now })
      expect(result).toBe("3:42 PM")
    })

    test("returns date and time for yesterday", () => {
      const now = new Date(2026, 3, 16, 10, 0, 0)
      const target = new Date(2026, 3, 15, 15, 42, 0)
      const result = formatDateTime(target.toISOString(), "contextual", { now })
      expect(result).toBe("Apr 15, 3:42 PM")
    })

    test("handles a month boundary", () => {
      const now = new Date(2026, 3, 1, 8, 0, 0) // Apr 1
      const target = new Date(2026, 2, 31, 23, 30, 0) // Mar 31 11:30 PM
      const result = formatDateTime(target.toISOString(), "contextual", { now })
      expect(result).toBe("Mar 31, 11:30 PM")
    })

    test("omits the year for prior-year datetimes", () => {
      const now = new Date(2026, 0, 5, 12, 0, 0) // Jan 5, 2026
      const target = new Date(2025, 11, 25, 9, 15, 0) // Dec 25, 2025
      const result = formatDateTime(target.toISOString(), "contextual", { now })
      expect(result).toBe("Dec 25, 9:15 AM")
    })

    test("treats 11:59 PM yesterday as a different day from early morning today", () => {
      const now = new Date(2026, 3, 16, 0, 30, 0) // Apr 16 12:30 AM
      const target = new Date(2026, 3, 15, 23, 59, 0) // Apr 15 11:59 PM
      const result = formatDateTime(target.toISOString(), "contextual", { now })
      expect(result).toBe("Apr 15, 11:59 PM")
    })
  })

  describe("timezone option", () => {
    // 2026-05-04T13:00:00Z → 9 AM EDT (Mon, May 4) in New York and 6 AM PDT in Los Angeles.
    const iso = "2026-05-04T13:00:00Z"

    test("formats wall-clock time in the requested timezone, not the browser's", () => {
      expect(formatDateTime(iso, "weekday_short_month_day_time_tz", { timezone: "America/New_York" })).toBe(
        "Mon, May 4 at 9 AM EDT"
      )
      expect(formatDateTime(iso, "weekday_short_month_day_time_tz", { timezone: "America/Los_Angeles" })).toBe(
        "Mon, May 4 at 6 AM PDT"
      )
    })

    test("omits the abbreviation when no timezone is passed (z token is empty without a tz-aware date)", () => {
      // Without a timezone option, the `z` token has no value to render — the rest of the format
      // still works, so callers shouldn't reach for this format without passing `timezone`.
      const result = formatDateTime(iso, "weekday_short_month_day_time_tz")
      expect(result).toMatch(/^Mon, May 4 at \d+ (AM|PM)/)
    })
  })

  describe("named formats", () => {
    const d = new Date(2026, 3, 15, 15, 42, 0).toISOString()

    test("datetime", () => {
      expect(formatDateTime(d, "datetime")).toBe("4/15/2026 3:42 PM")
    })

    test("time", () => {
      expect(formatDateTime(d, "time")).toBe("3:42 PM")
    })

    test("date_medium", () => {
      expect(formatDateTime(d, "date_medium")).toBe("Apr 15 2026")
    })

    test("month_day", () => {
      expect(formatDateTime(d, "month_day")).toBe("Apr 15")
    })
  })

  describe("formatScheduledFor", () => {
    test("prefixes the send time in the given timezone", () => {
      // 2026-05-04T13:00:00Z → 9:00 AM EDT in New York.
      expect(formatScheduledFor("2026-05-04T13:00:00Z", "America/New_York")).toBe("Scheduled May 4 2026, 9:00 AM")
    })

    test("falls back to a bare label when no time is given", () => {
      expect(formatScheduledFor(null)).toBe("Scheduled")
    })
  })

  describe("isoDateInZone", () => {
    test("returns the calendar date in the given timezone, not the browser's", () => {
      // 02:00Z is still 2026-07-20 (22:00) in New York but already 2026-07-21 (11:00) in Tokyo.
      const instant = new Date("2026-07-21T02:00:00Z")
      expect(isoDateInZone(instant, "America/New_York")).toBe("2026-07-20")
      expect(isoDateInZone(instant, "Asia/Tokyo")).toBe("2026-07-21")
    })
  })

  describe("combineDateTimeToIso", () => {
    test("interprets the date + time as wall-clock in the given timezone", () => {
      // 9:00 AM in New York on 2026-05-04 (EDT, UTC-4) is 13:00:00Z.
      expect(combineDateTimeToIso("2026-05-04", "09:00", "America/New_York")).toBe("2026-05-04T13:00:00.000Z")
      // Same wall-clock in Los Angeles (PDT, UTC-7) is 16:00:00Z.
      expect(combineDateTimeToIso("2026-05-04", "09:00", "America/Los_Angeles")).toBe("2026-05-04T16:00:00.000Z")
    })
  })

  describe("relative format", () => {
    test("returns a human-readable relative string", () => {
      const target = new Date(Date.now() - 60 * 1000) // 1 minute ago
      const result = formatDateTime(target.toISOString(), "relative")
      expect(result).toMatch(/minute/)
    })

    test("stays relative within the 30-day cutoff", () => {
      const now = new Date(2026, 3, 15, 12, 0, 0)
      const target = new Date(2026, 3, 1, 12, 0, 0) // 14 days earlier
      expect(formatDateTime(target.toISOString(), "relative", { now })).toBe("14 days ago")
    })

    test("falls back to an absolute date once older than the cutoff (same year)", () => {
      const now = new Date(2026, 5, 15, 12, 0, 0) // Jun 15, 2026
      const target = new Date(2026, 2, 1, 12, 0, 0) // Mar 1, 2026 (~3.5 months earlier)
      expect(formatDateTime(target.toISOString(), "relative", { now })).toBe("Mar 1")
    })

    test("includes the year when the absolute fallback is a prior year", () => {
      const now = new Date(2026, 0, 20, 12, 0, 0) // Jan 20, 2026
      const target = new Date(2025, 9, 1, 12, 0, 0) // Oct 1, 2025
      expect(formatDateTime(target.toISOString(), "relative", { now })).toBe("Oct 1 2025")
    })

    test("applies the cutoff to far-future dates too", () => {
      const now = new Date(2026, 3, 15, 12, 0, 0)
      const target = new Date(2026, 6, 1, 12, 0, 0) // ~2.5 months ahead
      expect(formatDateTime(target.toISOString(), "relative", { now })).toBe("Jul 1")
    })
  })
})
