import { useCallback, useEffect, useRef } from "react"

import { getChannelsClient } from "~/channels/client"
import { apiFetch } from "../apiFetch"
import { compareMessages, mergeDedup } from "../chatMessageOrdering"
import type { ChatMessage, MessageListResponse } from "../types"

interface CatchUpOptions {
  chatId: string | null
  workspaceId: string | null
  // Writes the merged tail into the chat's message store. useChat supplies this
  // (it owns the Query cache key), so this shared hook stays layer-clean and
  // doesn't import the composites-layer query module.
  setMessages: React.Dispatch<React.SetStateAction<ChatMessage[]>>
  // Gates the merge: the latest page may only be spliced in when the loaded bottom
  // is the live tail. While viewing a not-caught-up historical window it's skipped
  // (splicing would leave a gap). A getter, not a boolean, so the gate reads the
  // live value at catch-up time. Defaults to true (merge) when no getter is given.
  isAtTail?: () => boolean
}

/**
 * Recovers missed messages after a WebSocket reconnect or a subscription re-arm,
 * merging the latest page with existing state to avoid duplicates. The initial
 * load is owned by useChat's `useQuery`; this hook only handles catch-up.
 *
 * Returns `catchUp`, which useChat also fires on a warm-cache remount (the SPA
 * navigation re-arm case, where the socket never dropped so no "reconnected"
 * fires but events were missed while unmounted).
 */
export function useCatchUpMessages({ chatId, workspaceId, setMessages, isAtTail }: CatchUpOptions) {
  const isAtTailRef = useRef(isAtTail)
  useEffect(() => {
    isAtTailRef.current = isAtTail
  })
  const notAtTail = () => isAtTailRef.current?.() === false

  const mergeMessages = useCallback(
    (incoming: ChatMessage[]) => {
      setMessages(prev => {
        const merged = mergeDedup(prev, incoming, "newer")
        if (merged.length === prev.length) return prev
        return merged.sort(compareMessages)
      })
    },
    [setMessages]
  )

  const catchUp = useCallback(
    async (signal?: AbortSignal) => {
      if (!chatId || notAtTail()) return
      const resp = await apiFetch<MessageListResponse>(`/api/chats/${chatId}/messages`, { signal })
      // Re-check after the await: the user may have jumped into a historical
      // window while this fetch was in flight. Merging the latest page now would
      // splice it onto the window (and sort), leaving a gap.
      if (notAtTail()) return
      mergeMessages(resp.messages)
    },
    [chatId, mergeMessages]
  )

  useEffect(() => {
    const client = getChannelsClient()
    if (!chatId || !workspaceId || !client) return
    const controller = new AbortController()
    const onReconnect = () => {
      void catchUp(controller.signal).catch(() => {})
    }
    client.on("reconnected", onReconnect)
    return () => {
      controller.abort()
      client.off("reconnected", onReconnect)
    }
  }, [chatId, workspaceId, catchUp])

  return { catchUp }
}
