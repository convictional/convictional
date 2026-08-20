import { queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { ChatCollaborator, ChatMetadata } from "~/react/shared/types"

// Shared by the chat show page and the chat panel, so it lives in composites/
// (both are features, which can't import each other). Same queryKey ⇒ opening a
// chat in the panel reuses the metadata the page already fetched.
export function chatMetadataQueryKey(chatId: string) {
  return ["chat", chatId, "metadata"] as const
}

// Channel-backed: the chat's CHAT_COLLABORATOR events patch collaborators into
// this cache, and useChatShowState invalidates it on reconnect, so no background
// refetch.
export function chatMetadataQueryOptions(chatId: string | null) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: chatMetadataQueryKey(chatId ?? ""),
    enabled: !!chatId,
    queryFn: ({ signal }) => apiFetch<ChatMetadata>(`/api/chats/${chatId}`, { signal }),
  })
}

// --- Pure cache-patch helpers (operate on the ChatMetadata cache value) ---

export function addCollaboratorToMetadata(metadata: ChatMetadata | undefined, collaborator: ChatCollaborator) {
  if (!metadata) return metadata
  if (metadata.collaborators.some(c => c.user.id === collaborator.user.id)) return metadata
  return { ...metadata, collaborators: [...metadata.collaborators, collaborator] }
}

export function removeCollaboratorFromMetadata(metadata: ChatMetadata | undefined, userId: string) {
  if (!metadata) return metadata
  return { ...metadata, collaborators: metadata.collaborators.filter(c => c.user.id !== userId) }
}
