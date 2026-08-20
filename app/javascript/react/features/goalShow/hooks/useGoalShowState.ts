import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import type { Goal, MailboxEntryResponse } from "~/react/shared/types"

import { type GoalShowData, goalQueryKey, goalQueryOptions } from "../queries"

export function useGoalShowState(goalId: string, mailboxEntryId?: string) {
  const queryClient = useQueryClient()
  const query = useQuery(goalQueryOptions(goalId, mailboxEntryId))

  const patch = useCallback(
    (fn: (old: GoalShowData) => GoalShowData) => {
      queryClient.setQueryData<GoalShowData>(goalQueryKey(goalId, mailboxEntryId), old => (old ? fn(old) : old))
    },
    [queryClient, goalId, mailboxEntryId]
  )

  // The header pickers and dropdowns PATCH the goal and get the full resource
  // back, so their response is the new cache value — no refetch. Writing under
  // `goal` leaves the sibling mailbox entry untouched.
  const handleGoalUpdated = useCallback((updated: Goal) => patch(old => ({ ...old, goal: updated })), [patch])

  const setMailboxEntry = useCallback(
    (next: MailboxEntryResponse) => patch(old => ({ ...old, mailboxEntry: next })),
    [patch]
  )

  // Re-read the goal after an out-of-band change the response body can't supply.
  // Reactivate is the case: POST /api/goals/{id}/reactivate returns a GoalResponse,
  // but its expansions come from that request's own `expand` query param — the
  // actions menu sends none, so feeding its body to the cache would blank `parent`
  // and `subgoals`. Invalidating re-runs the show query, which carries them.
  const refetchGoal = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: goalQueryKey(goalId, mailboxEntryId) })
  }, [queryClient, goalId, mailboxEntryId])

  return {
    goal: query.data?.goal ?? null,
    mailboxEntry: query.data?.mailboxEntry ?? null,
    setMailboxEntry,
    loading: query.isLoading,
    error: query.isError,
    handleGoalUpdated,
    refetchGoal,
  }
}
