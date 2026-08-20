import { useCallback, useMemo, useState } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import type { Goal, Group, GoalSummary } from "~/react/shared/types"

import { Dropdown } from "~/react/ui/Dropdown"

interface GroupPickerProps {
  goal: Goal | GoalSummary
  groups: Group[]
  onGoalUpdated: (goal: Goal) => void
}

export function GroupPicker({ goal, groups, onGoalUpdated }: GroupPickerProps) {
  const [searchQuery, setSearchQuery] = useState("")

  // Focus the search input without scrolling. The picker renders in a floating
  // portal during the goals page's document-level scroll, so autoFocus (or a
  // plain .focus()) scrolls the page to the top to reveal it. See GifPicker.
  const focusWithoutScroll = useCallback((node: HTMLInputElement | null) => {
    node?.focus({ preventScroll: true })
  }, [])

  const filteredGroups = useMemo(() => {
    if (!searchQuery) return groups
    const q = searchQuery.toLowerCase()
    return groups.filter(g => g.name.toLowerCase().includes(q))
  }, [groups, searchQuery])

  const availableGroups = useMemo(
    () => filteredGroups.filter(g => g.id !== goal.group?.id),
    [filteredGroups, goal.group]
  )

  async function selectGroup(groupId: string | null, close: () => void) {
    close()
    setSearchQuery("")
    const payload: Record<string, unknown> = groupId ? { group_id: groupId } : { clear_group: true }

    try {
      const updated = await apiFetch<Goal>(`/api/goals/${goal.id}?expand=subgoals&expand=parent`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      })
      onGoalUpdated(updated)
    } catch {
      // Matches silent-fail pattern of other pickers
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
          <span className={`text-sm ${goal.group ? "text-primary" : "text-base-content/40"}`}>
            {goal.group ? `@${goal.group.name}` : "No group"}
          </span>
        </div>
      }
    >
      {({ close }) => (
        <>
          <div className="p-2 pb-0">
            <input
              type="text"
              placeholder="Search groups..."
              autoComplete="off"
              className="input input-sm input-bordered !outline-none bg-base-50 w-full"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              ref={focusWithoutScroll}
            />
          </div>
          {goal.group && (
            <>
              <div className="px-2">
                <span className="text-xs font-semibold opacity-75 px-1">Current Group</span>
                <button
                  onClick={() => selectGroup(null, close)}
                  className="dropdown-item w-full flex items-center justify-between gap-2"
                >
                  <span className="text-xs font-semibold truncate flex-1">{goal.group.name}</span>
                  <span className="material-symbols-outlined text-sm">close</span>
                </button>
              </div>
              <div className="divider my-0" />
            </>
          )}
          <div className="p-2 pt-0">
            <span className="text-xs font-semibold opacity-75 px-1">{goal.group ? "Reassign to" : "Assign to"}</span>
            <ul className="max-h-60 overflow-y-auto grid gap-1">
              {availableGroups.length === 0 && (
                <li className="text-center py-2 text-sm text-base-500">No results match your search</li>
              )}
              {availableGroups.map(group => (
                <li key={group.id}>
                  <button onClick={() => selectGroup(group.id, close)} className="dropdown-item p-1 w-full">
                    <span className="text-xs font-semibold truncate">{group.name}</span>
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
