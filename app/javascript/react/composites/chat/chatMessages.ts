import { queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { MessageListResponse } from "~/react/shared/types"

// The cache value is the MessageListResponse-shaped window: the sorted message
// list plus the *older* (backward) cursor from the last load. Channel patches and
// pagination rewrite `.messages`; the forward-window state (atTail, hasNewer, the
// newer cursor) stays local in useChat since it's only meaningful transiently
// after a jumpToMessage. In composites/ so both chatShow and chatPanel consume it.
export type ChatMessagesData = MessageListResponse

export function chatMessagesQueryKey(chatId: string) {
  return ["chat", chatId, "messages"] as const
}

// Channel-backed: the chat channel's message events patch this cache and
// reconnect/re-arm merge into it, so no background refetch. The queryFn is the
// initial no-cursor tail load.
export function chatMessagesQueryOptions(chatId: string | null) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: chatMessagesQueryKey(chatId ?? ""),
    enabled: !!chatId,
    queryFn: ({ signal }) => apiFetch<MessageListResponse>(`/api/chats/${chatId}/messages`, { signal }),
  })
}
