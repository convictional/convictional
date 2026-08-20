import { useCallback } from "react"

import { useChannel } from "~/react/shared/hooks/useChannel"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

export interface WorkspaceEventBroadcast {
  eventId: string
  eventAction: string
  recordableType: string
  recordableId: string
  creatorId: string | null
}

// System events (null creator) still nudge — the user didn't cause them.
export function isOwnWorkspaceEvent(event: WorkspaceEventBroadcast, currentUserId: string | null): boolean {
  return currentUserId !== null && event.creatorId === currentUserId
}

interface UseWorkspaceEventsChannelOptions {
  workspaceId: string | null
  onEventAdded: (event: WorkspaceEventBroadcast) => void
}

// Subscribes to the workspace-wide `workspace_events` channel. The JSON peer
// emits WORKSPACE_EVENT/ADDED with the new event's identifiers and recordable
// info — not the rendered HTML. The consumer is responsible for refetching the
// thread's timeline (via GET /api/email_threads/{id}) to pick up the rendered
// activity HTML. Comment-creation activity arrives here as well (action ==
// "commented"); the consumer should branch on event_action.
//
// **No sender-skip**: this channel is the sole writer to the React timeline
// for activity events, including comments. The comment form does not
// optimistically append, so skipping the actor would mean their own comment
// never lands. The comment form handles its own optimistic insert; skipping
// the actor here would hide their comment from the activity feed.
export function useWorkspaceEventsChannel({ workspaceId, onEventAdded }: UseWorkspaceEventsChannelOptions): void {
  const handleEvent = useCallback(
    (action: ChannelEventAction, data: Record<string, unknown>) => {
      if (action !== ChannelEventAction.ADDED) return
      const eventId = data.event_id
      const eventAction = data.event_action
      const recordableType = data.recordable_type
      const recordableId = data.recordable_id
      if (
        typeof eventId !== "string" ||
        typeof eventAction !== "string" ||
        typeof recordableType !== "string" ||
        typeof recordableId !== "string"
      ) {
        return
      }
      onEventAdded({
        eventId,
        eventAction,
        recordableType,
        recordableId,
        creatorId: typeof data.creator_id === "string" ? data.creator_id : null,
      })
    },
    [onEventAdded]
  )

  useChannel(
    workspaceId ? { stream: ChannelStream.WORKSPACE_EVENTS, params: { workspace_id: workspaceId } } : null,
    ChannelEventResource.WORKSPACE_EVENT,
    handleEvent
  )
}
