import dayjs from "dayjs"
import utc from "dayjs/plugin/utc"

dayjs.extend(utc)

// Date-only utilities (no timezone conversion)
// Use these for DateField (not DateTimeField) to avoid timezone issues

/**
 * Parses an ISO date string (YYYY-MM-DD) into year, month (0-indexed), day components
 * without any timezone conversion.
 */
export function parseDateOnly(isoDate: string): { year: number; month: number; day: number } {
  const parts = isoDate.split("-")
  return {
    year: parseInt(parts[0], 10),
    month: parseInt(parts[1], 10) - 1, // JS months are 0-indexed
    day: parseInt(parts[2], 10),
  }
}

/**
 * Formats year, month (0-indexed), day into ISO date string (YYYY-MM-DD)
 * without any timezone conversion.
 */
export function formatDateOnly(year: number, month: number, day: number): string {
  const monthStr = String(month + 1).padStart(2, "0") // Convert 0-indexed to 1-indexed
  const dayStr = String(day).padStart(2, "0")
  return `${year}-${monthStr}-${dayStr}`
}

/**
 * Formats a date object to a human-readable string (e.g., "Jan 15, 2026")
 */
export function formatDateDisplay(year: number, month: number, day: number): string {
  // Use dayjs in UTC mode to avoid any timezone shifts
  // Note: month is 0-indexed, day is 1-indexed
  return dayjs.utc().year(year).month(month).date(day).format("MMM DD, YYYY")
}

/**
 * Formats an ISO date string (YYYY-MM-DD) to a human-readable string (e.g., "Jan 15, 2026")
 */
export function formatISODate(iso: string): string {
  const [year, month, day] = iso.split("-")
  const date = new Date(Number(year), Number(month) - 1, Number(day))
  return date.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" })
}
