import { useEffect, useRef } from "react"

import { ChannelEventAction, ChannelEventResource } from "~/types/channels"
import { insertInOrder } from "../chatMessageOrdering"
import { reportOutOfOrderDelivery } from "../reportOutOfOrderDelivery"
import type { ChatMessage } from "../types"
import { useChatChannel } from "./useChatChannel"

interface ChatMessageSubscriptionOptions {
  onNewMessage?: (msg: ChatMessage) => void
  // Gates the live append: a NEW_MESSAGE may only be appended when the loaded
  // bottom is the live tail. While viewing a not-caught-up historical window it
  // would look contiguous but isn't — forward pagination (loadNewer) closes the
  // gap instead. A getter, not a boolean, so the gate reads the live value at
  // event time. Defaults to true (append) when no getter is supplied.
  isAtTail?: () => boolean
}

/**
 * Subscribes to real-time chat message events (new, updated, deleted) and
 * updates the message list accordingly. Shared between the full chat show
 * page and the DM panel. `onNewMessage` lets the caller react to incoming
 * messages (e.g. mark the chat read). `isAtTail` gates the live append;
 * UPDATED/DELETED always apply (no-op if the id isn't in the window).
 */
export function useChatMessageSubscription(
  chatId: string | null,
  workspaceId: string | null,
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>,
  { onNewMessage, isAtTail }: ChatMessageSubscriptionOptions = {}
) {
  const onNewMessageRef = useRef(onNewMessage)
  const isAtTailRef = useRef(isAtTail)
  useEffect(() => {
    onNewMessageRef.current = onNewMessage
    isAtTailRef.current = isAtTail
  })

  // React runs the setMessages updater during render, not at the call site, so the
  // detection must stash the report here for the effect below to fire after commit.
  // A single overwrite ref keeps it idempotent if the updater is ever re-invoked.
  const pendingReportRef = useRef<Parameters<typeof reportOutOfOrderDelivery>[0] | null>(null)
  useEffect(() => {
    if (!pendingReportRef.current) return
    reportOutOfOrderDelivery(pendingReportRef.current)
    pendingReportRef.current = null
  })

  useChatChannel(chatId, workspaceId, ChannelEventResource.CHAT_MESSAGE, (action, data) => {
    if (action === ChannelEventAction.NEW_MESSAGE) {
      const msg = data as unknown as ChatMessage
      // Not at the tail → dropping it is safe: loadNewer will fetch it as part
      // of closing the gap to the live tail.
      if (isAtTailRef.current?.() === false) return
      setMessages(prev => {
        const { messages, inserted, outOfOrder } = insertInOrder(prev, msg)
        if (inserted && outOfOrder) {
          const tail = prev[prev.length - 1]
          pendingReportRef.current = {
            chatId,
            messageId: msg.id,
            messageCreatedAt: msg.created_at,
            tailCreatedAt: tail?.created_at,
            gapMs: tail ? new Date(tail.created_at).getTime() - new Date(msg.created_at).getTime() : 0,
          }
        }
        return messages
      })
      onNewMessageRef.current?.(msg)
    } else if (action === ChannelEventAction.UPDATED_MESSAGE) {
      const msg = data as unknown as ChatMessage
      setMessages(prev => prev.map(m => (m.id === msg.id ? msg : m)))
    } else if (action === ChannelEventAction.DELETED_MESSAGE) {
      const id = data.id as string
      setMessages(prev => prev.filter(m => m.id !== id))
    }
  })
}
