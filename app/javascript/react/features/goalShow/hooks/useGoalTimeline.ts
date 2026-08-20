import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback } from "react"

import { useChannel } from "~/react/shared/hooks/useChannel"
import { useReconnectCatchUp } from "~/react/shared/hooks/useReconnectCatchUp"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

import { goalTimelineQueryKey, goalTimelineQueryOptions } from "../queries"
import type { TimelineEvent, TimelineResponse } from "../types"

const NO_EVENTS: TimelineEvent[] = []

export function useGoalTimeline(goalId: string) {
  const queryClient = useQueryClient()
  const query = useQuery(goalTimelineQueryOptions(goalId))

  // The broadcast carries the whole TimelineResponse, so the payload *is* the new
  // cache value — write it rather than invalidating, which would refetch what the
  // event already handed us.
  const handleMessage = useCallback(
    (_action: unknown, data: Record<string, unknown>) => {
      queryClient.setQueryData<TimelineResponse>(goalTimelineQueryKey(goalId), data as unknown as TimelineResponse)
    },
    [queryClient, goalId]
  )

  // goal_timeline carries content changes (comments/updates/status). View state (seen-by,
  // last-seen divider) is not here — it rides the shared collaborators query (useWorkspaceViewState).
  useChannel(
    { stream: ChannelStream.GOAL_TIMELINE, params: { goal_id: goalId } },
    ChannelEventResource.GOAL_TIMELINE,
    handleMessage
  )

  // Recover broadcasts missed while this route was unmounted and its subscription
  // unwired — on socket reconnect and on a warm remount. See useReconnectCatchUp.
  useReconnectCatchUp(goalTimelineQueryKey(goalId), "useGoalTimeline")

  return { events: query.data?.events ?? NO_EVENTS, loading: query.isLoading, error: query.isError }
}
