import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core"
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { type ReactNode, useMemo, useState } from "react"

import type { Goal, Group, GoalSummary, User } from "~/react/shared/types"
import { SortableSubgoalRow } from "./SortableSubgoalRow"
import { SubgoalSummaryRow } from "./SubgoalSummaryRow"

export function reorderSubgoals(goal: Goal, activeId: string, overId: string): GoalSummary[] | null {
  if (activeId === overId) return null
  const subgoals = goal.subgoals ?? []
  const oldIndex = subgoals.findIndex(s => s.id === activeId)
  const newIndex = subgoals.findIndex(s => s.id === overId)
  if (oldIndex === -1 || newIndex === -1) return null
  return arrayMove(subgoals, oldIndex, newIndex)
}

function SortableSubgoalList({
  subgoals,
  onDragEnd,
  children,
}: {
  subgoals: GoalSummary[]
  onDragEnd: (activeId: string, overId: string) => void
  children: ReactNode
}) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event
    if (over && active.id !== over.id) {
      onDragEnd(String(active.id), String(over.id))
    }
  }

  const ids = useMemo(() => subgoals.map(s => s.id), [subgoals])

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={ids} strategy={verticalListSortingStrategy}>
        <ol>{children}</ol>
      </SortableContext>
    </DndContext>
  )
}

interface SortableSubgoalEditListProps {
  subgoals: GoalSummary[]
  isPlanningList: boolean
  isSortEnabled: boolean
  isClosed: boolean
  organizationUsers: User[]
  organizationGroups: Group[]
  onGoalUpdated: (goal: Goal) => void
  onGoalRemoved: (goalId: string) => void
  onDragEnd: (activeId: string, overId: string) => void
  openCommentsGoalId: string | null
  onToggleComments: (goalId: string | null) => void
}

export function SortableSubgoalEditList({
  subgoals,
  isPlanningList,
  isSortEnabled,
  isClosed,
  organizationUsers,
  organizationGroups,
  onGoalUpdated,
  onGoalRemoved,
  onDragEnd,
  openCommentsGoalId,
  onToggleComments,
}: SortableSubgoalEditListProps) {
  return (
    <SortableSubgoalList subgoals={subgoals} onDragEnd={onDragEnd}>
      {subgoals.map(subgoal => (
        <SortableSubgoalRow
          key={subgoal.id}
          subgoal={subgoal}
          isPlanningList={isPlanningList}
          isSortEnabled={isSortEnabled}
          isClosed={isClosed}
          organizationUsers={organizationUsers}
          organizationGroups={organizationGroups}
          onGoalUpdated={onGoalUpdated}
          onGoalRemoved={onGoalRemoved}
          openCommentsGoalId={openCommentsGoalId}
          onToggleComments={onToggleComments}
        />
      ))}
    </SortableSubgoalList>
  )
}

interface SortableSubgoalSummaryListProps {
  subgoals: GoalSummary[]
  isSortEnabled: boolean
  isClosed: boolean
  organizationUsers: User[]
  organizationGroups: Group[]
  onGoalUpdated: (goal: Goal) => void
  onGoalRemoved: (goalId: string) => void
  onDragEnd: (activeId: string, overId: string) => void
  openCommentsGoalId: string | null
  onToggleComments: (goalId: string | null) => void
}

export function SortableSubgoalSummaryList({
  subgoals,
  isSortEnabled,
  isClosed,
  organizationUsers,
  organizationGroups,
  onGoalUpdated,
  onGoalRemoved,
  onDragEnd,
  openCommentsGoalId,
  onToggleComments,
}: SortableSubgoalSummaryListProps) {
  const [editingSubgoalId, setEditingSubgoalId] = useState<string | null>(null)

  return (
    <SortableSubgoalList subgoals={subgoals} onDragEnd={onDragEnd}>
      {subgoals.map(subgoal =>
        editingSubgoalId === subgoal.id ? (
          <SortableSubgoalRow
            key={subgoal.id}
            subgoal={subgoal}
            isPlanningList={false}
            isSortEnabled={isSortEnabled}
            isClosed={isClosed}
            organizationUsers={organizationUsers}
            organizationGroups={organizationGroups}
            onGoalUpdated={onGoalUpdated}
            onGoalRemoved={onGoalRemoved}
            openCommentsGoalId={openCommentsGoalId}
            onToggleComments={onToggleComments}
            onExitEdit={() => setEditingSubgoalId(null)}
          />
        ) : (
          <SubgoalSummaryRow
            key={subgoal.id}
            subgoal={subgoal}
            isSortEnabled={isSortEnabled}
            isClosed={isClosed}
            onGoalRemoved={onGoalRemoved}
            openCommentsGoalId={openCommentsGoalId}
            onToggleComments={onToggleComments}
            onStartEditing={() => setEditingSubgoalId(subgoal.id)}
          />
        )
      )}
    </SortableSubgoalList>
  )
}
