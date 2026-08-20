import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useState } from "react"

import {
  addCollaboratorToMetadata,
  chatMetadataQueryKey,
  chatMetadataQueryOptions,
  removeCollaboratorFromMetadata,
} from "~/react/composites/chat/chatMetadata"
import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { useChatChannel } from "~/react/shared/hooks/useChatChannel"
import type { ChatCollaborator, ChatMetadata, User } from "~/react/shared/types"
import { ChannelEventAction, ChannelEventResource } from "~/types/channels"

interface AddCollaboratorResponse {
  chat_id: string
  added: boolean
}

export interface CollaboratorArchiveState {
  conflictingDmId: string | null
}

const EMPTY_COLLABORATORS: ChatCollaborator[] = []

// Collaborators live on the shared chat-metadata cache — a parallel local list
// would be exactly the duplicate store the ADR warns against. This hook selects
// them out, patches them on channel events, and keeps only the transient UI
// signals (archived morph, self-removed) in local state.
export function useChatCollaborators(chatId: string, workspaceId: string | null, currentUserId: string | null) {
  const queryClient = useQueryClient()
  const { data: collaborators = EMPTY_COLLABORATORS } = useQuery({
    ...chatMetadataQueryOptions(chatId),
    select: metadata => metadata.collaborators,
  })
  const [archived, setArchived] = useState<CollaboratorArchiveState | null>(null)
  const [selfRemoved, setSelfRemoved] = useState(false)

  useChatChannel(chatId, workspaceId, ChannelEventResource.CHAT_COLLABORATOR, (action, data) => {
    if (action === ChannelEventAction.ADDED) {
      const user = data.user as User | undefined
      if (!user) return
      queryClient.setQueryData<ChatMetadata>(chatMetadataQueryKey(chatId), prev =>
        addCollaboratorToMetadata(prev, { id: `pending-${user.id}`, user })
      )
    } else if (action === ChannelEventAction.REMOVED) {
      const userId = data.user_id as string | undefined
      if (!userId) return
      queryClient.setQueryData<ChatMetadata>(chatMetadataQueryKey(chatId), prev =>
        removeCollaboratorFromMetadata(prev, userId)
      )
      if (userId === currentUserId) setSelfRemoved(true)
    } else if (action === ChannelEventAction.ARCHIVED) {
      const morph = (data.conflicting_dm_id as string | null | undefined) ?? null
      setArchived({ conflictingDmId: morph })
    }
  })

  const addCollaborator = useCallback(
    async (userId: string, shareHistory: boolean): Promise<{ chatId: string; added: boolean; error?: string }> => {
      try {
        const data = await apiFetch<AddCollaboratorResponse>(`/api/chats/${chatId}/collaborators`, {
          method: "POST",
          body: JSON.stringify({ user_id: userId, share_history: shareHistory }),
        })
        return { chatId: data.chat_id, added: data.added }
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Couldn't add collaborator."
        return { chatId, added: false, error: message }
      }
    },
    [chatId]
  )

  const selfLeave = useCallback(() => {
    if (!currentUserId) return
    queryClient.setQueryData<ChatMetadata>(chatMetadataQueryKey(chatId), prev =>
      removeCollaboratorFromMetadata(prev, currentUserId)
    )
    setSelfRemoved(true)
  }, [chatId, currentUserId, queryClient])

  const removeCollaborator = useCallback(
    async (userId: string): Promise<{ error?: string }> => {
      try {
        await apiFetch(`/api/chats/${chatId}/collaborators/${userId}`, { method: "DELETE" })
        return {}
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Couldn't remove collaborator."
        return { error: message }
      }
    },
    [chatId]
  )

  return {
    collaborators,
    archived,
    selfRemoved,
    selfLeave,
    addCollaborator,
    removeCollaborator,
  }
}
