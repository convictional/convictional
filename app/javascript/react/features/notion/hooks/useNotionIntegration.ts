import { useCallback, useEffect, useState } from "react"

import type { NotionConnectionResult, NotionStatus, NotionSyncStatus } from "~/react/features/notion/types"
import { apiFetch } from "~/react/shared/apiFetch"

// Connection lifecycle for the Notion integration: status, connect, disconnect,
// and sync. The page/tree data lives in `useNotionTree`; this hook owns only the
// connection. NotionSettings composes the two.
export function useNotionIntegration() {
  const [status, setStatus] = useState<NotionStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(true)
  const [statusError, setStatusError] = useState(false)

  const fetchStatus = useCallback(async () => {
    setStatusLoading(true)
    setStatusError(false)
    try {
      const data = await apiFetch<NotionStatus>("/api/integrations/notion/connection")
      setStatus(data)
    } catch {
      setStatusError(true)
    } finally {
      setStatusLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchStatus()
  }, [fetchStatus])

  const connect = useCallback(async (accessToken: string): Promise<NotionConnectionResult> => {
    const result = await apiFetch<NotionConnectionResult>(
      "/api/integrations/notion/connection",
      { method: "POST", body: JSON.stringify({ access_token: accessToken }) },
      { expectedStatuses: [422, 502] }
    )
    setStatus({
      is_connected: result.is_connected,
      workspace_name: result.workspace_name,
      last_synced_at: null,
    })
    return result
  }, [])

  const disconnect = useCallback(async () => {
    await apiFetch("/api/integrations/notion/connection", { method: "DELETE" })
    await fetchStatus()
  }, [fetchStatus])

  const sync = useCallback(async () => {
    const result = await apiFetch<NotionSyncStatus>("/api/integrations/notion/sync", { method: "POST" })
    setStatus(prev => (prev ? { ...prev, last_synced_at: result.last_synced_at } : prev))
  }, [])

  return {
    status,
    statusLoading,
    statusError,
    connect,
    disconnect,
    sync,
  }
}
