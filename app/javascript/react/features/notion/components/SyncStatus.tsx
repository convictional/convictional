import { useState } from "react"

import { DateTime } from "~/react/ui/DateTime"
import { showFlash } from "~/shared/flash"

interface SyncStatusProps {
  lastSyncedAt: string | null
  onSync: () => Promise<void>
  // Disabled while a folder cascade is pending/running for the connection, so a
  // half-resolved selection is never imported.
  disabled?: boolean
}

export function SyncStatus({ lastSyncedAt, onSync, disabled = false }: SyncStatusProps) {
  const [syncing, setSyncing] = useState(false)

  async function handleSync() {
    if (syncing) return
    setSyncing(true)
    try {
      await onSync()
      // Sync runs as a background job (POST returns 202), so the import isn't done yet.
      showFlash("Your documents are being synced.", "success")
    } catch {
      showFlash("Couldn't start the sync. Please try again.", "error")
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 border border-neutral rounded-lg bg-base-100">
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col">
          <p className="text-sm font-semibold">Sync</p>
          <p className="text-xs opacity-60">
            {lastSyncedAt ? (
              <>
                Last synced <DateTime datetime={lastSyncedAt} format="relative" />
              </>
            ) : (
              "No sync has run yet."
            )}
          </p>
        </div>
        <button
          type="button"
          className={`btn btn-primary${syncing ? " loading loading-sm loading-spinner" : ""}`}
          disabled={syncing || disabled}
          onClick={handleSync}
        >
          Sync now
        </button>
      </div>
    </div>
  )
}
