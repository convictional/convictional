import { useCallback } from "react"

import { useChannel } from "~/react/shared/hooks/useChannel"
import type { EmailMessageSummary } from "~/react/shared/types"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

interface UseEmailThreadChannelOptions {
  threadId: string | null
  onMessageAdded: (message: EmailMessageSummary) => void
}

// Subscribes to the per-thread `email_thread` channel. The JSON peer of the legacy
// HTML handler emits MESSAGE_ADDED with a metadata-only message summary; the body is
// fetched lazily from content_url like any other timeline message. The same-user
// filter is enforced server-side so this hook does not need to skip its own broadcasts.
function isEmailMessageSummary(value: unknown): value is EmailMessageSummary {
  if (!value || typeof value !== "object") return false
  const m = value as Record<string, unknown>
  return typeof m.id === "string" && typeof m.sender_email === "string" && typeof m.content_url === "string"
}

export function useEmailThreadChannel({ threadId, onMessageAdded }: UseEmailThreadChannelOptions): void {
  const handleEvent = useCallback(
    (action: ChannelEventAction, data: Record<string, unknown>) => {
      if (action !== ChannelEventAction.MESSAGE_ADDED) return
      if (!isEmailMessageSummary(data.message)) return
      onMessageAdded(data.message)
    },
    [onMessageAdded]
  )

  useChannel(
    threadId ? { stream: ChannelStream.EMAIL_THREAD, params: { thread_id: threadId } } : null,
    ChannelEventResource.EMAIL_THREAD,
    handleEvent
  )
}
