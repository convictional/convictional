import { useRef } from "react"

import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { EmptyState } from "~/react/ui/EmptyState"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { CirclePackChart } from "./components/CirclePackChart"
import { GoalList } from "./components/GoalList"
import { useAlignmentsOverviewState } from "./hooks/useAlignmentsOverviewState"

export function GoalAlignmentsIndex() {
  const { data, loading, error } = useAlignmentsOverviewState()
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [data])

  if (error) return <ErrorState message="Failed to load goal alignments. Please try refreshing the page." />
  if (loading || !data) return <LoadingState />

  const allGoals = [...data.groups.flatMap(group => group.goals), ...data.ungrouped_goals]

  if (allGoals.length === 0) {
    return <EmptyState title="No active goals" text="There are no active goals to show alignments for yet." />
  }

  return (
    <div ref={rootRef}>
      <CirclePackChart groups={data.groups} ungroupedGoals={data.ungrouped_goals} />
      <GoalList goals={allGoals} />
    </div>
  )
}
