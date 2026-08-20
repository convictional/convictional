import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { Link } from "@tanstack/react-router"

import { CommentsPanel } from "~/react/composites/CommentsPanel"
import { STATUS_CONFIG, STATUS_OPTIONS } from "~/react/shared/statusConfig"
import type { Goal, Group, GoalSummary, User } from "~/react/shared/types"
import { Tooltip } from "~/react/ui/Tooltip"
import { formatISODate } from "~/shared/datetime"
import { RowActions } from "./RowActions"
import { reorderSubgoals, SortableSubgoalSummaryList } from "./SortableSubgoalList"

interface GoalSummaryRowProps {
  goal: Goal
  isSortEnabled: boolean
  isHighlighted?: boolean
  isExpanded: boolean
  onToggleExpanded: () => void
  organizationUsers: User[]
  organizationGroups: Group[]
  onGoalUpdated: (goal: Goal) => void
  onGoalRemoved: (goalId: string) => void
  onReorderSubgoals: (parentId: string, subgoals: GoalSummary[]) => void
  openCommentsGoalId: string | null
  onToggleComments: (goalId: string | null) => void
  onStartEditing: () => void
}

export function GoalSummaryRow({
  goal,
  isSortEnabled,
  isHighlighted,
  isExpanded,
  onToggleExpanded,
  organizationUsers,
  organizationGroups,
  onGoalUpdated,
  onGoalRemoved,
  onReorderSubgoals,
  openCommentsGoalId,
  onToggleComments,
  onStartEditing,
}: GoalSummaryRowProps) {
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

  const statusConfig = goal.is_completed ? null : (STATUS_CONFIG[goal.status] ?? STATUS_OPTIONS[0])

  function handleSubgoalDragEnd(activeId: string, overId: string) {
    const reordered = reorderSubgoals(goal, activeId, overId)
    if (reordered) onReorderSubgoals(goal.id, reordered)
  }

  return (
    <li ref={setNodeRef} style={style} id={`goal-${goal.id}`} className="pl-10 -ml-10">
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
              onClick={onToggleExpanded}
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
        <Link
          to="/goals/$goalId"
          params={{ goalId: goal.id }}
          className="md:col-span-3 md:grid md:grid-cols-subgrid cursor-pointer group/link"
        >
          <Tooltip content="View goal" placement="bottom">
            <div className="flex items-center py-5 pl-2 pr-4">
              <div className="flex-1 flex flex-col gap-2 min-w-0">
                {goal.title && (
                  <span className="text-xs font-medium text-base-content/50 leading-none truncate">{goal.title}</span>
                )}
                <span className="text-sm text-base-content font-semibold group-hover/link:underline">
                  {goal.description}
                </span>
                <div className="flex items-center gap-2 flex-wrap md:hidden text-xs">
                  {goal.owner && <span className="text-primary">@{goal.owner.display_name}</span>}
                  {goal.group && <span className="text-primary">@{goal.group.name}</span>}
                  {goal.is_completed ? (
                    <span className="inline-flex items-center gap-1 font-medium text-success-content">
                      <span className="material-symbols-outlined text-xs">check</span>
                      Complete
                    </span>
                  ) : (
                    statusConfig && (
                      <span
                        className={`inline-flex items-center font-medium px-1.5 py-0.5 rounded-full border ${statusConfig.classes}`}
                      >
                        {statusConfig.text}
                      </span>
                    )
                  )}
                  {goal.target_date && <span className="text-base-content/60">{formatISODate(goal.target_date)}</span>}
                </div>
              </div>
            </div>
          </Tooltip>
          <div className="hidden md:flex px-4 py-4 flex-col gap-2">
            <span className={`text-sm ${goal.owner ? "text-primary" : "text-base-content/40"}`}>
              {goal.owner ? `@${goal.owner.display_name}` : "No assignee"}
            </span>
            <span className={`text-sm ${goal.group ? "text-primary" : "text-base-content/40"}`}>
              {goal.group ? `@${goal.group.name}` : "No group"}
            </span>
          </div>
          <div className="hidden md:flex px-4 py-4 flex-col items-start gap-3">
            {goal.is_completed ? (
              <span className="inline-flex items-center gap-2 text-sm font-medium text-success-content">
                <span className="material-symbols-outlined text-base">check</span>
                Complete
              </span>
            ) : (
              statusConfig && (
                <span
                  className={`inline-flex items-center text-sm font-medium px-2.5 py-0.5 rounded-full border ${statusConfig.classes}`}
                >
                  {statusConfig.text}
                </span>
              )
            )}
            <span className={`text-sm ${goal.target_date ? "text-base-content" : "text-base-content/40"}`}>
              {goal.target_date ? formatISODate(goal.target_date) : "No date"}
            </span>
          </div>
        </Link>
        <RowActions
          goal={goal}
          isCommentsOpen={isCommentsOpen}
          onToggleComments={onToggleComments}
          onGoalRemoved={onGoalRemoved}
          editButton={{ mode: "enter", onStartEditing, label: "Edit goal" }}
        />
        {isCommentsOpen && <CommentsPanel goalId={goal.id} onClose={() => onToggleComments(null)} />}
      </div>
      {isExpanded && subgoals.length > 0 && (
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
      )}
    </li>
  )
}
