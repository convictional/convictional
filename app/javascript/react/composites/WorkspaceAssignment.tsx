import { useCallback, useEffect, useState } from "react"

import { SearchablePicker } from "~/react/composites/SearchablePicker"
import { apiFetch } from "~/react/shared/apiFetch"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import type { User } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

interface WorkspaceAssignmentResponse {
  assignee: User | null
}

interface Props {
  workspaceId: string
}

export function WorkspaceAssignment({ workspaceId }: Props) {
  const isMobile = useIsMobile()
  const { users, loading } = useOrganizationMembers()
  const [assignee, setAssignee] = useState<User | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let cancelled = false
    apiFetch<WorkspaceAssignmentResponse>(`/api/workspaces/${workspaceId}/assignment`)
      .then(data => {
        if (cancelled) return
        setAssignee(data.assignee)
      })
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [workspaceId])

  const assign = useCallback(
    async (userId: string) => {
      try {
        const next = await apiFetch<WorkspaceAssignmentResponse>(`/api/workspaces/${workspaceId}/assignment`, {
          method: "PATCH",
          body: JSON.stringify({ user_id: userId }),
        })
        setAssignee(next.assignee)
      } catch {
        showFlash("Couldn't update assignment.")
      }
    },
    [workspaceId]
  )

  const unassign = useCallback(async () => {
    try {
      await apiFetch(`/api/workspaces/${workspaceId}/assignment`, { method: "DELETE" })
      setAssignee(null)
    } catch {
      showFlash("Couldn't clear assignment.")
    }
  }, [workspaceId])

  if (!loaded) return null

  const triggerLabel = assignee ? `Assigned to ${assignee.display_name}` : "Assign"
  // Mobile drops the text label (and chevron) for an icon-only button — the
  // assignee avatar when assigned, a person-add icon when not — so the header
  // row stays compact.
  const triggerClassName = isMobile ? "btn btn-square" : assignee ? "btn pl-1.5" : "btn"
  const triggerContent = isMobile ? (
    assignee ? (
      <Avatar displayName={assignee.display_name} picture={assignee.picture} size="small" />
    ) : (
      <span className="material-symbols-outlined text-xl text-base-600">person_add</span>
    )
  ) : assignee ? (
    <>
      <Avatar displayName={assignee.display_name} picture={assignee.picture} size="small" />
      <span className="text-xs truncate">{assignee.display_name}</span>
      <span className="material-symbols-outlined text-lg transition -mr-1">keyboard_arrow_down</span>
    </>
  ) : (
    <>
      Assign
      <span className="material-symbols-outlined text-lg transition -mr-1">keyboard_arrow_down</span>
    </>
  )

  return (
    <SearchablePicker
      trigger={
        <button type="button" className={triggerClassName} aria-label={triggerLabel}>
          {triggerContent}
        </button>
      }
      title="Assign"
      ariaLabel="Assignment"
      placement="bottom-end"
      panelClassName="dropdown-card p-0 w-56 z-50"
      searchPlaceholder="Search people…"
      loading={loading}
      items={users.filter(u => !(assignee && u.id === assignee.id))}
      getKey={u => u.id}
      getSearchText={u => u.display_name}
      renderHeader={close =>
        assignee ? (
          <>
            <div className="px-2">
              <span className="text-xs font-semibold opacity-75 px-1">Current Assignee</span>
              <button
                type="button"
                className="dropdown-item px-1 py-0 w-full"
                onClick={() => {
                  void unassign()
                  close()
                }}
              >
                <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2 w-full">
                  <Avatar displayName={assignee.display_name} picture={assignee.picture} size="small" />
                  <span className="text-xs font-semibold truncate text-left">{assignee.display_name}</span>
                  <Tooltip content={`Unassign ${assignee.display_name}`}>
                    <span className="material-symbols-outlined text-lg">close</span>
                  </Tooltip>
                </div>
              </button>
            </div>
            <div className="divider my-0" />
          </>
        ) : null
      }
      listLabel={
        <span className="text-xs font-semibold opacity-75 px-1">{assignee ? "Reassign to" : "Assign to"}</span>
      }
      renderItem={(user, close) => (
        <button
          type="button"
          className="dropdown-item p-1 w-full"
          onClick={() => {
            void assign(user.id)
            close()
          }}
        >
          <div className="grid grid-cols-[auto_1fr] items-center gap-2 w-full">
            <Avatar displayName={user.display_name} picture={user.picture} size="small" />
            <span className="text-xs font-semibold truncate text-left">{user.display_name}</span>
          </div>
        </button>
      )}
    />
  )
}
