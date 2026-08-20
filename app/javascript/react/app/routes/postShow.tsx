import { createRoute, lazyRouteComponent } from "@tanstack/react-router"

import { PostShowSkeleton } from "~/react/features/postShow/PostShowSkeleton"

import { shellRoute } from "../shellRoute"
import { backAndMailboxSearch } from "./mailboxEntryHelpers"

// Read-only post view with live comments. The post title and the draft→edit
// redirect are both handled in the component, since neither is known until the
// GET /api/posts/{id} query resolves — a draft 404s there (see PostShow).
const PostShowView = lazyRouteComponent(() => import("~/react/features/postShow/PostShow"), "PostShow")

// `return_to` carries the "back" target (the index, a search page, a gid redirect
// source); `mailbox_entry_id` scopes the header's mailbox variant when the post
// was opened from the inbox.
export const postShowRoute = createRoute({
  getParentRoute: () => shellRoute,
  path: "/posts/$postId",
  staticData: { hideMobileNav: true },
  validateSearch: backAndMailboxSearch,
  component: PostShowView,
  // Paints while the lazy page chunk downloads, so clicking a post row shows the
  // skeleton instantly — before the page code or its data exist.
  pendingComponent: PostShowSkeleton,
})
