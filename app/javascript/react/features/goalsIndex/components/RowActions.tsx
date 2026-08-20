import { GoalActionsMenu } from "~/react/composites/goals/GoalActionsMenu"
import type { Goal, GoalSummary } from "~/react/shared/types"
import { Tooltip } from "~/react/ui/Tooltip"
import { CommentButton } from "./CommentButton"

interface RowActionsProps {
  goal: Goal | GoalSummary
  isCommentsOpen: boolean
  onToggleComments: (goalId: string | null) => void
  onGoalRemoved: (goalId: string) => void
  editButton?: { mode: "enter"; onStartEditing: () => void; label: string } | { mode: "exit"; onExitEdit: () => void }
  actionsMenuProps?: {
    isSubgoal?: boolean
    isClosed?: boolean
    onActivate?: () => void
  }
}

export function RowActions({
  goal,
  isCommentsOpen,
  onToggleComments,
  onGoalRemoved,
  editButton,
  actionsMenuProps,
}: RowActionsProps) {
  return (
    <div className="join join-vertical items-center self-center px-2">
      {editButton?.mode === "exit" ? (
        <Tooltip content="Done editing" placement="left">
          <button
            type="button"
            className="btn btn-sm btn-square join-item"
            onClick={e => {
              e.stopPropagation()
              editButton.onExitEdit()
            }}
          >
            <span className="material-symbols-outlined text-base">edit_off</span>
          </button>
        </Tooltip>
      ) : editButton?.mode === "enter" ? (
        <button
          type="button"
          className="btn btn-sm btn-square join-item opacity-0 group-hover:opacity-100 transition-opacity"
          aria-label={editButton.label}
          onClick={e => {
            e.stopPropagation()
            editButton.onStartEditing()
          }}
        >
          <span className="material-symbols-outlined text-base">edit</span>
        </button>
      ) : null}
      <CommentButton
        goalId={goal.id}
        commentCount={goal.open_comment_count}
        isOpen={isCommentsOpen}
        onToggle={onToggleComments}
      />
      <GoalActionsMenu
        goal={goal}
        isSubgoal={actionsMenuProps?.isSubgoal}
        isClosed={actionsMenuProps?.isClosed}
        onClose={() => onGoalRemoved(goal.id)}
        onReactivate={() => onGoalRemoved(goal.id)}
        onDelete={() => onGoalRemoved(goal.id)}
        onActivate={actionsMenuProps?.onActivate}
        trigger={
          <button
            type="button"
            onClick={e => e.stopPropagation()}
            className="btn btn-sm btn-square join-item opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <span className="material-symbols-outlined text-base">more_horiz</span>
          </button>
        }
      />
    </div>
  )
}
