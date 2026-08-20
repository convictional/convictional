import { useState } from "react"

import type { Goal, Group, GoalSummary, User } from "~/react/shared/types"
import { GoalEditRow } from "./GoalEditRow"
import { GoalSummaryRow } from "./GoalSummaryRow"

interface GoalIndexRowProps {
  goal: Goal
  isSortEnabled: boolean
  isHighlighted?: boolean
  organizationUsers: User[]
  organizationGroups: Group[]
  onGoalUpdated: (goal: Goal) => void
  onGoalRemoved: (goalId: string) => void
  onReorderSubgoals: (parentId: string, subgoals: GoalSummary[]) => void
  openCommentsGoalId: string | null
  onToggleComments: (goalId: string | null) => void
}

export function GoalIndexRow({
  goal,
  isSortEnabled,
  isHighlighted,
  organizationUsers,
  organizationGroups,
  onGoalUpdated,
  onGoalRemoved,
  onReorderSubgoals,
  openCommentsGoalId,
  onToggleComments,
}: GoalIndexRowProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [isExpanded, setIsExpanded] = useState(true)
  const [prevHighlighted, setPrevHighlighted] = useState(isHighlighted)
  if (isHighlighted !== prevHighlighted) {
    setPrevHighlighted(isHighlighted)
    if (isHighlighted) setIsExpanded(true)
  }

  if (isEditing) {
    return (
      <GoalEditRow
        goal={goal}
        isPlanningList={false}
        isSortEnabled={isSortEnabled}
        isHighlighted={isHighlighted}
        isExpanded={isExpanded}
        onToggleExpanded={() => setIsExpanded(e => !e)}
        organizationUsers={organizationUsers}
        organizationGroups={organizationGroups}
        onGoalUpdated={onGoalUpdated}
        onGoalRemoved={onGoalRemoved}
        onReorderSubgoals={onReorderSubgoals}
        openCommentsGoalId={openCommentsGoalId}
        onToggleComments={onToggleComments}
        onExitEdit={() => setIsEditing(false)}
        summarySubgoals
      />
    )
  }

  return (
    <GoalSummaryRow
      goal={goal}
      isSortEnabled={isSortEnabled}
      isHighlighted={isHighlighted}
      isExpanded={isExpanded}
      onToggleExpanded={() => setIsExpanded(e => !e)}
      organizationUsers={organizationUsers}
      organizationGroups={organizationGroups}
      onGoalUpdated={onGoalUpdated}
      onGoalRemoved={onGoalRemoved}
      onReorderSubgoals={onReorderSubgoals}
      openCommentsGoalId={openCommentsGoalId}
      onToggleComments={onToggleComments}
      onStartEditing={() => setIsEditing(true)}
    />
  )
}
