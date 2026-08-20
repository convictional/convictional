import { useState } from "react"

import { BackButton } from "~/react/composites/BackButton"
import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { SharingDropdown, type SharingOption } from "~/react/composites/SharingDropdown"
import { SubscriptionBell, type SubscriptionBellProps } from "~/react/composites/SubscriptionBell"
import { WorkspaceCollaborators } from "~/react/composites/workspaceCollaborators/WorkspaceCollaborators"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import type { BackNavigation, DocumentShowResponse, Sharing } from "~/react/shared/types"
import { StickyHeader } from "~/react/ui/StickyHeader"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

const DOCUMENT_SHARING_OPTIONS: SharingOption[] = [
  { value: "private", label: "Private", description: "Only collaborators can access", icon: "lock" },
  {
    value: "organization",
    label: "Organization",
    description: "Everyone can view, collaborators can edit",
    icon: "public",
  },
]

interface Props {
  documentId: string
  back: BackNavigation
  metadata: DocumentShowResponse | null
  onSharingChange: (sharing: Sharing) => void
  savingTitle: boolean
  titleEverChanged: boolean
  subscriptionBell: Omit<SubscriptionBellProps, "portalTarget">
}

export function DocumentEditorHeader({
  documentId,
  back,
  metadata,
  onSharingChange,
  savingTitle,
  titleEverChanged,
  subscriptionBell,
}: Props) {
  return (
    <StickyHeader>
      <div className="flex items-center gap-2 p-2">
        {/* navLink so the back target client-routes when it's a registered SPA
            path, e.g. the documents index. */}
        <BackButton back={back} iconOnly navLink />
        <div className="border-l border-base-300 h-5 hidden sm:block" />
        <div id="document-toolbar-target" className="hidden sm:flex items-center gap-1" />
        <div className="flex items-center gap-2 ml-auto">
          <div id="document-sync-status-target" className="hidden sm:block" />
          {titleEverChanged && <SaveIndicator saving={savingTitle} />}
          {metadata && <WorkspaceCollaborators workspaceId={metadata.workspace_id} />}
          <SharingDropdown
            patchUrl={`/api/documents/${documentId}`}
            sharing={metadata?.sharing ?? "private"}
            options={DOCUMENT_SHARING_OPTIONS}
            triggerIcon={s => (s === "organization" ? "public" : "lock")}
            triggerIconClassName="text-base"
            errorMessage="Failed to update sharing. Please try again."
            onOptimisticChange={onSharingChange}
            onRevert={onSharingChange}
          />
          <SubscriptionBell {...subscriptionBell} />
          <DeleteButton documentId={documentId} isCreator={metadata?.is_creator ?? false} />
        </div>
      </div>
    </StickyHeader>
  )
}

function SaveIndicator({ saving }: { saving: boolean }) {
  return (
    <div className="text-base-500 flex items-center gap-1">
      {saving ? (
        <span className="loading loading-spinner loading-xs" />
      ) : (
        <span className="material-symbols-outlined text-lg">check</span>
      )}
      <p className="text-sm hidden sm:block">{saving ? "Saving..." : "Saved"}</p>
    </div>
  )
}

function DeleteButton({ documentId, isCreator }: { documentId: string; isCreator: boolean }) {
  const [deleting, setDeleting] = useState(false)

  if (!isCreator) {
    return (
      <Tooltip content="Only the document creator can delete">
        <button type="button" className="btn btn-square" disabled>
          <span className="material-symbols-outlined text-lg">delete</span>
        </button>
      </Tooltip>
    )
  }

  async function handleDelete() {
    if (deleting) return
    if (!(await confirm({ message: "Are you sure you want to delete this document?" }))) return
    setDeleting(true)
    try {
      await apiFetch(`/api/documents/${documentId}`, { method: "DELETE" })
      boostedNavigate("/documents")
    } catch (error) {
      setDeleting(false)
      const status = error instanceof ApiError ? error.status : 0
      showFlash(
        status === 403 ? "Only the document creator can delete." : "Failed to delete. Please try again.",
        "error"
      )
    }
  }

  return (
    <Tooltip content="Delete document">
      <button
        type="button"
        className="btn btn-square"
        onClick={handleDelete}
        disabled={deleting}
        aria-label="Delete document"
      >
        <span className="material-symbols-outlined text-lg">delete</span>
      </button>
    </Tooltip>
  )
}
