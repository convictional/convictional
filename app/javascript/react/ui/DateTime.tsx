import dayjs from "dayjs"
import advancedFormat from "dayjs/plugin/advancedFormat"
import localizedFormat from "dayjs/plugin/localizedFormat"
import relativeTime from "dayjs/plugin/relativeTime"
import timezone from "dayjs/plugin/timezone"
import utc from "dayjs/plugin/utc"
import { useEffect, useState } from "react"

dayjs.extend(utc)
dayjs.extend(timezone)
dayjs.extend(relativeTime)
dayjs.extend(localizedFormat)
dayjs.extend(advancedFormat)

export const DATETIME_FORMATS = {
  date: "M/D/YYYY",
  date_iso_8601: "YYYY-MM-DD",
  date_medium: "MMM D YYYY",
  date_ordinal: "MMM Do, YYYY",
  time: "h:mm A",
  datetime: "M/D/YYYY h:mm A",
  datetime_iso_8601: "YYYY-MM-DDTHH:mm:ssZ",
  datetime_long: "MMMM D, YYYY [at] h:mm A",
  full_weekday_full_month_day: "dddd, MMMM D",
  short_month_day_year_time: "MMM D YYYY, h:mm A",
  day_of_week: "dddd",
  month_day: "MMM D",
  month_day_time: "MMM D, h:mm A",
  // The `z` token is dayjs/timezone's tz abbreviation — it only resolves when the value is in
  // a tz-aware dayjs (i.e. options.timezone is passed). Without it, the abbreviation is empty.
  weekday_short_month_day_time_tz: "ddd, MMM D [at] h A z",
} as const

type NamedFormat = keyof typeof DATETIME_FORMATS
export type DateTimeFormat = NamedFormat | "contextual" | "relative"

export interface FormatDateTimeOptions {
  now?: Date
  timezone?: string | null
}

// Past this age (in either direction), a relative string like "4 months ago" is less useful
// than the actual date, so "relative" falls back to an absolute date.
// See https://github.com/convictional/convictional/issues/8648.
const RELATIVE_CUTOFF_MS = 30 * 24 * 60 * 60 * 1000

export function formatDateTime(
  isoString: string,
  format: DateTimeFormat = "datetime",
  options: FormatDateTimeOptions = {}
): string {
  const { now = new Date(), timezone: tz } = options
  const base = dayjs(isoString)
  const d = tz ? base.tz(tz) : base
  if (format === "relative") {
    const reference = tz ? dayjs(now).tz(tz) : dayjs(now)
    if (Math.abs(d.valueOf() - reference.valueOf()) >= RELATIVE_CUTOFF_MS) {
      // Absolute contextual date: same year "Aug 21", prior year "Aug 21 2024".
      return d.isSame(reference, "year")
        ? d.format(DATETIME_FORMATS.month_day)
        : d.format(DATETIME_FORMATS.date_medium)
    }
    // from(reference), not fromNow(), so the relative words honor options.now consistently with the cutoff.
    return d.from(reference)
  }
  if (format === "contextual") {
    return d.isSame(now, "day") ? d.format(DATETIME_FORMATS.time) : d.format(DATETIME_FORMATS.month_day_time)
  }
  return d.format(DATETIME_FORMATS[format])
}

// The snooze confirmation phrasing, shared by the index UndoToast, the show-page
// action bar, and the entry-row snooze tooltip so they can't drift apart.
export function formatSnoozedUntil(snoozedUntil: string | null | undefined, timezone?: string | null): string {
  if (!snoozedUntil) return "Snoozed"
  return `Snoozed until ${formatDateTime(snoozedUntil, "short_month_day_year_time", { timezone })}`
}

// The scheduled-send phrasing for the composer's read-only scheduled banner
// (ScheduledDraftPreview): "Scheduled {date}", with a bare "Scheduled" fallback.
export function formatScheduledFor(scheduledFor: string | null | undefined, timezone?: string | null): string {
  if (!scheduledFor) return "Scheduled"
  return `Scheduled ${formatDateTime(scheduledFor, "short_month_day_year_time", { timezone })}`
}

// Combines a calendar date (YYYY-MM-DD) and a wall-clock time (HH:mm) interpreted
// in `timezone` (browser-local when omitted) into an ISO instant. Used by the
// composer's send-later picker so the chosen time means the user's local clock.
export function combineDateTimeToIso(dateIso: string, time: string, timezone?: string | null): string {
  const wallClock = `${dateIso}T${time}`
  return (timezone ? dayjs.tz(wallClock, timezone) : dayjs(wallClock)).toISOString()
}

// Start of the calendar day containing `date`, in `timezone` (or browser-local
// when omitted), as an ISO instant. Used to derive the upcoming-list window so
// "today" matches the user's configured zone rather than the browser's.
export function startOfDayIso(date: Date, timezone?: string | null): string {
  const d = dayjs(date)
  return (timezone ? d.tz(timezone) : d).startOf("day").toISOString()
}

// The calendar date (naive YYYY-MM-DD) of `date` in `timezone` (browser-local when
// omitted). Anchors a date picker's "today" on the user's zone, matching the same
// timezone the picker uses to gate days — a bare `new Date()` would drift a day
// whenever the browser zone straddles a date boundary from the account zone.
export function isoDateInZone(date: Date, timezone?: string | null): string {
  const d = dayjs(date)
  return (timezone ? d.tz(timezone) : d).format("YYYY-MM-DD")
}

// The next top-of-the-hour after `date`, as a wall-clock HH:mm in `timezone` (browser-local
// when omitted). Seeds the DateTimePicker with a time that's already in the future, so
// selecting today opens on a valid time rather than the disabled/past state.
export function nextHourTimeInZone(date: Date, timezone?: string | null): string {
  const d = dayjs(date)
  return (timezone ? d.tz(timezone) : d).add(1, "hour").startOf("hour").format("HH:mm")
}

interface DateTimeProps {
  datetime: string
  format?: DateTimeFormat
  className?: string
  // The user's configured timezone. Omitted falls back to browser-local, which
  // diverges from the server-rendered value for users whose browser tz differs
  // from their account tz — so list/show islands thread the user tz through.
  timezone?: string | null
}

export function DateTime({ datetime, format = "datetime", className, timezone }: DateTimeProps) {
  const [, forceRender] = useState(0)

  useEffect(() => {
    if (format !== "relative") return
    const id = setInterval(() => forceRender(n => n + 1), 60000)
    return () => clearInterval(id)
  }, [format])

  const text = formatDateTime(datetime, format, { timezone })
  const title = formatDateTime(datetime, "datetime", { timezone })

  return (
    <time dateTime={datetime} title={title} className={className}>
      {text}
    </time>
  )
}
