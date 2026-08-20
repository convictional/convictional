import { useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import {
  useWorkspaceCollaboratorsQuery,
  workspaceCollaboratorsQueryKey,
} from "~/react/shared/hooks/useWorkspaceCollaboratorsQuery"
import type { WorkspaceCollaboratorsData } from "~/react/shared/types"

export interface UseWorkspaceCollaboratorsResult {
  data: WorkspaceCollaboratorsData | null
  loading: boolean
  error: string | null
  addCollaborator: (userId: string, reason?: string) => Promise<void>
  removeCollaborator: (userId: string) => Promise<void>
  inviteCollaborator: (email: string, reason?: string) => Promise<void>
  approveCollaborator: (collaboratorId: string) => Promise<void>
}

export function useWorkspaceCollaborators(workspaceId: string): UseWorkspaceCollaboratorsResult {
  const queryClient = useQueryClient()
  const query = useWorkspaceCollaboratorsQuery(workspaceId)
  const key = workspaceCollaboratorsQueryKey(workspaceId)

  // Mutations return the fresh payload; seed the cache so the panel reflects the change
  // immediately without waiting for the channel round-trip.
  const mutate = useCallback(
    async (path: string, init: RequestInit) => {
      const response = await apiFetch<WorkspaceCollaboratorsData>(
        `/api/workspaces/${workspaceId}/collaborators${path}`,
        init
      )
      queryClient.setQueryData(key, response)
    },
    [workspaceId, queryClient, key]
  )

  const addCollaborator = useCallback(
    async (userId: string, reason = "") => {
      await mutate("", { method: "POST", body: JSON.stringify({ user_id: userId, reason }) })
    },
    [mutate]
  )

  const removeCollaborator = useCallback(
    async (userId: string) => {
      await apiFetch(`/api/workspaces/${workspaceId}/collaborators/${userId}`, { method: "DELETE" })
      await queryClient.invalidateQueries({ queryKey: key })
    },
    [workspaceId, queryClient, key]
  )

  const inviteCollaborator = useCallback(
    async (email: string, reason = "") => {
      try {
        // Inviting by email can create a brand-new org user; the organization_members
        // channel broadcasts the add, so every session refreshes the shared store.
        await mutate("/invite", { method: "POST", body: JSON.stringify({ email, reason }) })
      } catch (err) {
        const detail = err instanceof ApiError && typeof err.body?.detail === "string" ? err.body.detail : null
        throw new Error(detail ?? "There was a problem inviting this person.")
      }
    },
    [mutate]
  )

  const approveCollaborator = useCallback(
    async (collaboratorId: string) => {
      await mutate(`/${collaboratorId}/approve`, { method: "POST" })
    },
    [mutate]
  )

  return {
    data: query.data ?? null,
    loading: query.isLoading,
    error: query.isError ? "Could not load collaborators." : null,
    addCollaborator,
    removeCollaborator,
    inviteCollaborator,
    approveCollaborator,
  }
}
