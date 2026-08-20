import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import { Link } from "@tanstack/react-router"

import { CommentsPanel } from "~/react/composites/CommentsPanel"
import { STATUS_CONFIG, STATUS_OPTIONS } from "~/react/shared/statusConfig"
import type { GoalSummary } from "~/react/shared/types"
import { Tooltip } from "~/react/ui/Tooltip"
import { formatISODate } from "~/shared/datetime"
import { RowActions } from "./RowActions"

interface SubgoalSummaryRowProps {
  subgoal: GoalSummary
  isSortEnabled: boolean
  isClosed: boolean
  onGoalRemoved: (goalId: string) => void
  openCommentsGoalId: string | null
  onToggleComments: (goalId: string | null) => void
  onStartEditing: () => void
}

export function SubgoalSummaryRow({
  subgoal,
  isSortEnabled,
  isClosed,
  onGoalRemoved,
  openCommentsGoalId,
  onToggleComments,
  onStartEditing,
}: SubgoalSummaryRowProps) {
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

  const statusConfig = subgoal.is_completed ? null : (STATUS_CONFIG[subgoal.status] ?? STATUS_OPTIONS[0])

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
        <Link
          to="/goals/$goalId"
          params={{ goalId: subgoal.id }}
          className="md:col-span-3 md:grid md:grid-cols-subgrid cursor-pointer group/link"
        >
          <Tooltip content="View goal" placement="bottom">
            <div className="flex items-center p-4">
              <div className="flex-1 flex flex-col gap-2 min-w-0">
                {subgoal.title && (
                  <span className="text-xs font-medium text-base-content/50 leading-none truncate">
                    {subgoal.title}
                  </span>
                )}
                <span className="text-sm text-base-content/90 group-hover/link:underline">{subgoal.description}</span>
                <div className="flex items-center gap-2 flex-wrap md:hidden text-xs">
                  {subgoal.owner && <span className="text-primary">@{subgoal.owner.display_name}</span>}
                  {subgoal.group && <span className="text-primary">@{subgoal.group.name}</span>}
                  {subgoal.is_completed ? (
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
                  {subgoal.target_date && (
                    <span className="text-base-content/60">{formatISODate(subgoal.target_date)}</span>
                  )}
                </div>
              </div>
            </div>
          </Tooltip>
          <div className="hidden md:flex px-4 py-4 flex-col gap-2">
            <span className={`text-sm ${subgoal.owner ? "text-primary" : "text-base-content/40"}`}>
              {subgoal.owner ? `@${subgoal.owner.display_name}` : "No assignee"}
            </span>
            <span className={`text-sm ${subgoal.group ? "text-primary" : "text-base-content/40"}`}>
              {subgoal.group ? `@${subgoal.group.name}` : "No group"}
            </span>
          </div>
          <div className="hidden md:flex px-4 py-4 flex-col items-start gap-3">
            {subgoal.is_completed ? (
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
            <span className={`text-sm ${subgoal.target_date ? "text-base-content" : "text-base-content/40"}`}>
              {subgoal.target_date ? formatISODate(subgoal.target_date) : "No date"}
            </span>
          </div>
        </Link>
        <RowActions
          goal={subgoal}
          isCommentsOpen={isCommentsOpen}
          onToggleComments={onToggleComments}
          onGoalRemoved={onGoalRemoved}
          editButton={{ mode: "enter", onStartEditing, label: "Edit subgoal" }}
          actionsMenuProps={{ isSubgoal: true, isClosed }}
        />
        {isCommentsOpen && <CommentsPanel goalId={subgoal.id} onClose={() => onToggleComments(null)} />}
      </div>
    </li>
  )
}
