import { forwardRef, useEffect, useMemo, useRef, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import type { ChatCollaborator } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"
import { BottomSheet, type BottomSheetHandle } from "~/react/ui/BottomSheet"
import { CollaboratorRow, SlideView } from "./collaboratorPanelShared"

interface OrgUser {
  id: string
  name: string
  picture: string | null
}

interface GroupCollaboratorPanelProps {
  groupId: string
  collaborators: ChatCollaborator[]
  currentUserId: string
  onClose: () => void
  onSelfLeave?: () => void
}

type PanelView = "list" | "add"

export const GroupCollaboratorPanel = forwardRef<BottomSheetHandle, GroupCollaboratorPanelProps>(
  function GroupCollaboratorPanel({ groupId, collaborators, currentUserId, onClose, onSelfLeave }, ref) {
    const [view, setView] = useState<PanelView>("list")
    const [listQuery, setListQuery] = useState("")
    const { users: orgUsers, loading: loadingUsers } = useOrganizationMembers()
    const [leaveError, setLeaveError] = useState<string | null>(null)

    const collaboratorIds = useMemo(() => new Set(collaborators.map(c => c.user.id)), [collaborators])

    const addableUsers = useMemo<OrgUser[]>(
      () =>
        orgUsers
          .map(u => ({ id: u.id, name: u.display_name, picture: u.picture }))
          .sort((a, b) => a.name.localeCompare(b.name)),
      [orgUsers]
    )

    const filteredCollaborators = useMemo(() => {
      const q = listQuery.trim().toLowerCase()
      if (!q) return collaborators
      return collaborators.filter(c => c.user.display_name.toLowerCase().includes(q))
    }, [collaborators, listQuery])

    async function handleLeave() {
      try {
        await apiFetch(`/api/groups/${groupId}/members/${currentUserId}`, { method: "DELETE" })
        onSelfLeave?.()
        onClose()
      } catch (err) {
        setLeaveError(err instanceof ApiError ? err.message : "Couldn't leave group.")
      }
    }

    const title = view === "add" ? "Add to group" : "Group members"
    const slideIndex = view === "list" ? 0 : 1

    return (
      <BottomSheet
        ref={ref}
        title={title}
        onClose={onClose}
        closeAriaLabel="Close members panel"
        desktop="docked"
        headerStart={
          view === "add" ? (
            <button
              type="button"
              onClick={() => setView("list")}
              aria-label="Back"
              className="btn btn-ghost btn-sm btn-square"
            >
              <span className="material-symbols-outlined text-lg leading-none">arrow_back</span>
            </button>
          ) : undefined
        }
      >
        <div className="flex-1 overflow-hidden min-h-[250px]" style={{ position: "relative" }}>
          <SlideView visible={view === "list"} offset={slideIndex > 0 ? "left" : "right"}>
            <GroupCollaboratorListView
              query={listQuery}
              onQueryChange={setListQuery}
              collaborators={filteredCollaborators}
              currentUserId={currentUserId}
              onAddClick={() => setView("add")}
              onLeave={handleLeave}
              leaveError={leaveError}
            />
          </SlideView>
          <SlideView visible={view === "add"} offset={slideIndex > 1 ? "left" : "right"}>
            <AddToGroupListView
              groupId={groupId}
              users={addableUsers}
              loading={loadingUsers}
              collaboratorIds={collaboratorIds}
              onAdded={() => setView("list")}
            />
          </SlideView>
        </div>
      </BottomSheet>
    )
  }
)

function GroupCollaboratorListView({
  query,
  onQueryChange,
  collaborators,
  currentUserId,
  onAddClick,
  onLeave,
  leaveError,
}: {
  query: string
  onQueryChange: (q: string) => void
  collaborators: ChatCollaborator[]
  currentUserId: string
  onAddClick: () => void
  onLeave: () => void
  leaveError: string | null
}) {
  return (
    <>
      <div className="p-3 pt-2">
        <input
          type="text"
          value={query}
          onChange={e => onQueryChange(e.target.value)}
          placeholder="Search members..."
          aria-label="Search members"
          className="input input-sm w-full"
        />
      </div>
      <div className="px-3 pb-2">
        <button type="button" onClick={onAddClick} className="btn w-full justify-center gap-2">
          <span className="material-symbols-outlined text-[18px] leading-none">person_add</span>
          <span>Add to group</span>
        </button>
      </div>
      {leaveError && (
        <div role="alert" className="mx-3 mb-2 text-xs font-medium bg-error text-error-content rounded-md px-2 py-1">
          {leaveError}
        </div>
      )}
      <ul className="flex flex-col px-2 pb-3">
        {collaborators.map(collaborator => {
          const isSelf = collaborator.user.id === currentUserId
          return (
            <CollaboratorRow
              key={collaborator.id}
              collaborator={collaborator}
              action={
                isSelf ? (
                  <button
                    type="button"
                    onClick={async () => {
                      if (!(await confirm({ message: "Leave this group?" }))) return
                      onLeave()
                    }}
                    title="Leave group"
                    aria-label="Leave group"
                    className="btn btn-ghost btn-sm shrink-0"
                  >
                    <span className="material-symbols-outlined text-[18px] leading-none">logout</span>
                  </button>
                ) : undefined
              }
            />
          )
        })}
      </ul>
    </>
  )
}

function AddToGroupListView({
  groupId,
  users,
  loading,
  collaboratorIds,
  onAdded,
}: {
  groupId: string
  users: OrgUser[]
  loading: boolean
  collaboratorIds: Set<string>
  onAdded: () => void
}) {
  const [query, setQuery] = useState("")
  const [pendingUser, setPendingUser] = useState<OrgUser | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return users.filter(u => !collaboratorIds.has(u.id) && (!q || u.name.toLowerCase().includes(q)))
  }, [users, collaboratorIds, query])

  async function confirmAdd() {
    if (!pendingUser) return
    setSubmitting(true)
    setError(null)
    try {
      await apiFetch(`/api/groups/${groupId}/members`, {
        method: "POST",
        body: JSON.stringify({ user_id: pendingUser.id }),
      })
      setPendingUser(null)
      onAdded()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add member.")
      setSubmitting(false)
    }
  }

  return (
    <>
      <div className="p-3 pt-2">
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={e => setQuery(e.target.value)}
          placeholder="Search people to add..."
          aria-label="Search people to add"
          className="input input-sm w-full"
        />
      </div>
      <ul className="flex flex-col px-2 pb-3">
        {loading && <li className="px-3 py-4 text-sm text-base-content/60">Loading…</li>}
        {!loading && filtered.length === 0 && (
          <li className="px-3 py-4 text-sm text-base-content/60">No people to add</li>
        )}
        {filtered.map(user => (
          <li key={user.id}>
            <button
              type="button"
              onClick={() => {
                setError(null)
                setPendingUser(prev => (prev?.id === user.id ? null : user))
              }}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-base-200 text-left cursor-pointer"
            >
              <Avatar displayName={user.name} picture={user.picture} size="small" />
              <span className="flex-1 min-w-0 text-sm truncate">{user.name}</span>
              <span className="material-symbols-outlined text-[18px] leading-none text-base-content/40">
                {pendingUser?.id === user.id ? "close" : "person_add"}
              </span>
            </button>
            {pendingUser?.id === user.id && (
              <div className="flex flex-col gap-2 px-3 pt-2 pb-3">
                <button type="button" onClick={confirmAdd} disabled={submitting} className="btn">
                  Add to group
                </button>
                <p className="text-xs text-base-content/80">
                  Adding <span className="font-medium">{user.name}</span> gives them access to the full chat history,
                  goals, and posts for this group.
                </p>
                {error && (
                  <div role="alert" className="text-xs font-medium bg-error text-error-content rounded-md px-2 py-1">
                    {error}
                  </div>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  )
}
