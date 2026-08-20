import { queryOptions, useQuery, useQueryClient } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useReconnectInvalidate } from "~/react/shared/hooks/useReconnectInvalidate"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { WorkspaceCollaboratorsData } from "~/react/shared/types"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

export const workspaceCollaboratorsQueryKey = (workspaceId: string) => ["workspaceCollaborators", workspaceId] as const

// Channel-backed, per-workspace query for the collaborators payload — which carries each
// collaborator's view_state (viewed / last_viewed_at / last_viewed_event_id). It is the single
// cached source of collaborator roster + view state, read by the collaborators panel, the goal
// timeline's "Seen by" avatars, and mention scoping (useWorkspaceCollaboratorIds). The
// workspace_collaborators channel keeps it live (see below), so it takes the channel-first
// posture (never background-refetch). Lives in shared/ so the shared-layer mention hook can reuse
// it without violating the layering boundary. Mirrors useDecisions.
export function workspaceCollaboratorsQueryOptions(workspaceId: string) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: workspaceCollaboratorsQueryKey(workspaceId),
    // Islands whose show response resolves async mount this before the workspace id is known.
    enabled: !!workspaceId,
    queryFn: () => apiFetch<WorkspaceCollaboratorsData>(`/api/workspaces/${workspaceId}/collaborators`),
  })
}

// Runs the query and wires the workspace_collaborators channel to keep it fresh:
// - VIEW_STATE_CHANGED (a collaborator recorded a visit) and membership CREATED/DELETED
//   invalidate → refetch the full payload (new view_state / roster).
// - UPDATED carries presence (present_user_ids); patch it in place rather than refetching,
//   since presence churn is frequent and doesn't touch the roster or view_state.
export function useWorkspaceCollaboratorsQuery(workspaceId: string) {
  const queryClient = useQueryClient()
  const query = useQuery(workspaceCollaboratorsQueryOptions(workspaceId))

  const key = workspaceCollaboratorsQueryKey(workspaceId)
  useReconnectInvalidate(key, "workspaceCollaborators")

  useChannel(
    workspaceId ? { stream: ChannelStream.WORKSPACE_COLLABORATORS, params: { workspace_id: workspaceId } } : null,
    ChannelEventResource.WORKSPACE_COLLABORATORS,
    (action, payload) => {
      if (action === ChannelEventAction.UPDATED) {
        const ids = payload.present_user_ids
        if (Array.isArray(ids)) {
          queryClient.setQueryData<WorkspaceCollaboratorsData>(key, prev =>
            prev ? { ...prev, present_user_ids: ids as string[] } : prev
          )
        }
        return
      }
      if (
        action === ChannelEventAction.VIEW_STATE_CHANGED ||
        action === ChannelEventAction.CREATED ||
        action === ChannelEventAction.DELETED
      ) {
        void queryClient.invalidateQueries({ queryKey: key })
      }
    }
  )

  return query
}
