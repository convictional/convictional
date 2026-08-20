import { useRef } from "react"

import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"

import { formatTimezoneAbbr } from "../timezone"
import { ScheduledResearchFrequency } from "../types"

const PROFILE_SETTINGS_PATH = "/profile/edit"

export interface FormState {
  prompt: string
  frequency: ScheduledResearchFrequency
  hour: number
  day_of_week: string
}

interface Props {
  state: FormState
  onChange: (next: FormState) => void
  timezone: string | null
}

const FREQUENCY_TABS: { value: ScheduledResearchFrequency; label: string }[] = [
  { value: ScheduledResearchFrequency.WEEKLY, label: "Weekly" },
  { value: ScheduledResearchFrequency.DAILY, label: "Daily" },
  { value: ScheduledResearchFrequency.WEEKDAYS, label: "Weekdays" },
]

const DAYS: { value: string; label: string }[] = [
  { value: "0", label: "Sunday" },
  { value: "1", label: "Monday" },
  { value: "2", label: "Tuesday" },
  { value: "3", label: "Wednesday" },
  { value: "4", label: "Thursday" },
  { value: "5", label: "Friday" },
  { value: "6", label: "Saturday" },
]

const HOURS: { value: number; label: string }[] = Array.from({ length: 24 }, (_, h) => {
  const suffix = h < 12 ? "AM" : "PM"
  const display = h === 0 ? 12 : h > 12 ? h - 12 : h
  return { value: h, label: `${display}:00 ${suffix}` }
})

// An inline <select> styled to blend with surrounding text as a clickable token.
function InlineSelect<T extends string | number>({
  value,
  onChange,
  options,
  ariaLabel,
  className,
}: {
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
  ariaLabel: string
  className?: string
}) {
  return (
    <select
      aria-label={ariaLabel}
      value={value}
      onChange={e => {
        const raw = e.target.value
        onChange((typeof value === "number" ? Number(raw) : raw) as T)
      }}
      className={
        className ??
        "bg-transparent border-0 py-0 pl-1 pr-5 font-medium text-base-content hover:bg-base-200 rounded-md focus:outline-none focus:bg-base-200 cursor-pointer"
      }
    >
      {options.map(o => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

export function ScheduleFormFields({ state, onChange, timezone }: Props) {
  const isMobile = useIsMobile()
  // Boost the timezone/settings link so it's a same-realm nav instead of a hard
  // reload that strands the realm (#8744); this renders inside a portal htmx never
  // scanned, so process it once mounted.
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef)
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    onChange({ ...state, [key]: value })
  }

  const dayWord =
    state.frequency === ScheduledResearchFrequency.DAILY
      ? "day"
      : state.frequency === ScheduledResearchFrequency.WEEKDAYS
        ? "weekday"
        : null
  const tzAbbr = formatTimezoneAbbr(timezone)
  const tzTooltip = timezone
    ? `Schedule runs in ${timezone}. Click to change in settings.`
    : "Set your timezone in settings so schedules run in your local time."

  const tabClass = isMobile ? "px-3 py-1.5 rounded-full text-sm" : "px-3 py-1 rounded-full text-xs"

  const selectClass = isMobile
    ? "bg-transparent border border-base-300 py-1.5 pl-2 pr-6 font-medium text-base-content rounded-full focus:outline-none cursor-pointer text-sm"
    : "bg-transparent border border-base-300 py-0.5 pl-2 pr-6 font-medium text-base-content hover:bg-base-200 rounded-full focus:outline-none focus:bg-base-200 cursor-pointer"

  const textClass = isMobile ? "text-sm" : "text-sm"

  return (
    <div ref={rootRef} className={isMobile ? "space-y-3" : "space-y-2"}>
      <div
        role="tablist"
        aria-label="Frequency"
        className={
          isMobile
            ? "flex items-center gap-1"
            : "inline-flex items-center gap-0.5 rounded-full border border-base-300 bg-base-200/40 p-0.5"
        }
      >
        {FREQUENCY_TABS.map(tab => {
          const selected = state.frequency === tab.value
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => set("frequency", tab.value)}
              className={`${tabClass} transition-colors cursor-pointer ${
                selected
                  ? isMobile
                    ? "bg-primary/10 text-primary font-medium"
                    : "bg-base-100 text-base-content font-medium shadow-xs"
                  : isMobile
                    ? "text-base-content/50 active:text-base-content/70"
                    : "text-base-content/50 hover:text-base-content"
              }`}
            >
              {tab.label}
            </button>
          )
        })}
      </div>
      <div className={`flex flex-wrap items-center gap-x-1.5 gap-y-2 ${textClass} text-base-content/70`}>
        <span>Every</span>
        {dayWord ? (
          <span className="font-medium text-base-content">{dayWord}</span>
        ) : (
          <InlineSelect
            ariaLabel="Day of week"
            value={state.day_of_week}
            onChange={v => set("day_of_week", v)}
            options={DAYS}
            className={selectClass}
          />
        )}
        <span>at</span>
        <InlineSelect
          ariaLabel="Hour"
          value={state.hour}
          onChange={v => set("hour", v)}
          options={HOURS}
          className={selectClass}
        />
        <a
          href={PROFILE_SETTINGS_PATH}
          title={tzTooltip}
          aria-label={tzTooltip}
          className="text-base-content/60 hover:text-base-content hover:underline"
          data-testid="schedule-form-timezone"
        >
          {tzAbbr}
        </a>
      </div>
    </div>
  )
}
