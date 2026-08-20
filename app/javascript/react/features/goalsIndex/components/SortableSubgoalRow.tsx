import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"

import { CommentsPanel } from "~/react/composites/CommentsPanel"
import { GoalDescriptionEditor } from "~/react/composites/goals/GoalDescriptionEditor"
import { GroupPicker } from "~/react/composites/GroupPicker"
import { OwnerPicker } from "~/react/composites/OwnerPicker"
import { StatusDropdown } from "~/react/composites/StatusDropdown"
import { TargetDatePicker } from "~/react/composites/TargetDatePicker"
import type { Goal, Group, GoalSummary, User } from "~/react/shared/types"
import { RowActions } from "./RowActions"

export function SortableSubgoalRow({
  subgoal,
  isPlanningList,
  isSortEnabled,
  isClosed,
  organizationUsers,
  organizationGroups,
  onGoalUpdated,
  onGoalRemoved,
  openCommentsGoalId,
  onToggleComments,
  onExitEdit,
}: {
  subgoal: GoalSummary
  isPlanningList: boolean
  isSortEnabled: boolean
  isClosed: boolean
  organizationUsers: User[]
  organizationGroups: Group[]
  onGoalUpdated: (goal: Goal) => void
  onGoalRemoved: (goalId: string) => void
  openCommentsGoalId: string | null
  onToggleComments: (goalId: string | null) => void
  onExitEdit?: () => void
}) {
  const isCommentsOpen = openCommentsGoalId === subgoal.id

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: subgoal.id,
    disabled: !isSortEnabled,
  })

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : undefined,
  }

  return (
    <li ref={setNodeRef} style={style} id={`goal-${subgoal.id}`} className="pl-10">
      <div
        className={`grid grid-cols-[32px_1fr_48px] md:grid-cols-[32px_1fr_180px_160px_48px] hover:bg-base-200/50 group border-b border-base-300 relative${isCommentsOpen ? " bg-base-200/50" : ""}`}
      >
        {isSortEnabled && (
          <span
            {...attributes}
            {...listeners}
            className="material-symbols-outlined cursor-grab text-lg text-base-content/40 hover:text-base-content/60 absolute left-8 top-1/2 -translate-y-1/2 -translate-x-full px-2 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity"
          >
            drag_indicator
          </span>
        )}
        <div />
        <div className="flex items-center relative">
          <GoalDescriptionEditor goal={subgoal} onGoalUpdated={onGoalUpdated} isSubgoal />
        </div>
        <div className="hidden md:flex px-4 py-4 flex-col gap-2">
          <OwnerPicker goal={subgoal} users={organizationUsers} onGoalUpdated={onGoalUpdated} />
          <GroupPicker goal={subgoal} groups={organizationGroups} onGoalUpdated={onGoalUpdated} />
        </div>
        <div className="hidden md:flex px-4 py-4 flex-col items-start gap-3">
          {!isPlanningList && <StatusDropdown goal={subgoal} onGoalUpdated={onGoalUpdated} />}
          <TargetDatePicker goal={subgoal} onGoalUpdated={onGoalUpdated} />
        </div>
        <RowActions
          goal={subgoal}
          isCommentsOpen={isCommentsOpen}
          onToggleComments={onToggleComments}
          onGoalRemoved={onGoalRemoved}
          editButton={onExitEdit ? { mode: "exit", onExitEdit } : undefined}
          actionsMenuProps={{ isSubgoal: true, isClosed }}
        />
        <div className="order-1 col-span-full flex items-center gap-3 pl-10 pr-4 py-2 md:hidden">
          <OwnerPicker goal={subgoal} users={organizationUsers} onGoalUpdated={onGoalUpdated} />
          <GroupPicker goal={subgoal} groups={organizationGroups} onGoalUpdated={onGoalUpdated} />
          {!isPlanningList && <StatusDropdown goal={subgoal} onGoalUpdated={onGoalUpdated} />}
          <TargetDatePicker goal={subgoal} onGoalUpdated={onGoalUpdated} />
        </div>
        {isCommentsOpen && <CommentsPanel goalId={subgoal.id} onClose={() => onToggleComments(null)} />}
      </div>
    </li>
  )
}
