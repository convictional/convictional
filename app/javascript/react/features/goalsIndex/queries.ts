import { type InfiniteData, infiniteQueryOptions } from "@tanstack/react-query"

import type { GoalListResponse, GoalsView } from "~/react/features/goalsIndex/types"
import { apiFetch } from "~/react/shared/apiFetch"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import type { Goal, GoalSummary } from "~/react/shared/types"

export type GoalsListData = InfiniteData<GoalListResponse, string | null>

// The filter tuple is the cache identity, so a view or filter change is a new key
// rather than a manual refetch — and switching back paints the warm cache.
export const goalsListQueryKey = (view: GoalsView, ownerIds: string[], groupIds: string[]) =>
  ["goals", "list", view, ownerIds, groupIds] as const

// The API request URL, distinct from the address bar: the browser URL is the
// route's typed search params (the router owns it), while this adds the
// expansions and cursor the listing endpoint needs.
export function goalsListUrl(view: GoalsView, ownerIds: string[], groupIds: string[], cursor?: string | null): string {
  const params = new URLSearchParams()
  // The index tree renders subgoals inline.
  params.set("expand", "subgoals")

  if (view === "completed") {
    params.set("is_completed", "true")
  } else if (view === "closed") {
    params.set("is_closed", "true")
  } else if (view !== "active") {
    params.set("planning_list_name", view)
  }

  for (const id of ownerIds) params.append("owner_ids", id)
  for (const id of groupIds) params.append("group_ids", id)
  if (cursor) params.set("cursor", cursor)

  return `/api/goals?${params.toString()}`
}

// Channel-backed: the goals_index broadcast re-runs the page-1 listing and hands
// back the rows, so this query never background-refetches — the channel is the
// freshness source and the merge below is the write.
export function goalsListQueryOptions(view: GoalsView, ownerIds: string[], groupIds: string[]) {
  return infiniteQueryOptions({
    ...channelQueryDefaults,
    queryKey: goalsListQueryKey(view, ownerIds, groupIds),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      apiFetch<GoalListResponse>(goalsListUrl(view, ownerIds, groupIds, pageParam), { signal }),
    getNextPageParam: lastPage => (lastPage.has_more ? lastPage.next_cursor : undefined),
  })
}

// --- Pure cache-patch helpers ---
//
// The cache is a list of server pages. Every helper below rewrites goal arrays
// page-by-page and returns the input untouched when there is nothing cached, so
// each is a plain value-in/value-out function the tests drive directly.

function withGoals(data: GoalsListData | undefined, fn: (goals: Goal[]) => Goal[]): GoalsListData | undefined {
  if (!data) return data
  return { ...data, pages: data.pages.map(page => ({ ...page, goals: fn(page.goals) })) }
}

function goalToSummary(goal: Goal): GoalSummary {
  return {
    id: goal.id,
    workspace_id: goal.workspace_id,
    title: goal.title,
    description: goal.description,
    status: goal.status,
    progress: goal.progress,
    target_date: goal.target_date,
    is_completed: goal.is_completed,
    is_closed: goal.is_closed,
    is_draft: goal.is_draft,
    owner: goal.owner,
    group: goal.group,
    open_comment_count: goal.open_comment_count,
  }
}

export function containsTopLevelGoal(data: GoalsListData | undefined, goalId: string): boolean {
  return (data?.pages ?? []).some(page => page.goals.some(g => g.id === goalId))
}

export function updateGoalInPages(data: GoalsListData | undefined, updated: Goal): GoalsListData | undefined {
  return withGoals(data, goals =>
    goals.map(g => {
      if (g.id === updated.id) return updated
      // Check subgoals of parent goals
      if ((g.subgoals ?? []).some(s => s.id === updated.id)) {
        return {
          ...g,
          subgoals: (g.subgoals ?? []).map(s => (s.id === updated.id ? goalToSummary(updated) : s)),
        }
      }
      return g
    })
  )
}

export function removeGoalFromPages(data: GoalsListData | undefined, goalId: string): GoalsListData | undefined {
  if (!data) return data
  const isTopLevel = containsTopLevelGoal(data, goalId)
  return withGoals(data, goals =>
    isTopLevel
      ? goals.filter(g => g.id !== goalId)
      : // Otherwise remove as a subgoal from its parent
        goals.map(g =>
          (g.subgoals ?? []).some(s => s.id === goalId)
            ? { ...g, subgoals: (g.subgoals ?? []).filter(s => s.id !== goalId) }
            : g
        )
  )
}

// A new goal gets the highest position value, so it belongs after everything
// already loaded — append to the last page rather than page 1, or it would land
// mid-list for a user who has scrolled.
export function appendGoalToPages(data: GoalsListData | undefined, goal: Goal): GoalsListData | undefined {
  if (!data || data.pages.length === 0) return data
  const lastIndex = data.pages.length - 1
  return {
    ...data,
    pages: data.pages.map((page, i) => (i === lastIndex ? { ...page, goals: [...page.goals, goal] } : page)),
  }
}

// Drag-to-sort reorders the flattened list, so write it back preserving each
// page's length: page boundaries are cursor positions, not semantic groups.
export function setGoalsInPages(data: GoalsListData | undefined, goals: Goal[]): GoalsListData | undefined {
  if (!data) return data
  let offset = 0
  return {
    ...data,
    pages: data.pages.map(page => {
      const slice = goals.slice(offset, offset + page.goals.length)
      offset += page.goals.length
      return { ...page, goals: slice }
    }),
  }
}

export function setSubgoalsInPages(
  data: GoalsListData | undefined,
  parentId: string,
  subgoals: GoalSummary[]
): GoalsListData | undefined {
  return withGoals(data, goals => goals.map(g => (g.id === parentId ? { ...g, subgoals } : g)))
}

function laterPageGoalIds(data: GoalsListData | undefined): Set<string> {
  return new Set((data?.pages ?? []).slice(1).flatMap(page => page.goals.map(g => g.id)))
}

// The page-1 shape both the goals_index broadcast and an out-of-band page-1
// refetch deliver. The broadcast omits planning_list_names (it is not part of the
// channel payload), so the merge keeps the cached value in that case.
export interface GoalsPageUpdate {
  goals: Goal[]
  next_cursor: string | null
  has_more: boolean
  planning_list_names?: string[] | null
}

// Merge-aware page-1 write. The goals_index broadcast re-runs the whole page-1
// listing, so its payload *is* the new page 1 — patch it in rather than
// invalidating (which would refetch data the event already handed us) or
// replacing the whole cache (which would drop the pages a scrolled reader has
// loaded and visually rewind the list). Pages 2+ stay frozen.
//
// `localOnlyIds` are goals created in this tab that the server hasn't paged into
// page 1 yet (a fresh goal sorts last, and its title is generated
// asynchronously). They are preserved after the incoming rows instead of being
// dropped. Anything else missing from the payload is genuinely gone from this
// view — a goal closed in another tab, say — and is dropped. A goal the server
// has since paged onto a later page is dropped too: the authoritative row is
// already loaded, so keeping the page-1 copy would hold the same goal twice.
export function mergePageOne(
  data: GoalsListData | undefined,
  update: GoalsPageUpdate,
  localOnlyIds: ReadonlySet<string>
): GoalsListData | undefined {
  if (!data || data.pages.length === 0) return data
  const incomingIds = new Set(update.goals.map(g => g.id))
  const [first, ...rest] = data.pages
  const laterIds = laterPageGoalIds(data)
  const keptLocal = first.goals.filter(g => localOnlyIds.has(g.id) && !incomingIds.has(g.id) && !laterIds.has(g.id))
  return {
    ...data,
    pages: [
      {
        ...first,
        goals: [...update.goals, ...keptLocal],
        next_cursor: update.next_cursor,
        has_more: update.has_more,
        planning_list_names: update.planning_list_names ?? first.planning_list_names,
      },
      ...rest,
    ],
  }
}
