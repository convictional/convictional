import { useCallback, useEffect, useRef } from "react"

import { getChannelsClient } from "~/channels/client"
import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { usePaginatedList } from "~/react/shared/hooks/usePaginatedList"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

import type { ScheduledResearch, ScheduledResearchListResponse } from "../types"

interface PreparedEvent {
  schedule_id?: string
}

export function useScheduledResearchData() {
  const { user } = useCurrentUser()

  const { items, loading, loadingMore, error, hasMore, loadMore, reload, setItems } = usePaginatedList<
    ScheduledResearch,
    ScheduledResearchListResponse
  >({
    buildUrl: cursor =>
      cursor ? `/api/scheduled_research?cursor=${encodeURIComponent(cursor)}` : "/api/scheduled_research",
    select: data => data.scheduled_researches,
  })

  // Mirror items into a ref so the channel/reconnect handlers (async, after
  // commit) can read the current list without re-subscribing on every change.
  // Assigned during render, not in an effect: a `changed` event can fire in the
  // same tick the list first commits, and a passive-effect sync lags far enough
  // behind that the handler would read a stale ref and spuriously refetch.
  const itemsRef = useRef(items)
  itemsRef.current = items

  const applyCreated = useCallback(
    (item: ScheduledResearch) => {
      setItems(prev => (prev.some(s => s.id === item.id) ? prev : [item, ...prev]))
    },
    [setItems]
  )

  // Guard against bursts of unknown-id events (e.g. multiple off-screen rows updating in quick
  // succession) triggering a refetch each time.
  const unknownIdRefetchPendingRef = useRef(false)

  const applyUpdated = useCallback(
    (item: ScheduledResearch) => {
      if (!itemsRef.current.some(s => s.id === item.id)) {
        // Event arrived for an id we don't have locally (e.g. paginated off-screen). Refetch
        // so we don't silently drop the update — but coalesce bursts so we fire at most once.
        if (unknownIdRefetchPendingRef.current) return
        unknownIdRefetchPendingRef.current = true
        void reload().finally(() => {
          unknownIdRefetchPendingRef.current = false
        })
        return
      }
      setItems(prev => prev.map(s => (s.id === item.id ? item : s)))
    },
    [reload, setItems]
  )

  const applyDeleted = useCallback(
    (id: string) => {
      setItems(prev => prev.filter(s => s.id !== id))
    },
    [setItems]
  )

  // Title preparation broadcasts: update the title in place so the "Title in progress…" pulse
  // resolves as soon as the job lands. Refetch the row so we also pick up `preparation_failed_at`
  // in one place; the broadcast itself doesn't include it.
  useChannel(
    user?.id ? { stream: ChannelStream.SCHEDULED_RESEARCH, params: { user_id: user.id } } : null,
    ChannelEventResource.SCHEDULED_RESEARCH,
    (_action, data) => {
      const event = data as PreparedEvent
      if (!event.schedule_id) return
      apiFetch<ScheduledResearch>(`/api/scheduled_research/${event.schedule_id}`)
        .then(fresh => setItems(prev => prev.map(s => (s.id === fresh.id ? fresh : s))))
        .catch(() => {})
    }
  )

  // PG NOTIFY/LISTEN is fire-and-forget, so any `prepared` event broadcast while the socket was
  // down is lost. On reconnect, refetch any rows still waiting for a title.
  useEffect(() => {
    const client = getChannelsClient()
    if (!client) return

    const onReconnect = () => {
      const pending = itemsRef.current.filter(s => s.title === "Untitled" && !s.preparation_failed_at)
      for (const s of pending) {
        apiFetch<ScheduledResearch>(`/api/scheduled_research/${s.id}`)
          .then(fresh => setItems(prev => prev.map(p => (p.id === fresh.id ? fresh : p))))
          .catch(() => {})
      }
    }

    client.on("reconnected", onReconnect)
    return () => {
      client.off("reconnected", onReconnect)
    }
  }, [setItems])

  return {
    items,
    loading,
    loadingMore,
    error,
    hasMore,
    loadMore,
    applyCreated,
    applyUpdated,
    applyDeleted,
    refetch: reload,
  }
}
