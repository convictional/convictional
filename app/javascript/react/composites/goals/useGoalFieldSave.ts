import { useCallback, useRef } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal, GoalSummary } from "~/react/shared/types"

// PATCHes a single goal field, reusing the show-page expand params so the returned goal keeps the
// subgoal/parent shape the rest of the page depends on. The ref guard collapses the Enter-then-blur
// double fire into a single save. Callers own the trim / skip-unchanged decision and call this only
// when there's something to persist. Errors are swallowed, matching the pickers' silent behaviour.
export function useGoalFieldSave(goal: Goal | GoalSummary, onGoalUpdated: (goal: Goal) => void) {
  const savingRef = useRef(false)

  return useCallback(
    async (field: "title" | "description", value: string) => {
      if (savingRef.current) return
      savingRef.current = true
      try {
        const updated = await apiFetch<Goal>(`/api/goals/${goal.id}?expand=subgoals&expand=parent`, {
          method: "PATCH",
          body: JSON.stringify({ [field]: value }),
        })
        onGoalUpdated(updated)
      } catch {
        // Silent fail.
      } finally {
        savingRef.current = false
      }
    },
    [goal.id, onGoalUpdated]
  )
}
