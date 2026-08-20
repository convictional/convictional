import { openResearchDialog } from "~/react/features/research/dialog/hooks/useResearchDialog"

import { ScheduledResearchFrequency, type ScheduledResearch } from "../types"

interface Props {
  schedule: ScheduledResearch
  tzAbbr: string
}

export const SCHEDULE_ROW_GRID_COLS = "grid-cols-[1fr_240px_180px]"

const DAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

function formatHour(hour: number): string {
  const suffix = hour < 12 ? "AM" : "PM"
  const display = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour
  return `${display} ${suffix}`
}

function formatSchedule(schedule: ScheduledResearch, tzAbbr: string): string {
  const hour = `${formatHour(schedule.hour)} ${tzAbbr}`
  if (schedule.frequency === ScheduledResearchFrequency.DAILY) return `Daily at ${hour}`
  if (schedule.frequency === ScheduledResearchFrequency.WEEKDAYS) return `Weekdays at ${hour}`
  const dayIdx = Number(schedule.day_of_week ?? "1")
  const dayName = DAY_NAMES[dayIdx] ?? "Monday"
  return `Weekly, ${dayName}s at ${hour}`
}

function formatDelivered(lastDeliveredAt: string): string {
  const date = new Date(lastDeliveredAt)
  const diffMs = Date.now() - date.getTime()
  const minute = 60_000
  const hour = 3_600_000
  const day = 86_400_000
  if (diffMs < minute) return "delivered just now"
  if (diffMs < hour) return `delivered ${Math.floor(diffMs / minute)}m ago`
  if (diffMs < day) return `delivered ${Math.floor(diffMs / hour)}h ago`
  if (diffMs < 7 * day) return `delivered ${Math.floor(diffMs / day)}d ago`
  return `delivered ${date.toLocaleDateString()}`
}

function formatNextRun(nextRunAt: string): string {
  const date = new Date(nextRunAt)
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })
}

export function ScheduleRow({ schedule, tzAbbr }: Props) {
  const isPreparing = schedule.title === "Untitled" && !schedule.preparation_failed_at
  const hasPreparationFailure = !!schedule.preparation_failed_at
  const nextRun = schedule.next_run_at ? formatNextRun(schedule.next_run_at) : null
  const delivered = schedule.last_delivered_at ? formatDelivered(schedule.last_delivered_at) : null

  const handleClick = () => {
    openResearchDialog({ mode: "schedule", schedule })
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      data-testid="scheduled-research-row"
      className={`grid ${SCHEDULE_ROW_GRID_COLS} w-full text-left border-b border-base-300 hover:bg-base-200/60 transition-colors cursor-pointer`}
    >
      <div className="flex items-center gap-2 px-4 py-3 min-w-0">
        <span className="truncate text-base" data-testid="scheduled-research-row-title">
          {schedule.title}
        </span>
        {isPreparing && (
          <span
            className="shrink-0 text-xs text-base-content/40 animate-pulse"
            data-testid="scheduled-research-row-preparing"
          >
            title in progress…
          </span>
        )}
        {hasPreparationFailure && (
          <span
            className="shrink-0 text-xs text-warning"
            title="Edit and resave the prompt to retry preparation"
            data-testid="scheduled-research-row-failed"
          >
            preparation failed
          </span>
        )}
      </div>
      <div className="flex items-center px-4 py-3 text-sm text-base-content/70">
        {formatSchedule(schedule, tzAbbr)}
      </div>
      <div className="flex flex-col justify-center px-4 py-3 text-sm text-base-content/70">
        {nextRun ? <span>{nextRun}</span> : <span className="text-base-content/40">—</span>}
        {delivered && <span className="text-xs text-base-content/50">{delivered}</span>}
      </div>
    </button>
  )
}
