import { queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { Goal, MailboxEntryResponse } from "~/react/shared/types"

import type { GoalShowResponse, TimelineResponse } from "./types"

// The cached show response, with `mailbox_entry` split out as a sibling of the
// goal rather than left on it. The two have different writers — a picker PATCH
// returns a bare goal, the mailbox action bar returns only entry state — so
// keeping them apart means neither write can blank the other.
export interface GoalShowData {
  goal: Goal
  mailboxEntry: MailboxEntryResponse | null
}

// mailboxEntryId belongs in the key, not just the URL: the same goal reached from
// the inbox carries an entry and reached from the index does not, so they are two
// different cache values. Both share the ["goal", goalId] prefix, so an
// invalidation by prefix refreshes whichever is live.
export const goalQueryKey = (goalId: string, mailboxEntryId?: string) =>
  ["goal", goalId, mailboxEntryId ?? null] as const

export const goalTimelineQueryKey = (goalId: string) => ["goalTimeline", goalId] as const

// The show fetch forwards mailbox_entry_id from the route's search params so the
// API resolves the (owner-scoped) entry and the header can render its mailbox
// variant. Mirrors postShowUrl.
function goalShowUrl(goalId: string, mailboxEntryId?: string): string {
  const base = `/api/goals/${goalId}?expand=subgoals&expand=parent`
  return mailboxEntryId ? `${base}&mailbox_entry_id=${encodeURIComponent(mailboxEntryId)}` : base
}

// Standard Query defaults, deliberately NOT channelQueryDefaults: no channel
// pushes the goal detail. goal_timeline carries timeline content only, so a
// channel-first query here (staleTime: Infinity, refetchOnMount: false) would
// serve indefinitely stale data with nothing to invalidate it. Same reasoning as
// shared/stores/documents.ts — refetch on mount/focus, plus explicit
// invalidation from the actions that change the goal out of band.
export function goalQueryOptions(goalId: string, mailboxEntryId?: string) {
  return queryOptions({
    queryKey: goalQueryKey(goalId, mailboxEntryId),
    queryFn: async ({ signal }): Promise<GoalShowData> => {
      const { mailbox_entry: mailboxEntry, ...goal } = await apiFetch<GoalShowResponse>(
        goalShowUrl(goalId, mailboxEntryId),
        { signal }
      )
      return { goal, mailboxEntry }
    },
  })
}

// Channel-backed: the goal_timeline broadcast carries the entire TimelineResponse,
// so its handler writes the payload straight into this cache — coarse in trigger,
// complete in payload, so it patches rather than invalidates.
export function goalTimelineQueryOptions(goalId: string) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: goalTimelineQueryKey(goalId),
    queryFn: ({ signal }) => apiFetch<TimelineResponse>(`/api/goals/${goalId}/timeline`, { signal }),
  })
}
