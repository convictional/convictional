import { apiFetch } from "~/react/shared/apiFetch"
import { STATUS_OPTIONS } from "~/react/shared/statusConfig"
import type { Goal, GoalSummary } from "~/react/shared/types"

import { Dropdown } from "~/react/ui/Dropdown"

interface BaseStatusDropdownProps {
  status: string
  isCompleted: boolean
  onSelect: (value: string) => void
}

export function BaseStatusDropdown({ status, isCompleted, onSelect }: BaseStatusDropdownProps) {
  const currentConfig = isCompleted ? null : (STATUS_OPTIONS.find(s => s.value === status) ?? STATUS_OPTIONS[0])

  const trigger = isCompleted ? (
    <button
      type="button"
      className="inline-flex items-center gap-2 text-sm font-medium cursor-pointer hover:opacity-80 transition-opacity whitespace-nowrap shrink-0 text-success-content"
    >
      <span className="material-symbols-outlined text-base">check</span>
      <span>Complete</span>
      <span className="material-symbols-outlined text-sm leading-none">expand_more</span>
    </button>
  ) : (
    <button
      type="button"
      className={`inline-flex items-center gap-2 text-sm font-medium cursor-pointer hover:opacity-80 transition-opacity whitespace-nowrap shrink-0 ${currentConfig!.textClass}`}
    >
      <span>{currentConfig!.text}</span>
      <span className="material-symbols-outlined text-sm leading-none">expand_more</span>
    </button>
  )

  return (
    <Dropdown placement="bottom-start" trigger={trigger}>
      {({ close }) => {
        const selectStatus = (value: string) => {
          close()
          onSelect(value)
        }

        return (
          <ul className="menu p-2">
            {STATUS_OPTIONS.map(option => (
              <li key={option.value}>
                <button
                  type="button"
                  className="flex items-center gap-2 w-full px-4 py-2"
                  onClick={() => selectStatus(option.value)}
                >
                  <span>{option.text}</span>
                </button>
              </li>
            ))}
            <li>
              <button
                type="button"
                className="flex items-center gap-2 w-full px-4 py-2"
                onClick={() => selectStatus("complete")}
              >
                <span className="material-symbols-outlined text-base">check</span>
                <span>Complete</span>
              </button>
            </li>
          </ul>
        )
      }}
    </Dropdown>
  )
}

interface StatusDropdownProps {
  goal: Goal | GoalSummary
  onGoalUpdated: (goal: Goal) => void
}

export function StatusDropdown({ goal, onGoalUpdated }: StatusDropdownProps) {
  async function handleSelect(statusValue: string) {
    const isComplete = statusValue === "complete"
    const payload: Record<string, unknown> = { is_completed: isComplete }
    if (!isComplete) payload.status = statusValue

    try {
      const updated = await apiFetch<Goal>(`/api/goals/${goal.id}?expand=subgoals&expand=parent`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
      onGoalUpdated(updated)
    } catch {
      // Intentionally silent — status update failures are not surfaced to the UI
    }
  }

  return <BaseStatusDropdown status={goal.status} isCompleted={goal.is_completed} onSelect={handleSelect} />
}
