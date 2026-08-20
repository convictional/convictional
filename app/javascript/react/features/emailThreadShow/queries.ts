import { type QueryClient, queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type {
  EmailMessageContentListResponse,
  EmailMessageContentResponse,
  EmailThreadShowResponse,
  TimelineItem,
} from "~/react/shared/types"

import { collapsedMessageIdsFor } from "./readState"

// The whole show envelope (thread, mailbox entry, timeline, comments, draft
// pointer) lives under one entry; channel handlers patch it via setQueryData and
// distinct threadIds keep distinct entries, so navigating A→B can't surface A's
// data. Per-message bodies are sub-keyed separately (immutable, fetched lazily).
export const emailThreadQueryKey = (threadId: string) => ["emailThread", threadId] as const
export const emailMessageContentQueryKey = (messageId: string) => ["emailMessageContent", messageId] as const

// Max ids per batch-content request; the load-time seed chunks the expanded set
// into requests of this size. Must not exceed MAX_BATCH_CONTENT_IDS on the server
// (email_threads.py), which rejects larger requests.
const CONTENT_BATCH_SIZE = 20

// Message ids that render expanded on load — the complement of `collapsed` over the
// timeline's messages. These are the bodies the load-time batch seeds.
function expandedMessageIdsFor(timeline: TimelineItem[], collapsed: Set<string>): string[] {
  const ids: string[] = []
  for (const item of timeline) {
    if (item.type === "message" && !collapsed.has(item.message.id)) ids.push(item.message.id)
  }
  return ids
}

// Batch-fetch the bodies of the messages that render expanded on load and seed each
// into its own per-message content cache, so the initial expanded set renders from
// cache with no per-message fetch. Runs inside the envelope queryFn (not a post-load
// effect), so the seeds are in place by the time the timeline first paints — which is
// what lets the "batch vs self-fetch" coordination (the old prefetchedContent Map /
// pendingContentIds Set) go away entirely. A failed batch is swallowed (apiFetch
// already reported it): each expanded message then self-fetches on a cache miss.
async function seedExpandedMessageContents(
  queryClient: QueryClient,
  threadId: string,
  response: EmailThreadShowResponse,
  signal: AbortSignal
): Promise<void> {
  const collapsed = collapsedMessageIdsFor(
    response.timeline,
    response.mailbox_entry.read_at,
    response.mailbox_entry.is_unread
  )
  // Skip bodies already cached: they're immutable, so a refetch (reconnect /
  // workspace-event invalidate / re-arm catch-up) re-runs this seed and must not
  // re-request the same bodies. Only genuinely-missing ones — a cold first load,
  // or a message that arrived while unmounted — hit the network.
  const missingIds = expandedMessageIdsFor(response.timeline, collapsed).filter(
    id => queryClient.getQueryData(emailMessageContentQueryKey(id)) === undefined
  )
  if (missingIds.length === 0) return
  try {
    // Chunk into CONTENT_BATCH_SIZE-id requests (the endpoint caps ids per request)
    // and fetch them in parallel — ceil(n / size) requests, far fewer than the
    // per-message N+1 this replaces.
    const chunks: string[][] = []
    for (let i = 0; i < missingIds.length; i += CONTENT_BATCH_SIZE) {
      chunks.push(missingIds.slice(i, i + CONTENT_BATCH_SIZE))
    }
    const responses = await Promise.all(
      chunks.map(chunkIds => {
        const params = new URLSearchParams()
        for (const id of chunkIds) params.append("ids", id)
        return apiFetch<EmailMessageContentListResponse>(
          `/api/email_threads/${threadId}/email_message_contents?${params}`,
          { signal }
        )
      })
    )
    for (const content of responses.flatMap(r => r.contents)) {
      queryClient.setQueryData<EmailMessageContentResponse>(emailMessageContentQueryKey(content.id), content)
    }
  } catch {
    // Swallow — apiFetch already reported to Sentry. Each expanded message falls
    // back to its own content fetch on a cache miss (see EmailMessage).
  }
}

// The show envelope. channelQueryDefaults (channel-first): the email_thread,
// email_thread_comments, and workspace_events channels are the freshness and
// recovery source, so it never background-refetches — a channel handler
// invalidates instead (reconnect / re-arm catch-up).
export function emailThreadQueryOptions(queryClient: QueryClient, threadId: string) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: emailThreadQueryKey(threadId),
    queryFn: async ({ signal }) => {
      const response = await apiFetch<EmailThreadShowResponse>(`/api/email_threads/${threadId}`, { signal })
      await seedExpandedMessageContents(queryClient, threadId, response, signal)
      return response
    },
  })
}

// A message body is immutable, so once fetched it never goes stale and never
// refetches; the load-time seed (above) or a lazy expand populates it.
export function emailMessageContentQueryOptions(messageId: string, contentUrl: string) {
  return queryOptions({
    queryKey: emailMessageContentQueryKey(messageId),
    queryFn: ({ signal }) => apiFetch<EmailMessageContentResponse>(contentUrl, { signal }),
    staleTime: Infinity,
  })
}
