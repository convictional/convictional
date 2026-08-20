import { STATUS_CONFIG, STATUS_OPTIONS } from "~/react/shared/statusConfig"
import type { GoalSummary } from "../types"

interface GoalTooltipProps {
  goal: GoalSummary
  position: { left: number; top: number }
  // The tooltip is itself hoverable (it carries the "open in new" link), so the
  // shell cancels the hide timer on enter and reschedules it on leave.
  onMouseEnter(): void
  onMouseLeave(): void
}

export function GoalTooltip({ goal, position, onMouseEnter, onMouseLeave }: GoalTooltipProps) {
  // STATUS_OPTIONS[0] (on_track) is the fallback for an unknown status.
  const config = STATUS_CONFIG[goal.status] ?? STATUS_OPTIONS[0]

  return (
    <div
      className="dropdown-card w-80 p-4 flex flex-col gap-3 fixed z-50 pointer-events-auto"
      style={{ left: `${position.left}px`, top: `${position.top}px` }}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <div className="flex items-start justify-between gap-4">
        <span className="text-sm font-semibold line-clamp-2 text-balance">{goal.description || goal.name}</span>
        <div
          className={`inline-flex items-center gap-1 text-xs font-medium shrink-0 px-2 py-0.5 rounded-full border max-w-max ${config.classes}`}
        >
          <span className={`w-1.5 h-1.5 rounded-full bg-current ${config.textClass}`} />
          <span>{config.text}</span>
        </div>
      </div>
      <div className="border-t border-base-200 -mx-4" />
      <div className="flex items-center justify-between -mt-1 -mb-2">
        <div className="flex items-center gap-3 min-w-0">
          {goal.group_name && (
            <div className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-sm text-base-content/40">group</span>
              <span className="text-xs text-base-content/50">{goal.group_name}</span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <span className="material-symbols-outlined text-sm text-base-content/40">trending_up</span>
            <span className="text-xs text-base-content/50">{goal.activity} alignments</span>
          </div>
        </div>
        <a href={goal.url} className="flex items-center text-base-content/40 hover:text-base-content/70 shrink-0">
          <span className="material-symbols-outlined text-lg">open_in_new</span>
        </a>
      </div>
    </div>
  )
}
