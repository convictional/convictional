import { describe, expect, it } from "vitest"

import { isSnoozeableAt, isSnoozeDayDisabled } from "~/react/composites/MailboxActionBar/snoozeSchedule"

// A fixed reference clock so the datemath is deterministic regardless of the machine tz.
// 2026-07-21T17:00:00Z is 13:00 EDT (America/New_York, UTC-4) on a Tuesday.
const NOW = Date.parse("2026-07-21T17:00:00Z")

describe("isSnoozeDayDisabled", () => {
  it("disables past days, keeps today and any future day (no upper horizon)", () => {
    const tz = "America/New_York"

    // Yesterday in the account tz is fully in the past.
    expect(isSnoozeDayDisabled("2026-07-20", NOW, tz)).toBe(true)
    // Today stays enabled — its midnight equals the start of today, not before it.
    expect(isSnoozeDayDisabled("2026-07-21", NOW, tz)).toBe(false)
    expect(isSnoozeDayDisabled("2026-07-22", NOW, tz)).toBe(false)

    // Snooze has no cap: even a year out stays enabled (unlike scheduled send's 30-day horizon).
    expect(isSnoozeDayDisabled("2027-07-21", NOW, tz)).toBe(false)
  })

  it("classifies a day relative to the account tz, not the browser tz", () => {
    // 02:00Z is still 2026-07-20 (22:00) in New York but already 2026-07-21 (11:00) in Tokyo,
    // so the same calendar cell is today vs. yesterday depending on the tz used.
    const atBoundary = Date.parse("2026-07-21T02:00:00Z")
    expect(isSnoozeDayDisabled("2026-07-20", atBoundary, "America/New_York")).toBe(false)
    expect(isSnoozeDayDisabled("2026-07-20", atBoundary, "Asia/Tokyo")).toBe(true)
  })
})

describe("isSnoozeableAt", () => {
  it("accepts any future instant and rejects the present, past, and null", () => {
    expect(isSnoozeableAt(null, NOW)).toBe(false)
    // A pick at exactly the reference clock is rejected — must be strictly in the future.
    expect(isSnoozeableAt(NOW, NOW)).toBe(false)
    expect(isSnoozeableAt(NOW - 1000, NOW)).toBe(false)
    expect(isSnoozeableAt(NOW + 1000, NOW)).toBe(true)
    // No upper bound — a far-future instant is still snoozeable.
    expect(isSnoozeableAt(NOW + 400 * 24 * 60 * 60 * 1000, NOW)).toBe(true)
  })
})
