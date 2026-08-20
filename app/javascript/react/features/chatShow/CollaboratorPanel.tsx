import { useNavigate } from "@tanstack/react-router"
import { forwardRef, useEffect, useMemo, useRef, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import type { PaginatedResponse, ChatCollaborator, GroupMatch } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"
import { BottomSheet, type BottomSheetHandle } from "~/react/ui/BottomSheet"
import { CollaboratorRow, SlideView } from "./collaboratorPanelShared"

interface OrgUser {
  id: string
  name: string
  picture: string | null
}

interface LookupResponse extends PaginatedResponse {
  matches: { id: string; collaborator_count: number }[]
  match_group: GroupMatch | null
}

interface CollaboratorPanelProps {
  collaborators: ChatCollaborator[]
  currentUserId: string
  canLeave?: boolean
  onClose: () => void
  onAdd: (userId: string, shareHistory: boolean) => Promise<{ chatId: string; added: boolean; error?: string }>
  onLeave: () => Promise<{ error?: string }>
}

type PanelView = "list" | "add"

export const CollaboratorPanel = forwardRef<BottomSheetHandle, CollaboratorPanelProps>(function CollaboratorPanel(
  { collaborators, currentUserId, canLeave = true, onClose, onAdd, onLeave },
  ref
) {
  const [view, setView] = useState<PanelView>("list")
  const [listQuery, setListQuery] = useState("")
  const { users: orgUsers, loading: loadingUsers } = useOrganizationMembers()

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

  const title = view === "add" ? "Add people" : "Members"
  const showBack = view !== "list"

  function goBack() {
    setView("list")
  }

  const slideIndex = view === "list" ? 0 : 1

  return (
    <BottomSheet
      ref={ref}
      title={title}
      onClose={onClose}
      closeAriaLabel="Close members panel"
      desktop="docked"
      headerStart={
        showBack ? (
          <button type="button" onClick={goBack} aria-label="Back" className="btn btn-ghost btn-sm btn-square">
            <span className="material-symbols-outlined text-lg leading-none">arrow_back</span>
          </button>
        ) : undefined
      }
    >
      {/* Each view is absolutely positioned inside the content box and
          slides via its own translateX. The current view sits at 0; others
          are pushed off to the right. No parent-percentage math, no flex
          width gymnastics. */}
      <div className="flex-1 overflow-hidden min-h-[250px]" style={{ position: "relative" }}>
        <SlideView visible={view === "list"} offset={slideIndex > 0 ? "left" : "right"}>
          <CollaboratorListView
            query={listQuery}
            onQueryChange={setListQuery}
            collaborators={filteredCollaborators}
            currentUserId={currentUserId}
            canLeave={canLeave}
            onAddClick={() => setView("add")}
            onLeave={onLeave}
          />
        </SlideView>
        <SlideView visible={view === "add"} offset={slideIndex > 1 ? "left" : "right"}>
          <AddCollaboratorListView
            users={addableUsers}
            loading={loadingUsers}
            collaboratorIds={collaboratorIds}
            collaborators={collaborators}
            onAdd={onAdd}
          />
        </SlideView>
      </div>
    </BottomSheet>
  )
})

function CollaboratorListView({
  query,
  onQueryChange,
  collaborators,
  currentUserId,
  canLeave,
  onAddClick,
  onLeave,
}: {
  query: string
  onQueryChange: (q: string) => void
  collaborators: ChatCollaborator[]
  currentUserId: string
  canLeave: boolean
  onAddClick: () => void
  onLeave: () => Promise<{ error?: string }>
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
          <span>Add people</span>
        </button>
      </div>
      <ul className="flex flex-col px-2 pb-3">
        {collaborators.map(collaborator => {
          const isSelf = collaborator.user.id === currentUserId
          return (
            <CollaboratorRow
              key={collaborator.id}
              collaborator={collaborator}
              action={
                isSelf && canLeave ? (
                  <button
                    type="button"
                    onClick={async () => {
                      if (!(await confirm({ message: "Leave this chat?" }))) return
                      await onLeave()
                    }}
                    title="Leave chat"
                    aria-label="Leave chat"
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

function AddCollaboratorListView({
  users,
  loading,
  collaboratorIds,
  collaborators,
  onAdd,
}: {
  users: OrgUser[]
  loading: boolean
  collaboratorIds: Set<string>
  collaborators: ChatCollaborator[]
  onAdd: (userId: string, shareHistory: boolean) => Promise<{ chatId: string; added: boolean; error?: string }>
}) {
  const [query, setQuery] = useState("")
  const [pendingUser, setPendingUser] = useState<OrgUser | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return users.filter(u => !collaboratorIds.has(u.id) && (!q || u.name.toLowerCase().includes(q)))
  }, [users, collaboratorIds, query])

  async function confirmAdd(shareHistory: boolean): Promise<{ error?: string }> {
    if (!pendingUser) return {}
    const result = await onAdd(pendingUser.id, shareHistory)
    if (result.error) return { error: result.error }
    if (!result.added) {
      void navigate({ to: "/chats/$chatId", params: { chatId: result.chatId } })
      return {}
    }
    setPendingUser(null)
    return {}
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
              onClick={() => setPendingUser(prev => (prev?.id === user.id ? null : user))}
              className="w-full flex items-center gap-2 px-2 py-1.5 rounded-md hover:bg-base-200 text-left cursor-pointer"
            >
              <Avatar displayName={user.name} picture={user.picture} size="small" />
              <span className="flex-1 min-w-0 text-sm truncate">{user.name}</span>
              <span className="material-symbols-outlined text-[18px] leading-none text-base-content/40">
                {pendingUser?.id === user.id ? "close" : "person_add"}
              </span>
            </button>
            {pendingUser?.id === user.id && (
              <AddCollaboratorPromptView
                collaborators={collaborators}
                user={user}
                onConfirm={confirmAdd}
                onContinueChat={(chatOrGroupId, isGroup) => {
                  if (isGroup) {
                    void navigate({ to: "/chats", search: { group_id: chatOrGroupId } })
                  } else {
                    void navigate({ to: "/chats/$chatId", params: { chatId: chatOrGroupId } })
                  }
                }}
              />
            )}
          </li>
        ))}
      </ul>
    </>
  )
}

function AddCollaboratorPromptView({
  collaborators,
  user,
  onConfirm,
  onContinueChat,
}: {
  collaborators: ChatCollaborator[]
  user: OrgUser
  onConfirm: (shareHistory: boolean) => Promise<{ error?: string }>
  onContinueChat: (id: string, isGroup: boolean) => void
}) {
  const [lookup, setLookup] = useState<LookupResponse | null>(null)
  const [lookupDone, setLookupDone] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    const userIds = [...collaborators.map(c => c.user.id), user.id]
    const params = userIds.map(id => `user_ids=${encodeURIComponent(id)}`).join("&")
    apiFetch<LookupResponse>(`/api/chats/lookup?${params}`)
      .then(setLookup)
      .catch(() => setLookup({ matches: [], match_group: null, next_cursor: null, has_more: false }))
      .finally(() => setLookupDone(true))
  }, [collaborators, user.id])

  const exactMatch = lookup?.matches.find(c => c.collaborator_count === collaborators.length + 1) ?? null
  const matchGroup = lookup?.match_group ?? null

  async function submit(shareHistory: boolean) {
    setSubmitting(true)
    setError(null)
    const result = await onConfirm(shareHistory)
    if (result.error) {
      setError(result.error)
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 px-3 pt-2 pb-3">
      {!lookupDone && <div className="text-sm text-base-content/60">Checking for existing conversations…</div>}

      {lookupDone && exactMatch && (
        <>
          <p className="text-sm">A conversation with these people already exists.</p>
          <div className="flex flex-col gap-1">
            <button type="button" onClick={() => onContinueChat(exactMatch.id, false)} className="btn">
              Continue there
            </button>
          </div>
        </>
      )}

      {lookupDone && !exactMatch && matchGroup && (
        <>
          <p className="text-sm">
            These people are all in the group <span className="font-medium">{matchGroup.name}</span>.
          </p>
          <div className="flex flex-col gap-1">
            <button type="button" onClick={() => onContinueChat(matchGroup.id, true)} className="btn">
              Continue in group
            </button>
          </div>
        </>
      )}

      {lookupDone && !exactMatch && !matchGroup && (
        <>
          <div className="flex flex-col gap-1">
            <button type="button" onClick={() => submit(true)} disabled={submitting} className="btn">
              Give access to history
            </button>
            <button type="button" onClick={() => submit(false)} disabled={submitting} className="btn">
              Start a new conversation
            </button>
          </div>
          {error && (
            <div role="alert" className="text-xs font-medium bg-error text-error-content rounded-md px-2 py-1">
              {error}
            </div>
          )}
        </>
      )}
    </div>
  )
}
