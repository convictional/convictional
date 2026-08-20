import { type ReactElement, useEffect, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal, GoalSummary } from "~/react/shared/types"
import { Dropdown } from "~/react/ui/Dropdown"
import { showFlash } from "~/shared/flash"

interface GoalActionsMenuProps {
  goal: Goal | GoalSummary
  isSubgoal?: boolean
  isClosed?: boolean
  onClose: () => void
  onReactivate: () => void
  onDelete: () => void
  onActivate?: () => void
  trigger?: ReactElement
}

export function GoalActionsMenu({
  goal,
  isSubgoal = false,
  isClosed: isClosedProp,
  onClose,
  onReactivate,
  onDelete,
  onActivate,
  trigger,
}: GoalActionsMenuProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [isSubscribed, setIsSubscribed] = useState<boolean | null>(null)

  const isClosed = isClosedProp ?? goal.is_closed
  const hasSubgoals = "subgoals" in goal && (goal.subgoals?.length ?? 0) > 0
  const entityName = isSubgoal ? "subgoal" : "goal"

  useEffect(() => {
    if (!isOpen || isSubscribed !== null) return
    apiFetch<{ wants_all: boolean }>(`/api/workspaces/${goal.workspace_id}/subscription`)
      .then(data => setIsSubscribed(data.wants_all))
      .catch(() => setIsSubscribed(false))
  }, [isOpen, goal.workspace_id, isSubscribed])

  async function toggleSubscription() {
    const newLevel = isSubscribed ? "relevant_only" : "all"
    setIsSubscribed(!isSubscribed)
    try {
      const data = await apiFetch<{ wants_all: boolean }>(`/api/workspaces/${goal.workspace_id}/subscription`, {
        method: "PATCH",
        body: JSON.stringify({ level: newLevel }),
      })
      setIsSubscribed(data.wants_all)
    } catch {
      setIsSubscribed(isSubscribed)
      showFlash("Failed to update subscription. Please try again.", "error")
    }
  }

  async function handleClose(close: () => void) {
    if (!(await confirm({ message: `Close this ${entityName}?` }))) return
    close()
    try {
      await apiFetch(`/api/goals/${goal.id}/close`, { method: "POST", body: JSON.stringify({}) })
      onClose()
    } catch {
      showFlash(`Failed to close ${entityName}. Please try again.`, "error")
    }
  }

  async function handleReactivate(close: () => void) {
    if (!(await confirm({ message: `Reopen this ${entityName}?` }))) return
    close()
    try {
      await apiFetch(`/api/goals/${goal.id}/reactivate`, { method: "POST" })
      onReactivate()
    } catch {
      showFlash(`Failed to reopen ${entityName}. Please try again.`, "error")
    }
  }

  async function handleDelete(close: () => void) {
    const deleteLabel = hasSubgoals ? "goal and all its subgoals" : entityName
    if (!(await confirm({ message: `Delete this ${deleteLabel}?` }))) return
    close()
    try {
      await apiFetch(`/api/goals/${goal.id}`, { method: "DELETE" })
      onDelete()
    } catch {
      showFlash(`Failed to delete ${entityName}. Please try again.`, "error")
    }
  }

  async function handleActivate(close: () => void) {
    close()
    try {
      await apiFetch(`/api/goals/${goal.id}/activate`, { method: "POST" })
      onActivate?.()
    } catch {
      showFlash(`Failed to activate ${entityName}. Please try again.`, "error")
    }
  }

  // The row containing this menu is clickable for navigation — stopPropagation
  // on the trigger keeps a kebab click from also triggering the row.
  const stopRowClick = (event: React.MouseEvent) => event.stopPropagation()

  const defaultTrigger = (
    <button type="button" onClick={stopRowClick} className="btn btn-sm btn-circle">
      <span className="material-symbols-outlined text-base">more_horiz</span>
    </button>
  )

  const hoverRevealTrigger = (
    <button
      type="button"
      onClick={stopRowClick}
      className="btn btn-sm btn-circle opacity-0 group-hover:opacity-100 transition-opacity"
    >
      <span className="material-symbols-outlined text-base">more_horiz</span>
    </button>
  )

  const resolvedTrigger = trigger ?? (goal.is_draft ? hoverRevealTrigger : defaultTrigger)

  return (
    <Dropdown
      placement="bottom-end"
      open={isOpen}
      onOpenChange={setIsOpen}
      className="dropdown-card p-2 w-72 z-50"
      trigger={resolvedTrigger}
    >
      {({ close }) => (
        <ul className="space-y-1">
          {goal.is_draft ? (
            <>
              <li>
                <button
                  type="button"
                  onClick={() => handleActivate(close)}
                  className="flex-1 flex items-center gap-4 text-left p-2 hover:bg-base-200 rounded-md w-full"
                >
                  <span className="material-symbols-outlined text-xl">rocket_launch</span>
                  <div className="flex flex-col text-left">
                    <span className="text-sm font-semibold">Activate</span>
                    <span className="text-pretty text-xs opacity-50">Make this {entityName} live</span>
                  </div>
                </button>
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => handleDelete(close)}
                  className="flex-1 flex items-center gap-4 text-left p-2 hover:bg-base-200 rounded-md w-full"
                >
                  <span className="material-symbols-outlined text-xl">delete</span>
                  <div className="flex flex-col text-left">
                    <span className="text-sm font-semibold">Delete</span>
                    <span className="text-pretty text-xs opacity-50">
                      Delete this {hasSubgoals ? "goal and all its subgoals" : entityName} permanently
                    </span>
                  </div>
                </button>
              </li>
            </>
          ) : (
            <>
              <li>
                {isSubscribed === null ? (
                  <div className="flex items-center justify-center p-2">
                    <span className="loading loading-spinner loading-xs" />
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={toggleSubscription}
                    className="flex-1 flex items-center gap-4 text-left p-2 hover:bg-base-200 rounded-md w-full"
                  >
                    <span className="material-symbols-outlined text-xl">
                      {isSubscribed ? "notifications_active" : "notifications_off"}
                    </span>
                    <div className="flex flex-col text-left">
                      <span className="text-sm font-semibold">{isSubscribed ? "Subscribed" : "Not subscribed"}</span>
                      <span className="text-pretty text-xs opacity-50">
                        {isSubscribed ? "You're receiving notifications" : "You're not receiving notifications"}
                      </span>
                    </div>
                  </button>
                )}
              </li>
              <li>
                {isClosed ? (
                  <button
                    type="button"
                    onClick={() => handleReactivate(close)}
                    className="flex-1 flex items-center gap-4 text-left p-2 hover:bg-base-200 rounded-md w-full"
                  >
                    <span className="material-symbols-outlined text-xl">refresh</span>
                    <div className="flex flex-col text-left">
                      <span className="text-sm font-semibold">Reopen</span>
                      <span className="text-pretty text-xs opacity-50">Reopen this {entityName}</span>
                    </div>
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => handleClose(close)}
                    className="flex-1 flex items-center gap-4 text-left p-2 hover:bg-base-200 rounded-md w-full"
                  >
                    <span className="material-symbols-outlined text-xl">check_circle</span>
                    <div className="flex flex-col text-left">
                      <span className="text-sm font-semibold">Close</span>
                      <span className="text-pretty text-xs opacity-50">Close this {entityName}</span>
                    </div>
                  </button>
                )}
              </li>
              <li>
                <button
                  type="button"
                  onClick={() => handleDelete(close)}
                  className="flex-1 flex items-center gap-4 text-left p-2 hover:bg-base-200 rounded-md w-full"
                >
                  <span className="material-symbols-outlined text-xl">delete</span>
                  <div className="flex flex-col text-left">
                    <span className="text-sm font-semibold">Delete</span>
                    <span className="text-pretty text-xs opacity-50">
                      Delete this {hasSubgoals ? "goal and all its subgoals" : entityName} permanently
                    </span>
                  </div>
                </button>
              </li>
            </>
          )}
        </ul>
      )}
    </Dropdown>
  )
}
