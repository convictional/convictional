import { describe, expect, it } from "vitest"

import {
  isDayDisabled,
  isSchedulableAt,
  SCHEDULE_MAX_MS,
  sendLaterValidationMessage,
} from "~/react/composites/emailComposer/components/sendLaterSchedule"

// A fixed reference clock so the datemath is deterministic regardless of the machine tz.
// 2026-07-21T17:00:00Z is 13:00 EDT (America/New_York, UTC-4) on a Tuesday.
const NOW = Date.parse("2026-07-21T17:00:00Z")

describe("isDayDisabled", () => {
  it("disables past days and days entirely beyond the 30-day horizon, keeps today and partial days", () => {
    const tz = "America/New_York"

    // Yesterday in the account tz is fully in the past.
    expect(isDayDisabled("2026-07-20", NOW, tz)).toBe(true)
    // Today stays enabled — its midnight equals the start of today, not before it.
    expect(isDayDisabled("2026-07-21", NOW, tz)).toBe(false)
    expect(isDayDisabled("2026-07-22", NOW, tz)).toBe(false)

    // The horizon lands mid-day on 2026-08-20 (NOW + 30d = 2026-08-20T17:00Z), so that
    // day only partially exceeds it and stays enabled; the next day is fully beyond.
    expect(isDayDisabled("2026-08-20", NOW, tz)).toBe(false)
    expect(isDayDisabled("2026-08-21", NOW, tz)).toBe(true)
  })

  it("classifies a day relative to the account tz, not the browser tz", () => {
    // 02:00Z is still 2026-07-20 (22:00) in New York but already 2026-07-21 (11:00) in Tokyo,
    // so the same calendar cell is today vs. yesterday depending on the tz used.
    const atBoundary = Date.parse("2026-07-21T02:00:00Z")
    expect(isDayDisabled("2026-07-20", atBoundary, "America/New_York")).toBe(false)
    expect(isDayDisabled("2026-07-20", atBoundary, "Asia/Tokyo")).toBe(true)
  })
})

describe("isSchedulableAt", () => {
  it("accepts times inside (now, now + horizon] and rejects everything else", () => {
    expect(isSchedulableAt(null, NOW)).toBe(false)
    // A pick at exactly the reference clock is rejected — must be strictly in the future.
    expect(isSchedulableAt(NOW, NOW)).toBe(false)
    expect(isSchedulableAt(NOW - 1000, NOW)).toBe(false)
    expect(isSchedulableAt(NOW + 1000, NOW)).toBe(true)
    // The horizon boundary is inclusive; one step past it is rejected.
    expect(isSchedulableAt(NOW + SCHEDULE_MAX_MS, NOW)).toBe(true)
    expect(isSchedulableAt(NOW + SCHEDULE_MAX_MS + 1000, NOW)).toBe(false)
  })
})

describe("sendLaterValidationMessage", () => {
  it("is null until a selection exists", () => {
    expect(sendLaterValidationMessage(null, NOW)).toBeNull()
  })

  it("flags past instants", () => {
    expect(sendLaterValidationMessage(NOW, NOW)).toBe("Pick a time later than now.")
    expect(sendLaterValidationMessage(NOW - 1, NOW)).toBe("Pick a time later than now.")
  })

  it("flags instants beyond the 30-day horizon", () => {
    expect(sendLaterValidationMessage(NOW + SCHEDULE_MAX_MS + 1, NOW)).toBe("Choose a time within the next 30 days.")
  })

  it("accepts instants inside the window", () => {
    expect(sendLaterValidationMessage(NOW + 1, NOW)).toBeNull()
    expect(sendLaterValidationMessage(NOW + SCHEDULE_MAX_MS, NOW)).toBeNull()
  })
})
