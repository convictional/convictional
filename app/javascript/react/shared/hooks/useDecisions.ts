import { queryOptions, useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useRef } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { Decision, DecisionListResponse } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

export interface UseDecisionsOptions {
  // The DECISIONS_CHANGED signal rides the workspace_events topic; there is no
  // per-user sender-skip, so the acting tab refetches too — harmless (the list
  // is re-derived from one GET).
  workspaceId: string
}

export interface UseDecisionsResult {
  decisions: Decision[]
  // comment_gid -> decision, for the per-comment inline marker.
  decisionsByGid: Map<string, Decision>
  // Single-click toggle: marks an undecided comment, clears a decided one. Keyed
  // by the comment's global_id — the hook abstracts over the uniform
  // workspace-scoped API contract and carries no thread-shape knowledge, so the
  // post and chat islands (and any future comment-bearing island) share it unchanged.
  toggleDecision: (commentGid: string) => Promise<void>
}

const decisionsQueryKey = (workspaceId: string) => ["decisions", workspaceId] as const

// The cache holds the flat Decision[] the API returns; the select derives both
// the list and the comment_gid index subscribers read. Module-level (stable
// identity) so TanStack reuses the result until the cached list changes — the
// same memoization the old useMemo gave, recomputed only on a real change.
function selectDecisions(decisions: Decision[]): { decisions: Decision[]; decisionsByGid: Map<string, Decision> } {
  const decisionsByGid = new Map<string, Decision>()
  for (const decision of decisions) decisionsByGid.set(decision.comment_gid, decision)
  return { decisions, decisionsByGid }
}

function decisionsQueryOptions(workspaceId: string) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: decisionsQueryKey(workspaceId),
    // Islands whose show response loads async (e.g. chat) mount this hook before
    // the workspace id is known; gate the query until it arrives so we never fire
    // GET /api/workspaces//decisions.
    enabled: !!workspaceId,
    queryFn: async () => {
      const { decisions } = await apiFetch<DecisionListResponse>(`/api/workspaces/${workspaceId}/decisions`)
      return decisions
    },
    select: selectDecisions,
  })
}

const EMPTY_DECISIONS: Decision[] = []
const EMPTY_BY_GID = new Map<string, Decision>()

export function useDecisions({ workspaceId }: UseDecisionsOptions): UseDecisionsResult {
  const queryClient = useQueryClient()
  const query = useQuery(decisionsQueryOptions(workspaceId))

  const toggleMutation = useMutation({
    mutationFn: async (commentGid: string) => {
      // Branch on the canonical cached list (read at call time, not closed over)
      // so a toggle always reflects the latest server state.
      const list = queryClient.getQueryData<Decision[]>(decisionsQueryKey(workspaceId)) ?? []
      const existing = list.find(d => d.comment_gid === commentGid)
      if (existing) {
        await apiFetch(`/api/workspaces/${workspaceId}/decisions/${existing.id}`, { method: "DELETE" })
      } else {
        await apiFetch(`/api/workspaces/${workspaceId}/decisions`, {
          method: "POST",
          body: JSON.stringify({ comment_gid: commentGid }),
        })
      }
    },
    // Pessimistic: re-derive from the server (the canonical list) rather than
    // splicing. The acting tab refetches here for prompt feedback; the channel
    // signal drives the same refetch for other tabs. Return the invalidate promise
    // (don't void it) so mutateAsync — and the inFlight guard below — stays held
    // until the refetched list lands. Releasing the guard after the HTTP call but
    // before the refetch would let a second tap in that window read the stale
    // cache and re-POST, the 409 the guard exists to prevent.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: decisionsQueryKey(workspaceId) }),
    onError: () => showFlash("Couldn't update the decision."),
  })

  // Comments with a toggle in flight. The marker is a single-click affordance, so
  // a fast double-tap would otherwise fire a second request the server is bound
  // to reject (409 on re-POST, 404 on re-DELETE), surfacing a misleading error
  // flash on an otherwise-successful decision. Guarding per gid (not a single
  // boolean) keeps toggles on different comments independent. useMutation does not
  // dedup by key, so this guard still has a job after the Query migration.
  const inFlight = useRef(new Set<string>())
  const { mutateAsync: toggleMutate } = toggleMutation

  // toggleDecision keeps a stable identity (mutateAsync is referentially stable):
  // this hook's result flows down as onToggleDecision to every message bubble, and
  // a toggleDecision that churned on each decision change would defeat their
  // React.memo and re-render the whole list whenever any decision changed.
  const toggleDecision = useCallback(
    async (commentGid: string) => {
      if (inFlight.current.has(commentGid)) return
      inFlight.current.add(commentGid)
      try {
        await toggleMutate(commentGid)
      } catch {
        // onError already flashed; swallow so callers don't see a rejected promise.
      } finally {
        inFlight.current.delete(commentGid)
      }
    },
    [toggleMutate]
  )

  // A payload-less DECISIONS_CHANGED event invalidates (no granular patch to
  // apply); the mounted query refetches the canonical list.
  useChannel(
    workspaceId ? { stream: ChannelStream.WORKSPACE_EVENTS, params: { workspace_id: workspaceId } } : null,
    ChannelEventResource.DECISION,
    action => {
      if (action === ChannelEventAction.DECISIONS_CHANGED) {
        void queryClient.invalidateQueries({ queryKey: decisionsQueryKey(workspaceId) })
      }
    }
  )

  // Recover broadcasts missed while this hook was unmounted and its subscription
  // unwired — on socket reconnect and on a warm remount. See useReconnectCatchUp.
  useReconnectCatchUp(decisionsQueryKey(workspaceId), "useDecisions")

  return {
    decisions: query.data?.decisions ?? EMPTY_DECISIONS,
    decisionsByGid: query.data?.decisionsByGid ?? EMPTY_BY_GID,
    toggleDecision,
  }
}
