import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { useState } from "react"

import { CommentsPanel } from "~/react/composites/CommentsPanel"
import { GoalDescriptionEditor } from "~/react/composites/goals/GoalDescriptionEditor"
import { GroupPicker } from "~/react/composites/GroupPicker"
import { OwnerPicker } from "~/react/composites/OwnerPicker"
import { StatusDropdown } from "~/react/composites/StatusDropdown"
import { TargetDatePicker } from "~/react/composites/TargetDatePicker"
import type { Group, User, Goal, GoalSummary } from "~/react/shared/types"
import { GoalCreationRow } from "./GoalCreationRow"
import { RowActions } from "./RowActions"
import { reorderSubgoals, SortableSubgoalEditList, SortableSubgoalSummaryList } from "./SortableSubgoalList"

interface GoalEditRowProps {
  goal: Goal
  isPlanningList: boolean
  isSortEnabled: boolean
  isHighlighted?: boolean
  defaultExpanded?: boolean
  isExpanded?: boolean
  onToggleExpanded?: () => void
  organizationUsers: User[]
  organizationGroups: Group[]
  onGoalUpdated: (goal: Goal) => void
  onGoalRemoved: (goalId: string) => void
  onReorderSubgoals: (parentId: string, subgoals: GoalSummary[]) => void
  openCommentsGoalId: string | null
  onToggleComments: (goalId: string | null) => void
  onExitEdit?: () => void
  summarySubgoals?: boolean
}

export function GoalEditRow({
  goal,
  isPlanningList,
  isSortEnabled,
  isHighlighted,
  defaultExpanded = false,
  isExpanded: controlledExpanded,
  onToggleExpanded,
  organizationUsers,
  organizationGroups,
  onGoalUpdated,
  onGoalRemoved,
  onReorderSubgoals,
  openCommentsGoalId,
  onToggleComments,
  onExitEdit,
  summarySubgoals = false,
}: GoalEditRowProps) {
  const [localExpanded, setLocalExpanded] = useState(isHighlighted ?? defaultExpanded)
  const [prevHighlighted, setPrevHighlighted] = useState(isHighlighted)
  if (isHighlighted !== prevHighlighted) {
    setPrevHighlighted(isHighlighted)
    if (isHighlighted && !onToggleExpanded) setLocalExpanded(true)
  }

  const isExpanded = controlledExpanded ?? localExpanded
  const toggleExpanded = onToggleExpanded ?? (() => setLocalExpanded(e => !e))

  const [isCreatingSubgoal, setIsCreatingSubgoal] = useState(false)
  const isCommentsOpen = openCommentsGoalId === goal.id
  // The index always fetches with `?expand=subgoals`, so `goal.subgoals` is
  // populated. The `?? []` keeps the type checker happy without sprinkling
  // null-checks at every read site.
  const subgoals = goal.subgoals ?? []

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: goal.id,
    disabled: !isSortEnabled,
  })

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : undefined,
  }

  function handleSubgoalDragEnd(activeId: string, overId: string) {
    const reordered = reorderSubgoals(goal, activeId, overId)
    if (reordered) onReorderSubgoals(goal.id, reordered)
  }

  return (
    <li ref={setNodeRef} style={style} id={`goal-${goal.id}`} className="pl-10 -ml-10">
      <div className="relative">
        <div
          className={`grid grid-cols-[32px_1fr_48px] md:grid-cols-[32px_1fr_180px_160px_48px] hover:bg-base-200/50 group border-b border-base-300 relative${isHighlighted ? " goal-highlight" : isCommentsOpen ? " bg-base-200/50" : ""}`}
        >
          {isSortEnabled && (
            <span
              {...attributes}
              {...listeners}
              className="material-symbols-outlined cursor-grab text-lg text-base-content/40 hover:text-base-content/60 absolute left-0 top-1/2 -translate-y-1/2 -translate-x-full px-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
            >
              drag_indicator
            </span>
          )}
          <div className="flex">
            {subgoals.length > 0 ? (
              <button
                type="button"
                onClick={toggleExpanded}
                className="cursor-pointer hover:bg-base-200 px-2 py-3 text-base-content/60 hover:text-base-content transition-colors"
              >
                <span
                  className={`material-symbols-outlined text-base inline-block transition-transform ${isExpanded ? "rotate-90" : ""}`}
                >
                  chevron_right
                </span>
              </button>
            ) : (
              <div className="px-2 py-3 w-5" />
            )}
          </div>
          <div className="flex items-center relative">
            <GoalDescriptionEditor goal={goal} onGoalUpdated={onGoalUpdated} />
          </div>
          <div className="hidden md:flex px-4 py-4 flex-col gap-2">
            <OwnerPicker goal={goal} users={organizationUsers} onGoalUpdated={onGoalUpdated} />
            <GroupPicker goal={goal} groups={organizationGroups} onGoalUpdated={onGoalUpdated} />
          </div>
          <div className="hidden md:flex px-4 py-4 flex-col items-start gap-3">
            {!isPlanningList && <StatusDropdown goal={goal} onGoalUpdated={onGoalUpdated} />}
            <TargetDatePicker goal={goal} onGoalUpdated={onGoalUpdated} />
          </div>
          <RowActions
            goal={goal}
            isCommentsOpen={isCommentsOpen}
            onToggleComments={onToggleComments}
            onGoalRemoved={onGoalRemoved}
            editButton={onExitEdit ? { mode: "exit", onExitEdit } : undefined}
            actionsMenuProps={{ onActivate: () => onGoalRemoved(goal.id) }}
          />
          <div className="order-1 col-span-full flex items-center gap-3 pl-10 pr-4 py-2 md:hidden">
            <OwnerPicker goal={goal} users={organizationUsers} onGoalUpdated={onGoalUpdated} />
            <GroupPicker goal={goal} groups={organizationGroups} onGoalUpdated={onGoalUpdated} />
            {!isPlanningList && <StatusDropdown goal={goal} onGoalUpdated={onGoalUpdated} />}
            <TargetDatePicker goal={goal} onGoalUpdated={onGoalUpdated} />
          </div>
          {isCommentsOpen && <CommentsPanel goalId={goal.id} onClose={() => onToggleComments(null)} />}
          {!isCreatingSubgoal && (
            <button
              type="button"
              onClick={() => {
                setIsCreatingSubgoal(true)
                if (!isExpanded) toggleExpanded()
              }}
              className="btn btn-sm absolute bottom-0 left-12 translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity z-10"
            >
              <span className="material-symbols-outlined text-base">add</span>
              Add subgoal
            </button>
          )}
        </div>
      </div>
      {isExpanded &&
        subgoals.length > 0 &&
        (summarySubgoals ? (
          <SortableSubgoalSummaryList
            subgoals={subgoals}
            isSortEnabled={isSortEnabled}
            isClosed={goal.is_closed}
            organizationUsers={organizationUsers}
            organizationGroups={organizationGroups}
            onGoalUpdated={onGoalUpdated}
            onGoalRemoved={onGoalRemoved}
            onDragEnd={handleSubgoalDragEnd}
            openCommentsGoalId={openCommentsGoalId}
            onToggleComments={onToggleComments}
          />
        ) : (
          <SortableSubgoalEditList
            subgoals={subgoals}
            isPlanningList={isPlanningList}
            isSortEnabled={isSortEnabled}
            isClosed={goal.is_closed}
            organizationUsers={organizationUsers}
            organizationGroups={organizationGroups}
            onGoalUpdated={onGoalUpdated}
            onGoalRemoved={onGoalRemoved}
            onDragEnd={handleSubgoalDragEnd}
            openCommentsGoalId={openCommentsGoalId}
            onToggleComments={onToggleComments}
          />
        ))}
      {isCreatingSubgoal && (
        <GoalCreationRow isSubgoal parentGoalId={goal.id} onCancel={() => setIsCreatingSubgoal(false)} />
      )}
    </li>
  )
}
