import { hashKey, useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { getRouteApi, useNavigate } from "@tanstack/react-router"
import { useCallback, useEffect, useMemo, useRef } from "react"

import { getChannelsClient } from "~/channels/client"
import {
  appendGoalToPages,
  containsTopLevelGoal,
  type GoalsListData,
  type GoalsPageUpdate,
  goalsListQueryKey,
  goalsListQueryOptions,
  goalsListUrl,
  mergePageOne,
  removeGoalFromPages,
  setGoalsInPages,
  setSubgoalsInPages,
  updateGoalInPages,
} from "~/react/features/goalsIndex/queries"
import type { GoalListResponse, GoalsView } from "~/react/features/goalsIndex/types"
import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import type { Goal, GoalSummary } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"
import { ChannelEventResource, ChannelStream } from "~/types/channels"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/goals".
const routeApi = getRouteApi("/shell/goals")

// Stable identity for an absent filter, so the query key doesn't change on every
// render. Present filters come straight off the route's parsed search, which is
// stable per location.
const NO_IDS: string[] = []
const NO_NAMES: string[] = []

// How long to ignore goals_index broadcasts after a sort, covering the sort POST
// + broadcast round-trip (~1-2s) so the server's echo of the pre-sort order can't
// clobber the optimistic reorder and jump the scroll position. Query has no
// answer for this; the window stays.
const SORT_SUPPRESSION_MS = 3000

// Cursor pages can overlap at their boundary, so dedupe the flattened list by id
// (keeping the first occurrence) — infiniteQuery just concatenates pages.
function dedupeById(goals: Goal[]): Goal[] {
  const seen = new Set<string>()
  return goals.filter(goal => {
    if (seen.has(goal.id)) return false
    seen.add(goal.id)
    return true
  })
}

// The view selector and owner/group filters live in the route's typed search
// params, so the router owns history (deep links, refresh, back/forward) — this
// hook only reads them and navigates to change them. `view` stays the internal
// single-value abstraction the header and channels speak, derived from the three
// mutually-exclusive view params rather than stored alongside them.
export function useGoalsData() {
  const search = routeApi.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { user } = useCurrentUser()
  const organizationId = user?.organization_id

  const planningListName = search.planning_list_name
  const view: GoalsView = search.is_completed
    ? "completed"
    : search.is_closed
      ? "closed"
      : (planningListName ?? "active")
  const ownerIds = search.owner_ids ?? NO_IDS
  const groupIds = search.group_ids ?? NO_IDS

  const queryKey = useMemo(() => goalsListQueryKey(view, ownerIds, groupIds), [view, ownerIds, groupIds])
  const query = useInfiniteQuery(goalsListQueryOptions(view, ownerIds, groupIds))
  const { data, fetchNextPage, isFetchingNextPage, hasNextPage, isLoading, isError } = query

  const goals = useMemo(() => dedupeById(data?.pages.flatMap(page => page.goals) ?? []), [data])
  // planning_list_names rides in on the listing response rather than an endpoint
  // of its own, so it's derived from page 1 instead of a parallel useState.
  const planningListNames = data?.pages[0]?.planning_list_names ?? NO_NAMES

  const patch = useCallback(
    (fn: (old: GoalsListData | undefined) => GoalsListData | undefined) =>
      queryClient.setQueryData<GoalsListData>(queryKey, fn),
    [queryClient, queryKey]
  )

  // Goals created in this tab that the server's page-1 broadcast hasn't paged in
  // yet: a fresh goal sorts last, and its title is generated asynchronously. They
  // are the only rows the page-1 merge preserves, and the only rows it re-fetches
  // individually. Reset when the cache key changes, since a locally created goal
  // belongs to the view it was created in.
  const localOnlyIdsRef = useRef(new Set<string>())
  const keyHash = hashKey(queryKey)
  useEffect(() => {
    localOnlyIdsRef.current = new Set()
  }, [keyHash])

  // The per-goal refetches below outlive an unmount (they carry no signal, and
  // their cache write is still correct after navigation), but their failure flash
  // is not: it would land on whatever route the reader is now looking at. Re-armed
  // in the effect body so StrictMode's mount→unmount→remount leaves it true.
  const mountedRef = useRef(true)
  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  // Suppress channel updates briefly after sorting to prevent the paginated broadcast
  // from clobbering the optimistic reorder and causing scroll jumps
  const suppressChannelUntilRef = useRef(0)

  const isFiltered = ownerIds.length > 0 || groupIds.length > 0
  const isPlanningList = !!planningListName

  const loadMore = useCallback(() => {
    if (isFetchingNextPage || !hasNextPage) return
    void fetchNextPage()
  }, [isFetchingNextPage, hasNextPage, fetchNextPage])

  // The view/filter changers navigate the route; the router writes the search
  // params (pushing a history entry) and this hook re-reads them, which selects a
  // different query key. Switching view drops the owner/group filters, matching
  // the old hand-rolled pushState.
  const changeView = useCallback(
    (newView: GoalsView) =>
      void navigate({
        to: "/goals",
        search:
          newView === "completed"
            ? { is_completed: true }
            : newView === "closed"
              ? { is_closed: true }
              : newView === "active"
                ? {}
                : { planning_list_name: newView },
      }),
    [navigate]
  )

  const toggleOwnerFilter = useCallback(
    (userId: string) =>
      void navigate({
        to: "/goals",
        search: prev => {
          const current = prev.owner_ids ?? []
          const next = current.includes(userId) ? current.filter(id => id !== userId) : [...current, userId]
          return { ...prev, owner_ids: next.length ? next : undefined }
        },
      }),
    [navigate]
  )

  const toggleGroupFilter = useCallback(
    (groupId: string) =>
      void navigate({
        to: "/goals",
        search: prev => {
          const current = prev.group_ids ?? []
          const next = current.includes(groupId) ? current.filter(id => id !== groupId) : [...current, groupId]
          return { ...prev, group_ids: next.length ? next : undefined }
        },
      }),
    [navigate]
  )

  const clearFilters = useCallback(
    () => void navigate({ to: "/goals", search: prev => ({ ...prev, owner_ids: undefined, group_ids: undefined }) }),
    [navigate]
  )

  const updateGoalInList = useCallback((updated: Goal) => patch(old => updateGoalInPages(old, updated)), [patch])

  const removeGoal = useCallback((goalId: string) => patch(old => removeGoalFromPages(old, goalId)), [patch])

  // Dedup rather than trust the create response alone: the goals_index broadcast
  // can arrive before the POST resolves, and both would otherwise insert a row.
  const addGoalToList = useCallback(
    (goal: Goal) => {
      if (containsTopLevelGoal(queryClient.getQueryData<GoalsListData>(queryKey), goal.id)) return
      localOnlyIdsRef.current.add(goal.id)
      patch(old => appendGoalToPages(old, goal))
    },
    [patch, queryClient, queryKey]
  )

  // No optimistic append for new subgoals: the GOALS_INDEX broadcast is the sole
  // producer, which avoids the duplicate-row race two producers would create.

  // Apply a fresh page-1 listing — from the channel, or from the out-of-band
  // refetch below. Anything in the payload is now server-owned, so it stops being
  // local-only; whatever is still local-only is re-fetched individually to pick up
  // server-side changes (e.g. a generated title). Tracking outlives the merge on
  // purpose: a goal appended past page 1 never appears in a page-1 payload, and
  // dropping it would strand it without its generated title.
  const applyPageOne = useCallback(
    (update: GoalsPageUpdate) => {
      const localOnly = localOnlyIdsRef.current
      for (const goal of update.goals) localOnly.delete(goal.id)
      patch(old => mergePageOne(old, update, localOnly))

      for (const id of localOnly) {
        apiFetch<Goal>(`/api/goals/${id}?expand=subgoals`)
          .then(updated => patch(old => updateGoalInPages(old, updated)))
          .catch(() => {
            if (mountedRef.current) showFlash("Couldn't refresh a goal. Try reloading.")
          })
      }
    },
    [patch]
  )

  // Merge-aware page-1 refetch for the recovery paths. Never invalidateQueries:
  // invalidate has no merge hook, so its refetch would drop pages 2+ and any
  // local-only goal. The AbortController makes each call supersede the last, and
  // stops a response that lands after unmount from writing into the shared cache.
  const abortRef = useRef<AbortController | null>(null)
  const refreshPageOne = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    const page = await apiFetch<GoalListResponse>(goalsListUrl(view, ownerIds, groupIds, null), {
      signal: controller.signal,
    })
    applyPageOne(page)
  }, [view, ownerIds, groupIds, applyPageOne])

  useEffect(() => () => abortRef.current?.abort(), [])

  // Recover broadcasts missed while the socket was down. channelQueryDefaults
  // disables refetchOnReconnect, and this rides the channels client's
  // "reconnected" event rather than the browser online event, which fires on
  // flaky transitions the socket hasn't acted on. With nothing cached (a cold or
  // errored query, which retryOnMount: false won't retry) there is nothing to
  // merge into, so invalidate instead — that is the only path back for an errored
  // channel-backed query.
  const catchUp = useCallback(() => {
    if (queryClient.getQueryData(queryKey) === undefined) {
      void queryClient.invalidateQueries({ queryKey })
      return
    }
    void refreshPageOne().catch(() => {})
  }, [queryClient, queryKey, refreshPageOne])

  useEffect(() => {
    const client = getChannelsClient()
    if (!client) return
    client.on("reconnected", catchUp)
    return () => client.off("reconnected", catchUp)
  }, [catchUp])

  // Subscription re-arm catch-up. The goals_index subscription is per-mount, but
  // navigation tears this route down while the QueryClient singleton (and the
  // socket) survive, so broadcasts arriving while unmounted are missed and
  // staleTime: Infinity means the remount won't refetch. A warm cache at mount
  // means a prior mount fetched it; a cold first mount has no cached data yet
  // (the query is still fetching), so it's skipped.
  //
  // Keyed on cached data rather than a fire-once ref: the abort-on-unmount above
  // cancels this refetch during StrictMode's mount→unmount→remount, and a ref
  // would have already been tripped, so the catch-up would be dropped entirely.
  // Re-running it on the second pass costs nothing — the abort collapses the two
  // into one request — and the cold first mount is skipped on both passes.
  useEffect(() => {
    if (queryClient.getQueryData(queryKey) !== undefined) void refreshPageOne().catch(() => {})
  }, [queryClient, queryKey, refreshPageOne])

  // The optimistic reorder + rollback is what useMutation is for: onMutate
  // snapshots and writes, onError restores. The suppression window above is not —
  // it guards against the server's own echo, which Query has no notion of.
  const { mutate: sortGoals } = useMutation({
    mutationFn: (reordered: Goal[]) =>
      apiFetch("/api/goals/sort", {
        method: "POST",
        body: JSON.stringify({ ids: reordered.map(g => g.id), view: isPlanningList ? view : "active" }),
      }),
    onMutate: (reordered: Goal[]) => {
      suppressChannelUntilRef.current = Date.now() + SORT_SUPPRESSION_MS
      const previous = queryClient.getQueryData<GoalsListData>(queryKey)
      patch(old => setGoalsInPages(old, reordered))
      return { previous }
    },
    onError: (_error, _reordered, context) => {
      if (context?.previous) queryClient.setQueryData(queryKey, context.previous)
      showFlash("Couldn't save goal order.")
    },
  })

  const { mutate: sortSubgoals } = useMutation({
    mutationFn: ({ parentId, subgoals }: { parentId: string; subgoals: GoalSummary[] }) =>
      apiFetch(`/api/goals/${parentId}/subgoals/sort`, {
        method: "POST",
        body: JSON.stringify({ ids: subgoals.map(s => s.id) }),
      }),
    onMutate: ({ parentId, subgoals }) => {
      suppressChannelUntilRef.current = Date.now() + SORT_SUPPRESSION_MS
      const previous = queryClient.getQueryData<GoalsListData>(queryKey)
      patch(old => setSubgoalsInPages(old, parentId, subgoals))
      return { previous }
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) queryClient.setQueryData(queryKey, context.previous)
      showFlash("Couldn't save goal order.")
    },
  })

  const reorderGoals = useCallback((reordered: Goal[]) => sortGoals(reordered), [sortGoals])

  const reorderSubgoals = useCallback(
    (parentId: string, subgoals: GoalSummary[]) => sortSubgoals({ parentId, subgoals }),
    [sortSubgoals]
  )

  const isSortEnabled = useMemo(() => !isFiltered && view !== "completed" && view !== "closed", [isFiltered, view])

  useChannel(
    organizationId ? { stream: ChannelStream.GOALS_INDEX, params: { organization_id: organizationId, view } } : null,
    ChannelEventResource.GOALS_INDEX,
    (_action, data) => {
      if (Date.now() < suppressChannelUntilRef.current) return

      const incoming = data.goals as Goal[] | undefined
      if (!incoming) return

      applyPageOne({
        goals: incoming,
        next_cursor: typeof data.next_cursor === "string" ? data.next_cursor : null,
        has_more: !!data.has_more,
      })
    }
  )

  return {
    goals,
    loading: isLoading,
    loadingMore: isFetchingNextPage,
    error: isError,
    hasMore: hasNextPage,
    loadMore,
    view,
    changeView,
    ownerIds,
    groupIds,
    toggleOwnerFilter,
    toggleGroupFilter,
    clearFilters,
    isFiltered,
    isPlanningList,
    planningListNames,
    updateGoalInList,
    removeGoal,
    addGoalToList,
    reorderGoals,
    reorderSubgoals,
    isSortEnabled,
  }
}
