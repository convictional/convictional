import { getRouteApi, useLocation, useNavigate } from "@tanstack/react-router"
import { useCallback } from "react"

import { usePostsData } from "~/react/features/postsIndex/hooks/usePostsData"
import { useSearchOverlay } from "~/react/features/postsIndex/hooks/useSearchOverlay"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useOrganizationMembers } from "~/react/shared/hooks/useOrganizationMembers"
import { withReturnTo } from "~/react/shared/returnTo"
import { ErrorState } from "~/react/ui/ErrorState"
import { LoadMoreSentinel } from "~/react/ui/LoadMoreSentinel"
import { DraftCard } from "./components/DraftCard"
import { NewPostForm } from "./components/NewPostForm"
import { PinnedPosts } from "./components/PinnedPosts"
import { PostCard } from "./components/PostCard"
import { PostsEmptyState } from "./components/PostsEmptyState"
import { PostsFirstRunComposer } from "./components/PostsFirstRunComposer"
import { PostsHeader } from "./components/PostsHeader"
import { PostsSearch } from "./components/PostsSearch"
import { PostsListSkeleton } from "./PostsListSkeleton"

// The route id carries the pathless shell parent prefix (shellRoute has id
// "shell"), so the typed accessor is addressed as "/shell/posts".
const routeApi = getRouteApi("/shell/posts")

export function PostsIndex() {
  const routeSearch = routeApi.useSearch()
  const navigate = useNavigate()
  // `canAnnounce` is an advisory UI hint for the composer's Announcement option —
  // the create endpoint re-gates it authoritatively. Sourced from the current
  // user now that data-props is gone.
  const { user } = useCurrentUser()
  const canAnnounce = user?.is_admin ?? false

  // The current index URL (filters + q) — stamped onto each card link as the
  // show page's back target so its back button returns to this exact view.
  const returnTo = useLocation({ select: location => location.href })

  // Push a debounced query into the route (replace, so typing doesn't stack
  // history); results navigation is a full-document gid load carrying return_to.
  const commitQuery = useCallback(
    (query: string) =>
      void navigate({ to: "/posts", replace: true, search: prev => ({ ...prev, q: query || undefined }) }),
    [navigate]
  )
  const navigateToResult = useCallback((sourceUrl: string) => window.location.assign(withReturnTo(sourceUrl)), [])

  const data = usePostsData()
  const search = useSearchOverlay({
    routeQuery: routeSearch.q ?? "",
    onCommit: commitQuery,
    onNavigateToResult: navigateToResult,
  })
  const { groups: orgGroups } = useOrganizationMembers()

  const isDrafts = data.view === "drafts"
  const showPinned = !isDrafts && data.pinnedPosts.length > 0
  const activeCount = isDrafts ? data.drafts.length : data.posts.length
  // Empty state is suppressed when the pinned rail has items (posts view only).
  const isEmpty = activeCount === 0 && !showPinned
  // First-run = the org has no posts at all (default feed, no filters), vs. a filter that just
  // happens to be empty. Confirmed only once loading resolves, so the standard composer shows during
  // load and we swap to the welcome panel only when we know the org is genuinely empty.
  const isFirstRun = isEmpty && data.view === "posts" && !data.decided && !data.groupId
  const showFirstRunComposer = isFirstRun && !data.loading && !data.error

  return (
    <div>
      <PostsHeader
        isSearch={search.isOpen}
        view={data.view}
        groupId={data.groupId}
        decided={data.decided}
        draftCount={data.draftCount}
        orgGroups={orgGroups}
        onSelectGroup={data.changeGroup}
        onToggleDecided={data.toggleDecided}
        onShowDrafts={data.showDrafts}
        onShowPosts={data.showPosts}
        query={search.query}
        onChangeQuery={search.setQuery}
        onKeyDown={search.handleKeyDown}
        onOpenSearch={search.openSearch}
        onCloseSearch={search.handleClose}
        searchLoading={search.loading && search.results.length > 0}
      />

      {search.isOpen ? (
        <div className="w-full px-2">
          <PostsSearch search={search} />
        </div>
      ) : (
        <div className="px-2">
          <div className="mt-8 mb-6">
            {showFirstRunComposer ? (
              <PostsFirstRunComposer canAnnounce={canAnnounce} orgGroups={orgGroups} onCreated={data.prependPost} />
            ) : (
              <NewPostForm canAnnounce={canAnnounce} orgGroups={orgGroups} onCreated={data.prependPost} />
            )}
          </div>

          {showPinned && (
            <PinnedPosts posts={data.pinnedPosts} decisionsByPostId={data.decisionsByPostId} returnTo={returnTo} />
          )}

          {data.loading && activeCount === 0 ? (
            <PostsListSkeleton />
          ) : data.error ? (
            <ErrorState message="Failed to load posts. Please try refreshing the page." />
          ) : (
            <>
              {/* First-run teaching lives in the composer panel above, so suppress the generic
                  empty state there; other empty views (drafts, decided, a group) still show it. */}
              {isEmpty && !showFirstRunComposer && <PostsEmptyState view={data.view} decided={data.decided} />}
              {activeCount > 0 && (
                <ol className="divide-y divide-base-300 border border-base-300 rounded-2xl overflow-hidden shadow-xs">
                  {isDrafts
                    ? data.drafts.map(draft => (
                        <DraftCard key={draft.id} draft={draft} currentUserId={user?.id ?? null} returnTo={returnTo} />
                      ))
                    : data.posts.map(post => (
                        <PostCard
                          key={post.id}
                          post={post}
                          decision={data.decisionsByPostId.get(post.id) ?? null}
                          returnTo={returnTo}
                        />
                      ))}
                </ol>
              )}
              {data.hasMore && <LoadMoreSentinel onIntersect={data.loadMore} loading={data.loadingMore} />}
            </>
          )}
        </div>
      )}
    </div>
  )
}
