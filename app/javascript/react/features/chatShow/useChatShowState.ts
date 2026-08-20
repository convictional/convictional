import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import { chatMetadataQueryKey, chatMetadataQueryOptions } from "~/react/composites/chat/chatMetadata"
import { useChat } from "~/react/composites/chat/useChat"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useReconnectInvalidate } from "~/react/shared/hooks/useReconnectInvalidate"
import type { ChatMetadata } from "~/react/shared/types"

export function useChatShowState(chatId: string) {
  const queryClient = useQueryClient()
  const metadataQuery = useQuery(chatMetadataQueryOptions(chatId))
  const metadata = metadataQuery.data ?? null
  const metadataError = metadataQuery.isError

  // Metadata is channel-backed (channelQueryDefaults: no retry/refetch), so a
  // failed load or collaborator events missed while the socket was down only
  // recover on an explicit invalidate — wire the reconnect recovery the list and
  // messages caches already have, rather than stranding the page on a skeleton.
  useReconnectInvalidate(chatMetadataQueryKey(chatId), "useChatShowState metadata")

  const workspaceId = metadata?.workspace_id ?? null
  const { user } = useCurrentUser()
  // Gate currentUserId on metadata being loaded so the markRead effect in
  // useChat fires once both the chat-show fetch and the /users/me fetch have
  // resolved — same one-shot trigger we relied on before user moved into a
  // separate fetch.
  const currentUserId = metadata && user ? user.id : null
  const currentUserDisplayName = metadata && user ? user.display_name : null

  const chat = useChat({
    chatId,
    workspaceId,
    currentUserId,
    currentUserDisplayName,
    initialLastReadAt: metadata?.last_read_at ?? null,
    initialUnreadCount: metadata?.unread_message_count ?? 0,
    mailboxEntryId: metadata?.mailbox?.id ?? null,
    markReadOnOpen: true,
    enableTyping: true,
  })

  const renameMutation = useMutation({
    mutationFn: (title: string | null) =>
      apiFetch<{ id: string; title: string | null; chat_title: string }>(`/api/chats/${chatId}`, {
        method: "PATCH",
        body: JSON.stringify({ title }),
      }),
    onSuccess: data => {
      queryClient.setQueryData<ChatMetadata>(chatMetadataQueryKey(chatId), prev =>
        prev ? { ...prev, chat_title: data.chat_title } : prev
      )
    },
  })

  const renameChat = useCallback(
    async (title: string | null): Promise<{ error?: string }> => {
      try {
        await renameMutation.mutateAsync(title)
        return {}
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Couldn't rename chat."
        return { error: message }
      }
    },
    [renameMutation]
  )

  return {
    metadata,
    metadataError,
    renameChat,
    ...chat,
  }
}
