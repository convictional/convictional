import { useMemo, useState } from "react"

import { formatDateOnly, parseDateOnly } from "~/shared/datetime"

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
]

const DAY_NAMES = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]

interface CalendarProps {
  // The selected day as an ISO date (YYYY-MM-DD), or null when nothing is picked.
  selected: string | null
  // Emits the clicked day as an ISO date (YYYY-MM-DD).
  onSelect: (isoDate: string) => void
  // Per-day predicates keyed by ISO date. Disabled days can't be clicked; today
  // gets a subtle highlight. Omitted predicates treat every day as enabled / not-today.
  isDisabled?: (isoDate: string) => boolean
  isToday?: (isoDate: string) => boolean
  // Month to open on when nothing is selected, as an ISO date (YYYY-MM-DD).
  // Lets a caller anchor on "today" in the user's timezone; defaults to the
  // browser-local current month.
  defaultMonth?: string
}

function monthOf(isoDate: string | null): { year: number; month: number } {
  if (isoDate) {
    const { year, month } = parseDateOnly(isoDate)
    return { year, month }
  }
  const today = new Date()
  return { year: today.getFullYear(), month: today.getMonth() }
}

// Month-grid date picker: header with month navigation, weekday labels, and a
// grid of day cells. Purely presentational — callers own selection state and the
// meaning of disabled/today via predicates.
export function Calendar({ selected, onSelect, isDisabled, isToday, defaultMonth }: CalendarProps) {
  const [viewMonth, setViewMonth] = useState(() => monthOf(selected ?? defaultMonth ?? null))

  const { daysInMonth, blankDays } = useMemo(() => {
    const totalDays = new Date(viewMonth.year, viewMonth.month + 1, 0).getDate()
    const firstDayOfWeek = new Date(viewMonth.year, viewMonth.month, 1).getDay()
    return {
      daysInMonth: Array.from({ length: totalDays }, (_, i) => i + 1),
      blankDays: Array.from({ length: firstDayOfWeek }, (_, i) => i),
    }
  }, [viewMonth])

  function prevMonth() {
    setViewMonth(prev =>
      prev.month === 0 ? { year: prev.year - 1, month: 11 } : { year: prev.year, month: prev.month - 1 }
    )
  }

  function nextMonth() {
    setViewMonth(prev =>
      prev.month === 11 ? { year: prev.year + 1, month: 0 } : { year: prev.year, month: prev.month + 1 }
    )
  }

  return (
    <>
      <div className="flex justify-between items-center mb-2">
        <div>
          <span className="text-sm font-bold">{MONTH_NAMES[viewMonth.month]}</span>
          <span className="ml-1 text-sm font-normal opacity-60">{viewMonth.year}</span>
        </div>
        <div className="flex gap-1">
          <button onClick={prevMonth} type="button" className="btn btn-ghost btn-xs btn-square">
            <span className="material-symbols-outlined text-base">chevron_left</span>
          </button>
          <button onClick={nextMonth} type="button" className="btn btn-ghost btn-xs btn-square">
            <span className="material-symbols-outlined text-base">chevron_right</span>
          </button>
        </div>
      </div>
      <div className="grid grid-cols-7 mb-2 gap-1">
        {DAY_NAMES.map(day => (
          <div key={day} className="text-xs font-medium text-center opacity-60">
            {day}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {blankDays.map(i => (
          <div key={`blank-${i}`} className="aspect-square" />
        ))}
        {daysInMonth.map(day => {
          const iso = formatDateOnly(viewMonth.year, viewMonth.month, day)
          const selectedCell = iso === selected
          const disabledCell = isDisabled?.(iso) ?? false
          const todayCell = isToday?.(iso) ?? false
          return (
            <div key={day} className="aspect-square">
              <button
                type="button"
                disabled={disabledCell}
                onClick={() => onSelect(iso)}
                className={`w-full h-full flex items-center justify-center text-sm rounded ${
                  selectedCell
                    ? "bg-primary text-primary-content hover:bg-primary/80"
                    : disabledCell
                      ? "opacity-30 cursor-not-allowed"
                      : todayCell
                        ? "bg-base-200 cursor-pointer hover:bg-base-200"
                        : "hover:bg-base-200 cursor-pointer"
                }`}
              >
                {day}
              </button>
            </div>
          )
        })}
      </div>
    </>
  )
}
