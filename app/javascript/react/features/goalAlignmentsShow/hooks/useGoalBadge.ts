import { useEffect, useState } from "react"

import type { GoalBadgeGoal } from "~/react/composites/goals/GoalBadge"
import { apiFetch } from "~/react/shared/apiFetch"

// Loads the goal for the header badge. A failure leaves the badge unrendered
// rather than blocking the page — the alignments section surfaces page-level
// errors of its own.
export function useGoalBadge(goalId: string) {
  const [goal, setGoal] = useState<GoalBadgeGoal | null>(null)

  useEffect(() => {
    let cancelled = false
    apiFetch<GoalBadgeGoal>(`/api/goals/${goalId}?expand=parent`)
      .then(g => {
        if (!cancelled) setGoal(g)
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [goalId])

  return goal
}
