import { type ChannelEventAction, type ChannelEventResource, ChannelStream } from "~/types/channels"
import { useChannel } from "./useChannel"

/**
 * Subscribe to a resource on a chat's unsigned channel. Wraps `useChannel` with the
 * shared chat topic identity (stream `"chat"`, params `chat_id`/`workspace_id`) so the
 * gating and param shape live in one place. No-ops until both ids are present.
 */
export function useChatChannel(
  chatId: string | null,
  workspaceId: string | null,
  resource: ChannelEventResource,
  onMessage: (action: ChannelEventAction, data: Record<string, unknown>) => void
): void {
  useChannel(
    chatId && workspaceId
      ? { stream: ChannelStream.CHAT, params: { chat_id: chatId, workspace_id: workspaceId } }
      : null,
    resource,
    onMessage
  )
}
