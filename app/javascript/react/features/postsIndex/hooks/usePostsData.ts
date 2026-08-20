import { keepPreviousData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query"
import { getRouteApi, useNavigate } from "@tanstack/react-router"
import { useCallback, useMemo } from "react"

import {
  type PostsFeedData,
  pinnedPostsQueryOptions,
  postsDraftsQueryOptions,
  postsFeedQueryKey,
  postsFeedQueryOptions,
} from "~/react/features/postsIndex/queries"
import type { PostListDecision, PostsView } from "~/react/features/postsIndex/types"
import type { Post } from "~/react/shared/types"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/posts".
const routeApi = getRouteApi("/shell/posts")

const EMPTY_POSTS: Post[] = []

function decisionsToMap(decisions: PostListDecision[]): Map<string, PostListDecision> {
  return new Map(decisions.map(decision => [decision.post_id, decision]))
}

// Cursor pages can overlap at their boundary, so dedupe the flattened list by id
// (keeping the first occurrence) — infiniteQuery just concatenates pages.
function dedupeById<T extends { id: string }>(items: T[]): T[] {
  const seen = new Set<string>()
  return items.filter(item => {
    if (seen.has(item.id)) return false
    seen.add(item.id)
    return true
  })
}

// The browse view/filters live in the route's typed search params, so the router
// owns history (deep links, refresh, back/forward) — this hook only reads them
// and navigates to change them. `q` is owned by the search overlay; the changers
// preserve it so toggling a filter doesn't drop an active query.
export function usePostsData() {
  const search = routeApi.useSearch()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const view: PostsView = search.status === "drafts" ? "drafts" : "posts"
  const groupId = search.group_id ?? null
  const decided = search.decided ?? false

  // Feed and drafts are distinct endpoints with distinct shapes, so each rides
  // its own infinite query, gated to the active view. The shared, persistent
  // QueryClient keeps both caches warm across navigation and view switches:
  // returning to a view paints its cached list, then refetches quietly in the
  // background. keepPreviousData holds the old cards on screen through a filter
  // change instead of blanking to a skeleton.
  const feedQuery = useInfiniteQuery({
    ...postsFeedQueryOptions(groupId, decided),
    enabled: view === "posts",
    placeholderData: keepPreviousData,
  })
  const draftsQuery = useInfiniteQuery({
    ...postsDraftsQueryOptions(),
    enabled: view === "drafts",
    placeholderData: keepPreviousData,
  })
  // Runs in both views — the featured rail in the feed, and the drafts-toggle
  // badge (draft_count) even on a deep link straight into the drafts view.
  const pinnedQuery = useQuery({
    ...pinnedPostsQueryOptions(groupId, decided),
    placeholderData: keepPreviousData,
  })

  const activeQuery = view === "drafts" ? draftsQuery : feedQuery
  const { isFetchingNextPage, hasNextPage, fetchNextPage } = activeQuery

  const posts = useMemo(() => dedupeById(feedQuery.data?.pages.flatMap(page => page.posts) ?? []), [feedQuery.data])
  const drafts = useMemo(
    () => dedupeById(draftsQuery.data?.pages.flatMap(page => page.drafts) ?? []),
    [draftsQuery.data]
  )
  const pinnedPosts = pinnedQuery.data?.posts ?? EMPTY_POSTS

  // Decision badges, sourced from PostListResponse.decisions rather than Post.
  // Feed and pinned are disjoint collections (?pinned=false / true), so they keep
  // separate maps and merge for lookup.
  const feedDecisions = useMemo(
    () => decisionsToMap(feedQuery.data?.pages.flatMap(page => page.decisions) ?? []),
    [feedQuery.data]
  )
  const pinnedDecisions = useMemo(() => decisionsToMap(pinnedQuery.data?.decisions ?? []), [pinnedQuery.data])
  const decisionsByPostId = useMemo(
    () => new Map([...pinnedDecisions, ...feedDecisions]),
    [pinnedDecisions, feedDecisions]
  )

  const draftCount = pinnedQuery.data?.draft_count ?? 0

  const loadMore = useCallback(() => {
    if (isFetchingNextPage || !hasNextPage) return
    void fetchNextPage()
  }, [isFetchingNextPage, hasNextPage, fetchNextPage])

  // View/filter changers navigate the route; the router updates the search params
  // (pushing a history entry) and this hook re-reads them, which reselects the
  // active query and its cache. `q` is preserved so an active search survives a
  // filter switch; the drafts view ignores group/decided, so they're dropped there.
  const showPosts = useCallback(() => void navigate({ to: "/posts", search: prev => ({ q: prev.q }) }), [navigate])
  const showDrafts = useCallback(
    () => void navigate({ to: "/posts", search: prev => ({ q: prev.q, status: "drafts" }) }),
    [navigate]
  )
  const changeGroup = useCallback(
    (newGroupId: string | null) =>
      void navigate({ to: "/posts", search: prev => ({ q: prev.q, group_id: newGroupId ?? undefined }) }),
    [navigate]
  )
  const toggleDecided = useCallback(
    () =>
      void navigate({
        to: "/posts",
        search: prev => ({ q: prev.q, group_id: prev.group_id, decided: prev.decided ? undefined : true }),
      }),
    [navigate]
  )

  // Optimistic create: prepend the new card into the feed cache only when it
  // belongs in the list the user is looking at — the drafts view doesn't show
  // published posts, a Decisions filter excludes a fresh (undecided) post, and a
  // group filter excludes a post posted elsewhere. In those cases the card simply
  // isn't shown until a refetch.
  const prependPost = useCallback(
    (post: Post) => {
      if (view !== "posts" || decided) return
      if (groupId && post.group?.id !== groupId) return
      queryClient.setQueryData<PostsFeedData>(postsFeedQueryKey(groupId, decided), old => {
        if (!old) return old
        const [first, ...rest] = old.pages
        if (!first || first.posts.some(p => p.id === post.id)) return old
        return { ...old, pages: [{ ...first, posts: [post, ...first.posts] }, ...rest] }
      })
    },
    [view, groupId, decided, queryClient]
  )

  return {
    view,
    groupId,
    decided,
    posts,
    drafts,
    pinnedPosts,
    decisionsByPostId,
    draftCount,
    loading: activeQuery.isLoading,
    loadingMore: isFetchingNextPage,
    error: activeQuery.isError,
    hasMore: hasNextPage,
    loadMore,
    showPosts,
    showDrafts,
    changeGroup,
    toggleDecided,
    prependPost,
  }
}
