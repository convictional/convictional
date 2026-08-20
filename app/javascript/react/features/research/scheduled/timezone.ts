export function formatTimezoneAbbr(timezone: string | null): string {
  const tz = timezone || "UTC"
  try {
    const part = new Intl.DateTimeFormat("en-US", { timeZone: tz, timeZoneName: "short" })
      .formatToParts(new Date())
      .find(p => p.type === "timeZoneName")
    return part?.value || tz
  } catch {
    return tz
  }
}
