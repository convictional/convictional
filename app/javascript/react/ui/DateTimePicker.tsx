import { useEffect, useState } from "react"

import { Calendar } from "~/react/ui/Calendar"
import { combineDateTimeToIso, isoDateInZone, nextHourTimeInZone } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"

interface DateTimePickerProps {
  // Interprets the chosen wall-clock date/time and anchors "today"; browser-local when null.
  timezone: string | null
  // Gates calendar days. Receives the ticking `nowMs` so callers compare against a live clock
  // without owning the interval; callers close over their own bounds (e.g. a 30-day horizon).
  isDayDisabled: (dayIso: string, nowMs: number) => boolean
  // Whether the chosen instant may be confirmed. `ms` is null until both date and time are
  // picked; `nowMs` is the reference clock.
  isConfirmable: (ms: number | null, nowMs: number) => boolean
  // Why the current selection can't be confirmed, surfaced as a tooltip on the confirm
  // button so it isn't silently un-clickable (e.g. a past time-of-day on today reads as
  // "nothing's stopping me"). Returns null when there's nothing to say. Domain-specific —
  // callers supply it; the same `ms`/`nowMs` the button gates on.
  validationMessage?: (ms: number | null, nowMs: number) => string | null
  confirmLabel: string
  onConfirm: (iso: string) => void
}

// Calendar grid + native time control that emits a tz-aware ISO instant. Domain-free: the
// day-disable and confirmable rules are supplied by callers, so scheduling (30-day horizon)
// and snooze (unbounded) share one picker. See sendLaterSchedule.ts / snoozeSchedule.ts.
export function DateTimePicker({
  timezone,
  isDayDisabled,
  isConfirmable,
  validationMessage,
  confirmLabel,
  onConfirm,
}: DateTimePickerProps) {
  const [selectedDate, setSelectedDate] = useState<string | null>(null)
  // Seed with the next full hour (in the user's tz) so selecting today lands on a valid
  // future time instead of opening on a past default like a fixed 09:00.
  const [time, setTime] = useState(() => nextHourTimeInZone(new Date(), timezone))
  // Seed "now" from the clock once (lazy init, so the grid anchors on today from the first
  // render) and refresh it each minute so past days/times disable as time passes.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 60_000)
    return () => window.clearInterval(interval)
  }, [])

  // Today's date in the user's timezone so the grid's "today" highlight and opening month
  // agree with the same zone isDayDisabled gates on — a browser-local date would drift a day
  // when the two zones straddle a date boundary.
  const todayIso = isoDateInZone(new Date(now), timezone)

  // A cleared time input yields "", which combineDateTimeToIso would silently read as
  // midnight; require both a date and a time so the button stays disabled until picked.
  const chosenIso = selectedDate && time ? combineDateTimeToIso(selectedDate, time, timezone) : null
  const chosenMs = chosenIso ? new Date(chosenIso).getTime() : null
  const message = validationMessage?.(chosenMs, now) ?? null
  const canConfirm = isConfirmable(chosenMs, now)

  return (
    <div className="p-2">
      <Calendar
        selected={selectedDate}
        onSelect={setSelectedDate}
        defaultMonth={todayIso}
        isDisabled={iso => isDayDisabled(iso, now)}
        isToday={iso => iso === todayIso}
      />
      <div className="mt-2 pt-2 border-t border-base-400 flex items-center gap-2">
        {/* Hide Chrome's native picker clock — Safari/Firefox render none, and it overlapped
            the value in the narrow popover. Matches the [&::-webkit-scrollbar] pattern in
            GifPicker. Time is still editable by typing or the spinner arrows. */}
        <input
          type="time"
          value={time}
          onChange={e => setTime(e.target.value)}
          className="input input-sm input-bordered flex-1 [&::-webkit-calendar-picker-indicator]:hidden"
          aria-label="Time"
        />
        {/* The button's disabled state reads the ticking `now`, but the click re-checks
            against a fresh clock: `now` lags by up to a minute, so a near-term pick could
            otherwise pass the gate yet post a time the server has already moved past. */}
        {/* Swap to btn-disabled rather than leaning on :disabled — this theme doesn't dim a
            disabled btn-primary, so it reads as clickable (and still shows a press animation)
            even while the disabled attribute blocks it. Matches SendMenu/ComposerFooter.
            Tooltip explains why; it wraps the button in a span, so hover still fires even
            though the disabled button itself wouldn't. Renders bare when message is null. */}
        <Tooltip content={message} placement="top">
          <button
            type="button"
            className={`btn btn-sm ${canConfirm ? "btn-primary" : "btn-disabled"}`}
            disabled={!canConfirm}
            onClick={() => chosenIso && isConfirmable(chosenMs, Date.now()) && onConfirm(chosenIso)}
          >
            {confirmLabel}
          </button>
        </Tooltip>
      </div>
    </div>
  )
}
