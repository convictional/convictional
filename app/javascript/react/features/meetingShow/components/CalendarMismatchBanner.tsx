export function CalendarMismatchBanner() {
  return (
    <div className="border border-warning bg-warning/10 text-warning-content rounded-md p-3 flex items-start gap-2">
      <span className="material-symbols-outlined text-warning">warning</span>
      <p className="text-sm">
        This meeting isn&apos;t linked to a calendar event, so it can&apos;t be recorded. Add it to your calendar to
        enable recording.
      </p>
    </div>
  )
}
