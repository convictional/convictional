import { useCallback, useEffect, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { GoalAlignmentListResponse } from "../types"

// Loads the alignments list + timeline for a goal and exposes mutators.
//
// Add and delete change the server-computed timeline buckets, so they refresh()
// (a silent refetch — no loading flash) to reconcile both the card list and the
// chart. Pinning does not affect the timeline, so it updates locally and
// optimistically (reverting on error) for an instant flip.
export function useAlignmentsShowState(goalId: string) {
  const [data, setData] = useState<GoalAlignmentListResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  const fetchData = useCallback(() => apiFetch<GoalAlignmentListResponse>(`/api/goals/${goalId}/alignments`), [goalId])

  useEffect(() => {
    let cancelled = false
    fetchData()
      .then(d => {
        if (cancelled) return
        setData(d)
        setLoading(false)
      })
      .catch(() => {
        if (cancelled) return
        setError(true)
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [fetchData])

  const refresh = useCallback(async () => {
    setData(await fetchData())
  }, [fetchData])

  const setPinnedLocally = useCallback((alignmentId: string, pinned: boolean) => {
    setData(prev =>
      prev
        ? {
            ...prev,
            alignments: prev.alignments.map(a =>
              // score is 1.0 when pinned, else the ML alignment_score (the `score`
              // model property), so reflect that here to match a refetch.
              a.id === alignmentId ? { ...a, pinned, score: pinned ? 1.0 : a.alignment_score } : a
            ),
          }
        : prev
    )
  }, [])

  return { data, loading, error, refresh, setPinnedLocally }
}
