import { useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { GoalAlignmentOverviewResponse } from "../types"

// Loads the org's goal-alignment overview (groups + ungrouped goals) for the
// circle-pack chart and card list. Read-only: the index page has no mutations.
export function useAlignmentsOverviewState() {
  const [data, setData] = useState<GoalAlignmentOverviewResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiFetch<GoalAlignmentOverviewResponse>("/api/goal_alignments")
      .then(d => {
        if (!cancelled) setData(d)
      })
      .catch(() => {
        if (!cancelled) setError(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return { data, loading, error }
}
