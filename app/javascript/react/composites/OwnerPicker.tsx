import { useCallback, useMemo, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal, GoalSummary, User } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"

import { Dropdown } from "~/react/ui/Dropdown"

interface OwnerPickerProps {
  goal: Goal | GoalSummary
  users: User[]
  onGoalUpdated: (goal: Goal) => void
}

export function OwnerPicker({ goal, users, onGoalUpdated }: OwnerPickerProps) {
  const [searchQuery, setSearchQuery] = useState("")

  // Focus the search input without scrolling. The picker renders in a floating
  // portal during the goals page's document-level scroll, so autoFocus (or a
  // plain .focus()) scrolls the page to the top to reveal it. See GifPicker.
  const focusWithoutScroll = useCallback((node: HTMLInputElement | null) => {
    node?.focus({ preventScroll: true })
  }, [])

  const filteredUsers = useMemo(() => {
    if (!searchQuery) return users
    const q = searchQuery.toLowerCase()
    return users.filter(u => u.display_name.toLowerCase().includes(q))
  }, [users, searchQuery])

  const availableUsers = useMemo(() => filteredUsers.filter(u => u.id !== goal.owner?.id), [filteredUsers, goal.owner])

  async function selectOwner(userId: string | null, close: () => void) {
    close()
    setSearchQuery("")
    const payload: Record<string, unknown> = userId ? { owner_id: userId } : { clear_owner: true }

    try {
      const updated = await apiFetch<Goal>(`/api/goals/${goal.id}?expand=subgoals&expand=parent`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
      onGoalUpdated(updated)
    } catch {
      // Intentionally swallowed — a failed owner update is non-critical
    }
  }

  return (
    <Dropdown
      placement="bottom-start"
      onOpenChange={open => !open && setSearchQuery("")}
      // Disable floating-ui's auto-focus, which scrolls the page to reveal the
      // focused input; we focus the search input with preventScroll instead.
      initialFocus={-1}
      className="dropdown-card w-56 z-50"
      trigger={
        <div className="cursor-pointer flex items-center gap-1">
          <span className={`text-sm ${goal.owner ? "text-primary" : "text-base-content/40"}`}>
            {goal.owner ? `@${goal.owner.display_name}` : "No assignee"}
          </span>
        </div>
      }
    >
      {({ close }) => (
        <>
          <div className="p-2 pb-0">
            <input
              type="text"
              placeholder="Search people..."
              autoComplete="off"
              className="input input-sm input-bordered !outline-none bg-base-50 w-full"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              ref={focusWithoutScroll}
            />
          </div>
          {goal.owner && (
            <>
              <div className="px-2">
                <span className="text-xs font-semibold opacity-75 px-1">Current Owner</span>
                <button onClick={() => selectOwner(null, close)} className="dropdown-item px-1 py-0 w-full">
                  <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
                    <Avatar displayName={goal.owner.display_name} picture={goal.owner.picture} size="small" />
                    <span className="text-xs font-semibold truncate">{goal.owner.display_name}</span>
                    <span className="material-symbols-outlined text-lg">close</span>
                  </div>
                </button>
              </div>
              <div className="divider my-0" />
            </>
          )}
          <div className="p-2 pt-0">
            <span className="text-xs font-semibold opacity-75 px-1">{goal.owner ? "Reassign to" : "Assign to"}</span>
            <ul className="max-h-60 overflow-y-auto grid gap-1">
              {availableUsers.length === 0 && (
                <li className="text-center py-2 text-sm text-base-500">No results match your search</li>
              )}
              {availableUsers.map(user => (
                <li key={user.id}>
                  <button onClick={() => selectOwner(user.id, close)} className="dropdown-item p-1 w-full">
                    <div className="grid grid-cols-[auto_1fr] items-center gap-2">
                      <Avatar displayName={user.display_name} picture={user.picture} size="small" />
                      <span className="text-xs font-semibold truncate">{user.display_name}</span>
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </Dropdown>
  )
}
