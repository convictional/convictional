import { useMemo, useState, type FormEvent } from "react"

import { UserDateTime } from "~/react/composites/UserDateTime"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import type { Collaborator, CollaboratorViewState, User, WorkspaceCollaboratorsData } from "~/react/shared/types"
import { Avatar } from "~/react/ui/Avatar"
import { Tooltip } from "~/react/ui/Tooltip"

interface CollaboratorsPanelProps {
  data: WorkspaceCollaboratorsData
  currentUserId: string
  onAdd: (userId: string) => Promise<void>
  onRemove: (userId: string) => Promise<void>
  onInvite: (email: string, reason: string) => Promise<void>
  onApprove: (collaboratorId: string) => Promise<void>
  onSelfRemove?: () => void
}

export function CollaboratorsPanel({
  data,
  currentUserId,
  onAdd,
  onRemove,
  onInvite,
  onApprove,
  onSelfRemove,
}: CollaboratorsPanelProps) {
  // "Everyone else" = org members who aren't already approved collaborators,
  // derived from the shared store instead of a redundant server-sent list.
  // Pending access-requesters stay listed here too (matching the pre-store
  // behaviour) so an admin can add them directly rather than only via the
  // "Requested Access" approve action.
  const { users: orgUsers } = useOrganizationMembers()
  const availableUsers = useMemo(() => {
    const taken = new Set(data.collaborators.map(c => c.user.id))
    return orgUsers.filter(u => !taken.has(u.id))
  }, [orgUsers, data.collaborators])

  return (
    <>
      <CurrentCollaborators
        collaborators={data.collaborators}
        currentUserId={currentUserId}
        onRemove={onRemove}
        onSelfRemove={onSelfRemove}
      />
      <div className="divider my-0" />
      {data.pending.length > 0 && (
        <>
          <PendingRequests pending={data.pending} onApprove={onApprove} />
          <div className="divider my-0" />
        </>
      )}
      <EveryoneElse available={availableUsers} onAdd={onAdd} />
      <div className="divider my-0" />
      <InviteForm onInvite={onInvite} />
    </>
  )
}

function CurrentCollaborators({
  collaborators,
  currentUserId,
  onRemove,
  onSelfRemove,
}: {
  collaborators: Collaborator[]
  currentUserId: string
  onRemove: (userId: string) => Promise<void>
  onSelfRemove?: () => void
}) {
  return (
    <div className="p-2">
      <span className="text-xs font-semibold opacity-75 px-1">Collaborators</span>
      <ul className="max-h-32 overflow-y-auto grid gap-1" data-test-id="current-collaborators">
        {collaborators.map(c => (
          <li key={c.id}>
            <CollaboratorRow
              collaborator={c}
              isSelf={c.user.id === currentUserId}
              onRemove={onRemove}
              onSelfRemove={onSelfRemove}
            />
          </li>
        ))}
      </ul>
    </div>
  )
}

function CollaboratorRow({
  collaborator,
  isSelf,
  onRemove,
  onSelfRemove,
}: {
  collaborator: Collaborator
  isSelf: boolean
  onRemove: (userId: string) => Promise<void>
  onSelfRemove?: () => void
}) {
  const [removing, setRemoving] = useState(false)
  if (!collaborator.is_removable) {
    return (
      <div className="dropdown-item cursor-default px-1 py-0 grid grid-cols-[auto_1fr_auto] items-center gap-2">
        <Avatar displayName={collaborator.user.display_name} picture={collaborator.user.picture} size="small" />
        <div className="grid min-w-0">
          <span className="text-xs font-semibold truncate">{collaborator.user.display_name}</span>
          {/* Own view state is unreliable (the visit records as the page loads) and redundant —
              you know whether you've opened it — so only show it for other collaborators. */}
          {!isSelf && <ViewStateIndicator viewState={collaborator.view_state} />}
        </div>
        <Tooltip content="Can not be removed">
          <span className="material-symbols-outlined text-base opacity-50 cursor-default">lock</span>
        </Tooltip>
      </div>
    )
  }

  return (
    <button
      type="button"
      disabled={removing}
      className="dropdown-item px-1 py-0.5 w-full"
      onClick={async () => {
        setRemoving(true)
        try {
          await onRemove(collaborator.user.id)
          if (isSelf) onSelfRemove?.()
        } finally {
          setRemoving(false)
        }
      }}
    >
      <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
        <Avatar displayName={collaborator.user.display_name} picture={collaborator.user.picture} size="small" />
        <div className="grid min-w-0 text-left">
          <span className="text-xs font-semibold truncate">{collaborator.user.display_name}</span>
          {/* Own view state is unreliable (the visit records as the page loads) and redundant —
              you know whether you've opened it — so only show it for other collaborators. */}
          {!isSelf && <ViewStateIndicator viewState={collaborator.view_state} />}
        </div>
        <span className="material-symbols-outlined text-base">close</span>
      </div>
    </button>
  )
}

// Shows whether this collaborator has opened the resource, with a relative timestamp
// when the visit is recorded. Displays "Not viewed yet" for collaborators with no Visit.
function ViewStateIndicator({ viewState }: { viewState: CollaboratorViewState }) {
  return (
    <span className="text-[0.65rem] opacity-60 truncate" data-test-id="collaborator-view-state">
      {viewState.viewed && viewState.last_viewed_at ? (
        <>
          Viewed <UserDateTime datetime={viewState.last_viewed_at} format="relative" />
        </>
      ) : viewState.viewed ? (
        "Viewed"
      ) : (
        "Not viewed yet"
      )}
    </span>
  )
}

function PendingRequests({
  pending,
  onApprove,
}: {
  pending: Collaborator[]
  onApprove: (collaboratorId: string) => Promise<void>
}) {
  return (
    <div className="px-4">
      <span className="text-xs font-semibold opacity-75">Requested Access</span>
      <div className="max-h-32 overflow-y-auto">
        {pending.map(c => (
          <div key={c.id} className="flex flex-col w-full">
            <div className="flex w-full max-w-full gap-2 justify-between">
              <div className="flex items-center gap-2 my-2 truncate">
                <Avatar displayName={c.user.display_name} picture={c.user.picture} size="small" />
                <span className="text-xs font-semibold truncate">{c.user.display_name}</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="material-symbols-outlined text-lg"
                  aria-label={`Approve ${c.user.display_name}`}
                  onClick={() => onApprove(c.id)}
                >
                  add
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function EveryoneElse({ available, onAdd }: { available: User[]; onAdd: (userId: string) => Promise<void> }) {
  return (
    <div>
      <span className="text-xs font-semibold opacity-75 px-3">Everyone else</span>
      <div className="max-h-56 overflow-y-auto px-2 grid gap-1">
        {available.length === 0 ? (
          <span className="text-xs text-center text-pretty text-base-content py-2">
            Everyone in your organization has been invited.
          </span>
        ) : (
          available.map(user => <AddRow key={user.id} user={user} onAdd={onAdd} />)
        )}
      </div>
    </div>
  )
}

function AddRow({ user, onAdd }: { user: User; onAdd: (userId: string) => Promise<void> }) {
  const [adding, setAdding] = useState(false)
  return (
    <div data-test-id={`add-collaborator-${user.id}`}>
      <button
        type="button"
        disabled={adding}
        className="dropdown-item px-1 py-0 w-full"
        onClick={async () => {
          setAdding(true)
          try {
            await onAdd(user.id)
          } finally {
            setAdding(false)
          }
        }}
      >
        <div className="grid grid-cols-[auto_1fr_auto] items-center gap-2">
          <Avatar displayName={user.display_name} picture={user.picture} size="small" />
          <span className="text-xs font-semibold truncate text-left">{user.display_name}</span>
          <span className="material-symbols-outlined text-lg">add</span>
        </div>
      </button>
    </div>
  )
}

function InviteForm({ onInvite }: { onInvite: (email: string, reason: string) => Promise<void> }) {
  const [isInviting, setIsInviting] = useState(false)
  const [email, setEmail] = useState("")
  const [reason, setReason] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await onInvite(email, reason)
      setEmail("")
      setReason("")
      setIsInviting(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : "There was a problem inviting this person.")
    } finally {
      setSubmitting(false)
    }
  }

  if (!isInviting) {
    return (
      <button
        type="button"
        className="block w-full link text-center text-xs -mt-1 pb-1"
        onClick={() => setIsInviting(true)}
      >
        Invite a new team member
      </button>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2 px-4 pb-4">
      <div className="fieldset">
        <label className="label p-0" htmlFor="invite-email">
          <span className="label-text text-xs">Email address</span>
        </label>
        <input
          id="invite-email"
          type="email"
          required
          placeholder="Email address"
          className="input input-xs w-full"
          value={email}
          onChange={e => setEmail(e.target.value)}
        />
      </div>
      <div className="fieldset">
        <label className="label p-0" htmlFor="invite-reason">
          <span className="label-text text-xs">Message (optional)</span>
        </label>
        <input
          id="invite-reason"
          type="text"
          placeholder="to..."
          className="input input-xs w-full"
          value={reason}
          onChange={e => setReason(e.target.value)}
        />
      </div>
      {error && <p className="text-xs text-error">{error}</p>}
      <div className="flex gap-2 justify-end">
        <button type="button" className="btn btn-sm btn-ghost" onClick={() => setIsInviting(false)}>
          Nevermind
        </button>
        <button type="submit" disabled={submitting} className="btn btn-sm btn-primary">
          Invite and add
        </button>
      </div>
    </form>
  )
}
