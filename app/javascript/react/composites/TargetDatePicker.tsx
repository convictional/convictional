import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal, GoalSummary } from "~/react/shared/types"
import { Calendar } from "~/react/ui/Calendar"
import { Dropdown } from "~/react/ui/Dropdown"
import { formatDateOnly, formatISODate } from "~/shared/datetime"

function todayIso(): string {
  const today = new Date()
  return formatDateOnly(today.getFullYear(), today.getMonth(), today.getDate())
}

interface TargetDatePickerProps {
  goal: Goal | GoalSummary
  onGoalUpdated: (goal: Goal) => void
}

export function TargetDatePicker({ goal, onGoalUpdated }: TargetDatePickerProps) {
  async function selectDate(isoDate: string, close: () => void) {
    close()

    try {
      const updated = await apiFetch<Goal>(`/api/goals/${goal.id}?expand=subgoals&expand=parent`, {
        method: "PATCH",
        body: JSON.stringify({ target_date: isoDate }),
      })
      onGoalUpdated(updated)
    } catch {
      // Silent fail
    }
  }

  async function clearDate(close: () => void) {
    close()

    try {
      const updated = await apiFetch<Goal>(`/api/goals/${goal.id}?expand=subgoals&expand=parent`, {
        method: "PATCH",
        body: JSON.stringify({ clear_target_date: true }),
      })
      onGoalUpdated(updated)
    } catch {
      // Silent fail
    }
  }

  return (
    <Dropdown
      placement="bottom-end"
      className="dropdown-card p-3 z-50 w-64"
      trigger={
        <div className="cursor-pointer" onClick={e => e.stopPropagation()}>
          <span className={`text-sm ${goal.target_date ? "text-base-content" : "text-base-content/40"}`}>
            {goal.target_date ? formatISODate(goal.target_date) : "No date"}
          </span>
        </div>
      }
    >
      {({ close }) => (
        <>
          <Calendar
            selected={goal.target_date}
            onSelect={isoDate => void selectDate(isoDate, close)}
            isToday={iso => iso === todayIso()}
          />
          {goal.target_date && (
            <div className="mt-2 pt-2 border-t border-base-400">
              <button
                type="button"
                onClick={() => clearDate(close)}
                className="dropdown-item w-full text-left flex items-center gap-2"
              >
                <span className="material-symbols-outlined text-base">close</span>
                <span>Clear date</span>
              </button>
            </div>
          )}
        </>
      )}
    </Dropdown>
  )
}
