import { useCallback, useEffect, useState } from "react"

import { getChannelsClient } from "~/channels/client"
import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { type ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

export interface PendingResearchQuestion {
  id: string
  title: string
  research_created_at: string | null
}

export interface ResearchProgressResponse {
  pending_research_questions: PendingResearchQuestion[]
}

const EMPTY_STATE: ResearchProgressResponse = {
  pending_research_questions: [],
}

function isResearchProgressResponse(data: unknown): data is ResearchProgressResponse {
  return (
    typeof data === "object" &&
    data !== null &&
    Array.isArray((data as ResearchProgressResponse).pending_research_questions)
  )
}

async function fetchProgress(): Promise<ResearchProgressResponse | null> {
  try {
    const data = await apiFetch<ResearchProgressResponse>("/api/research_progress")
    return isResearchProgressResponse(data) ? data : null
  } catch {
    // Non-critical chrome — let the next broadcast or reconnect refetch recover.
    return null
  }
}

export function useResearchProgress(): ResearchProgressResponse {
  const { user } = useCurrentUser()
  const [state, setState] = useState<ResearchProgressResponse>(EMPTY_STATE)

  useEffect(() => {
    let cancelled = false
    fetchProgress().then(data => {
      if (!cancelled && data) setState(data)
    })
    return () => {
      cancelled = true
    }
  }, [])

  // Refetch on websocket reconnect to recover broadcasts missed while
  // disconnected — mirrors useInboxProgress / useMailboxEntries.
  useEffect(() => {
    const client = getChannelsClient()
    if (!client) return
    const onReconnect = () => {
      fetchProgress().then(data => {
        if (data) setState(data)
      })
    }
    client.on("reconnected", onReconnect)
    return () => client.off("reconnected", onReconnect)
  }, [])

  const onMessage = useCallback((_action: ChannelEventAction, data: Record<string, unknown>) => {
    if (isResearchProgressResponse(data)) setState(data)
  }, [])
  useChannel(
    user?.id ? { stream: ChannelStream.RESEARCH_PROGRESS, params: { user_id: user.id } } : null,
    ChannelEventResource.RESEARCH_PROGRESS,
    onMessage
  )

  return state
}
