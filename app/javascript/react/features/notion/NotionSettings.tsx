import { useEffect, useRef } from "react"

import { useBoostIslandLinks } from "~/react/shared/hooks/useBoostIslandLinks"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadingState } from "~/react/ui/LoadingState"
import { ConnectionPanel } from "./components/ConnectionPanel"
import { NotionPageTree } from "./components/NotionPageTree"
import { SyncStatus } from "./components/SyncStatus"
import { useNotionIntegration } from "./hooks/useNotionIntegration"
import { useNotionTree } from "./hooks/useNotionTree"

export function NotionSettings() {
  const { status, statusLoading, statusError, connect, disconnect, sync } = useNotionIntegration()

  const isConnected = !!status?.is_connected
  const tree = useNotionTree(isConnected)

  // Boost the "Open document" anchors the tree renders so opening one stays a
  // same-realm navigation instead of a hard reload that strands the realm
  // (#8744). Re-process when the tree grows or a node updates (new imported
  // anchors appear as nodes load/expand) and when the connection toggles the
  // tree's presence.
  const rootRef = useRef<HTMLDivElement>(null)
  useBoostIslandLinks(rootRef, [isConnected, tree.topIds, tree.nodesById])

  // Clear the tree whenever the connection goes away, so its state never leaks
  // across connections (mirrors useNotionIntegration's disconnect intent).
  useEffect(() => {
    if (!isConnected) tree.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConnected])

  if (statusLoading && status === null) {
    return <LoadingState />
  }

  if (statusError || status === null) {
    return <ErrorState message="Failed to load the Notion integration. Please try refreshing the page." />
  }

  return (
    <div ref={rootRef} className="space-y-6">
      <ConnectionPanel
        isConnected={status.is_connected}
        workspaceName={status.workspace_name}
        onConnect={connect}
        onDisconnect={disconnect}
      />

      {status.is_connected && (
        <>
          <SyncStatus lastSyncedAt={status.last_synced_at} onSync={sync} disabled={tree.syncDisabled} />
          <NotionPageTree
            topIds={tree.topIds}
            nodesById={tree.nodesById}
            loading={tree.loading}
            error={tree.error}
            hasMore={tree.hasMore}
            loadingMore={tree.loadingMore}
            onLoadMore={tree.loadMoreTop}
            onToggleExpanded={tree.toggleExpanded}
            onToggleSelection={tree.toggleSelection}
            onLoadMoreChildren={tree.loadMoreChildren}
            onRetryChildren={tree.retryChildren}
          />
        </>
      )}
    </div>
  )
}
