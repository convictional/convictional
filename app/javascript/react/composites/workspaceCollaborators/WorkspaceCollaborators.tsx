import { useState } from "react"

import { AvatarGroup } from "~/react/composites/AvatarGroup"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { BottomSheet } from "~/react/ui/BottomSheet"
import { Dropdown } from "~/react/ui/Dropdown"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { Tooltip } from "~/react/ui/Tooltip"
import { CollaboratorsPanel } from "./components/CollaboratorsPanel"
import { useWorkspaceCollaborators } from "./hooks/useWorkspaceCollaborators"
import type { WorkspaceCollaboratorsProps } from "./types"

interface Props extends WorkspaceCollaboratorsProps {
  onSelfRemove?: () => void
}

export function WorkspaceCollaborators({ workspaceId, onSelfRemove }: Props) {
  const isMobile = useIsMobile()
  const { data, loading, error, addCollaborator, removeCollaborator, inviteCollaborator, approveCollaborator } =
    useWorkspaceCollaborators(workspaceId)
  const { user, error: userError } = useCurrentUser()

  if (userError) return <ErrorState message="Could not load collaborators." />
  if (loading || !user) return <LoadingState className="py-1" />
  if (error || !data) return <ErrorState message={error ?? "Could not load collaborators."} />

  // Mobile keeps the trigger to at most two items — one avatar plus the "+N"
  // overflow chip — so the header row doesn't overflow.
  const maxCollaborators = isMobile ? 1 : 5
  const trigger = (
    <AvatarGroup
      layout="stack"
      users={data.collaborators.map(c => c.user)}
      presentUserIds={data.present_user_ids}
      sortPresentFirst
      max={maxCollaborators}
      emptyState={
        <Tooltip content="No collaborators">
          <div className="w-6 h-6 rounded-full bg-base-200 border-2 border-dashed border-base-400 flex items-center justify-center">
            <span className="text-xs text-base-400">?</span>
          </div>
        </Tooltip>
      }
    />
  )
  const panel = (
    <CollaboratorsPanel
      data={data}
      currentUserId={user.id}
      onAdd={addCollaborator}
      onRemove={removeCollaborator}
      onInvite={inviteCollaborator}
      onApprove={approveCollaborator}
      onSelfRemove={onSelfRemove}
    />
  )

  if (isMobile) return <MobileVariant trigger={trigger} panel={panel} />
  return <DesktopVariant trigger={trigger} panel={panel} />
}

function DesktopVariant({ trigger, panel }: { trigger: React.ReactNode; panel: React.ReactNode }) {
  return (
    <Dropdown
      placement="bottom-end"
      ariaLabel="Workspace collaborators"
      className="dropdown-card p-0 w-56 z-50"
      trigger={
        <button type="button" className="btn pl-1.5" aria-label="Collaborators" data-test-id="workspace-collaborators">
          {trigger}
          <span className="material-symbols-outlined text-lg transition -mr-1">keyboard_arrow_down</span>
        </button>
      }
    >
      {panel}
    </Dropdown>
  )
}

function MobileVariant({ trigger, panel }: { trigger: React.ReactNode; panel: React.ReactNode }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        className="btn pl-1.5"
        aria-label="Collaborators"
        data-test-id="workspace-collaborators"
        onClick={() => setOpen(true)}
      >
        {trigger}
        <span className="material-symbols-outlined text-lg -mr-1">keyboard_arrow_down</span>
      </button>
      {open && (
        <BottomSheet title="Collaborators" onClose={() => setOpen(false)}>
          <div className="overflow-y-auto pb-4">{panel}</div>
        </BottomSheet>
      )}
    </>
  )
}
