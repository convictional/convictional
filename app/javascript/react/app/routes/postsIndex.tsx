import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { PostsListSkeleton } from "~/react/features/postsIndex/PostsListSkeleton"
import { useDocumentTitle } from "~/react/shared/hooks/useDocumentTitle"

import { shellRoute } from "../shellRoute"

// See documentsIndex.tsx for the route-definition conventions. lazyRouteComponent
// code-splits the page chunk while the route's contracts (validateSearch) stay eager.
const PostsIndexView = lazyRouteComponent(() => import("~/react/features/postsIndex/PostsIndex"), "PostsIndex")

// The index URL carries the browse filters (published feed vs `status=drafts`, a
// `group_id`, a `decided` toggle) plus a full-text `q`. Defaults normalize out of
// the URL: the published feed is absent-`status`, `decided=false` is absent, and
// empty group/query are absent. This preserves the legacy `?status=drafts` /
// `?group_id=…` / `?decided=true` contract that deep links and url_for("posts_index")
// still produce server-side.
export interface PostsIndexSearch {
  status?: "drafts"
  group_id?: string
  decided?: boolean
  q?: string
}

function PostsPage() {
  useDocumentTitle("Posts")
  return <PostsIndexView />
}

export const postsIndexRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/posts",
  validateSearch: (search: Record<string, unknown>): PostsIndexSearch => ({
    status: search.status === "drafts" ? "drafts" : undefined,
    group_id: typeof search.group_id === "string" && search.group_id ? search.group_id : undefined,
    // Search params arrive parsed (JSON) from the URL, so `?decided=true` is the
    // boolean true; tolerate the string form defensively. false normalizes out.
    decided: search.decided === true || search.decided === "true" ? true : undefined,
    q: typeof search.q === "string" && search.q ? search.q : undefined,
  }),
  component: PostsPage,
  // Paints while the lazy page chunk downloads, so the skeleton shows the instant
  // a <Link> lands here — before the page code or its data exist.
  pendingComponent: PostsListSkeleton,
})
