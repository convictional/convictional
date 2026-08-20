import { createPortal } from "react-dom"

import type { SyncStatus as SyncStatusType } from "~/react/composites/editor/types"

interface SyncStatusContentProps {
  status: SyncStatusType
  docSynced: boolean
  className?: string
}

interface SyncStatusProps extends SyncStatusContentProps {
  portalTarget: HTMLElement | null
}

export function SyncStatus({ portalTarget, ...content }: SyncStatusProps) {
  if (!portalTarget) return null
  return createPortal(<SyncStatusContent {...content} />, portalTarget)
}

export function SyncStatusContent({ status, docSynced, className = "" }: SyncStatusContentProps) {
  // Nothing to show when fully connected and synced
  if (status === "connected" && docSynced) return null

  let icon: string
  let label: string
  let toneClass: string

  if (status === "disconnected") {
    icon = "cloud_off"
    label = "Offline"
    toneClass = "text-error-content"
  } else if (!docSynced) {
    icon = "sync"
    label = "Loading..."
    toneClass = "text-base-600"
  } else {
    // connecting but doc already synced (reconnecting)
    icon = "sync"
    label = "Reconnecting..."
    toneClass = "text-base-600"
  }

  return (
    <div className={`flex items-center gap-1 text-sm ${toneClass} ${className}`}>
      <span className="material-symbols-outlined text-lg">{icon}</span>
      <span>{label}</span>
    </div>
  )
}
