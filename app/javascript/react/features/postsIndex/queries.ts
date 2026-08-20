import { type InfiniteData, infiniteQueryOptions, queryOptions } from "@tanstack/react-query"

import type { PostDraftListResponse, PostListResponse } from "~/react/features/postsIndex/types"
import { apiFetch } from "~/react/shared/apiFetch"

export type PostsFeedData = InfiniteData<PostListResponse, string | null>

// Filters are part of the key so each view/group/decided combination caches
// separately — switching back to a combination paints its warm cache. Drafts
// ignore group/decided (their own endpoint), so their key carries neither.
export const postsFeedQueryKey = (groupId: string | null, decided: boolean) =>
  ["posts", "feed", groupId, decided] as const
export const postsDraftsQueryKey = () => ["posts", "drafts"] as const
export const pinnedPostsQueryKey = (groupId: string | null, decided: boolean) =>
  ["posts", "pinned", groupId, decided] as const

function buildPostsApiUrl(groupId: string | null, decided: boolean, pinned: boolean, cursor: string | null): string {
  const params = new URLSearchParams()
  if (groupId) params.set("group_id", groupId)
  if (decided) params.set("decided", "true")
  params.set("pinned", pinned ? "true" : "false")
  if (cursor) params.set("cursor", cursor)
  return `/api/posts?${params.toString()}`
}

function buildDraftsApiUrl(cursor: string | null): string {
  return cursor ? `/api/posts/drafts?cursor=${encodeURIComponent(cursor)}` : "/api/posts/drafts"
}

// No channelQueryDefaults: unlike chats, the posts index has no channel to keep
// it live, so it takes standard Query defaults — the warm cache paints instantly
// on navigation while a background refetch on mount keeps it correct.
export function postsFeedQueryOptions(groupId: string | null, decided: boolean) {
  return infiniteQueryOptions({
    queryKey: postsFeedQueryKey(groupId, decided),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) =>
      apiFetch<PostListResponse>(buildPostsApiUrl(groupId, decided, false, pageParam), { signal }),
    getNextPageParam: lastPage => (lastPage.has_more ? lastPage.next_cursor : undefined),
  })
}

export function postsDraftsQueryOptions() {
  return infiniteQueryOptions({
    queryKey: postsDraftsQueryKey(),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => apiFetch<PostDraftListResponse>(buildDraftsApiUrl(pageParam), { signal }),
    getNextPageParam: lastPage => (lastPage.has_more ? lastPage.next_cursor : undefined),
  })
}

// The featured rail is the same collection fetched with ?pinned=true (first page
// only — the rail isn't paginated). It also carries draft_count, so it runs in
// both views and remains the toggle-badge source on a deep link into drafts.
export function pinnedPostsQueryOptions(groupId: string | null, decided: boolean) {
  return queryOptions({
    queryKey: pinnedPostsQueryKey(groupId, decided),
    queryFn: ({ signal }) => apiFetch<PostListResponse>(buildPostsApiUrl(groupId, decided, true, null), { signal }),
  })
}
