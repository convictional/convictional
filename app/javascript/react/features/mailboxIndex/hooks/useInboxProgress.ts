import { useCallback, useEffect, useState } from "react"

import { getChannelsClient } from "~/channels/client"
import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { type ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

import type { InboxProgressResponse } from "../types"

// The pre-load default is tuned to surface no banner until real state arrives: no sync in
// progress, and gmail assumed connected so the "connect Gmail" nag doesn't flash on load.
const EMPTY_STATE: InboxProgressResponse = {
  is_onboarding_mailbox_sync_complete: true,
  onboarding_mailbox_sync_started_at: null,
  has_gmail_integration: true,
  has_calendar_integration: false,
  is_google_authenticated: true,
}

function isInboxProgressResponse(data: unknown): data is InboxProgressResponse {
  return typeof data === "object" && data !== null && "is_onboarding_mailbox_sync_complete" in data
}

async function fetchProgress(): Promise<InboxProgressResponse | null> {
  try {
    const data = await apiFetch<InboxProgressResponse>("/api/inbox_progress")
    return isInboxProgressResponse(data) ? data : null
  } catch {
    // Inbox-progress chrome is non-critical — return null and let the next
    // WebSocket broadcast (or reconnect refetch) refresh state.
    return null
  }
}

export function useInboxProgress(userId: string | null): InboxProgressResponse {
  const [state, setState] = useState<InboxProgressResponse>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false
    // Known race: a WebSocket EVENT that lands between mount and this fetch
    // resolving will be overwritten by the (potentially older) initial snapshot.
    // Accepted: broadcasts are idempotent full snapshots, so the next one — or
    // the reconnect refetch below — restores correct state. Not worth a
    // mutatedAt-style guard for this non-critical chrome.
    fetchProgress().then(data => {
      if (!cancelled && data) setState(data)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // Refetch on websocket reconnect to recover any inbox_progress broadcasts
  // missed while disconnected — the server doesn't replay them. Without this,
  // a sync-completion broadcast that fires during a transient disconnect would
  // leave the syncing pill/banner visible until a manual page reload. Mirrors
  // the same pattern in useMailboxEntries.
  useEffect(() => {
    const client = getChannelsClient()
    if (!client) return
    const onReconnect = () => {
      fetchProgress().then(data => {
        if (data) setState(data)
      })
    }
    client.on("reconnected", onReconnect)
    return () => client.off("reconnected", onReconnect)
  }, [])

  const onMessage = useCallback((_action: ChannelEventAction, data: Record<string, unknown>) => {
    if (isInboxProgressResponse(data)) setState(data)
  }, [])
  useChannel(
    userId ? { stream: ChannelStream.INBOX_PROGRESS, params: { user_id: userId } } : null,
    ChannelEventResource.INBOX_PROGRESS,
    onMessage
  )

  return state
}
