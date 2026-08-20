import { combineDateTimeToIso, startOfDayIso } from "~/react/ui/DateTime"

// Snooze has no upper horizon (unlike scheduled send's 30-day cap) — you can snooze
// as far out as you like. The only bound is that the target must be in the future.

// Days that can't be snoozed to: past days, compared against the start of today in
// the user's tz. There is no upper bound. The day's start instant is interpreted in
// the user's timezone (browser-local when unset), matching how the chosen time is —
// so day gating and the button-level future check agree on the same clock even when
// the browser tz differs from the account tz.
export function isSnoozeDayDisabled(dayIso: string, nowMs: number, timezone: string | null): boolean {
  const todayStartMs = new Date(startOfDayIso(new Date(nowMs), timezone)).getTime()
  const cellStartMs = new Date(combineDateTimeToIso(dayIso, "00:00", timezone)).getTime()
  return cellStartMs < todayStartMs
}

// The chosen instant must be in the future. `snoozeMs` is null until both a date and
// a time are picked; `atMs` is the reference clock.
export function isSnoozeableAt(snoozeMs: number | null, atMs: number): boolean {
  return snoozeMs !== null && snoozeMs > atMs
}

// Explains a rejected selection so the disabled Snooze button isn't silent. A past day
// is already un-clickable in the calendar, so the only reachable rejection is a past
// time-of-day on today. Null while nothing's picked yet — no message before the user acts.
export function snoozeValidationMessage(snoozeMs: number | null, atMs: number): string | null {
  if (snoozeMs === null) return null
  return isSnoozeableAt(snoozeMs, atMs) ? null : "Pick a time later than now."
}
