import { combineDateTimeToIso, startOfDayIso } from "~/react/ui/DateTime"

// Mirror the backend's SCHEDULED_SEND_MAX_HORIZON (app/models/workspaces/email/thread.py).
// The API rejects anything beyond this with a 422; disable it in the UI instead.
export const SCHEDULE_MAX_DAYS = 30
export const SCHEDULE_MAX_MS = SCHEDULE_MAX_DAYS * 24 * 60 * 60 * 1000

// A day's start instant in the user's timezone (browser-local when unset), matching
// how the chosen time is interpreted — so day gating and the button-level horizon
// check agree on the same clock even when the browser tz differs from the account tz.
export function cellStartMs(dayIso: string, timezone: string | null): number {
  return new Date(combineDateTimeToIso(dayIso, "00:00", timezone)).getTime()
}

// Days that can't be scheduled: past days (compared against the start of today in the
// user's tz), and days whose entire span is beyond the send horizon. A day that only
// partially exceeds the horizon stays enabled; the button-level check guards the
// specific time within it.
export function isDayDisabled(dayIso: string, nowMs: number, timezone: string | null): boolean {
  const todayStartMs = new Date(startOfDayIso(new Date(nowMs), timezone)).getTime()
  const cellMs = cellStartMs(dayIso, timezone)
  return cellMs < todayStartMs || cellMs > nowMs + SCHEDULE_MAX_MS
}

// The backend rejects times outside (now, now + horizon]. `scheduledMs` is the chosen
// instant (null until both a date and a time are picked); `atMs` is the reference clock.
export function isSchedulableAt(scheduledMs: number | null, atMs: number): boolean {
  return scheduledMs !== null && scheduledMs > atMs && scheduledMs <= atMs + SCHEDULE_MAX_MS
}

// Explains a rejected selection so the disabled Schedule button isn't silent. Past days and
// days wholly beyond the horizon are already un-clickable in the calendar, so the reachable
// rejections are a past time-of-day on today or a time past the horizon on the last allowed
// day. Null while nothing's picked yet — no message before the user acts.
export function sendLaterValidationMessage(scheduledMs: number | null, atMs: number): string | null {
  if (scheduledMs === null) return null
  if (scheduledMs <= atMs) return "Pick a time later than now."
  if (scheduledMs > atMs + SCHEDULE_MAX_MS) return `Choose a time within the next ${SCHEDULE_MAX_DAYS} days.`
  return null
}
