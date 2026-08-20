import type { PaginatedResponse, Post, User } from "~/react/shared/types"

// Mirrors `app.routers.api.schemas.PostDraftResponse`. Drafts are a separate
// collection from published posts (different shape — collaborators, not comment
// data — and never returned by the show endpoint), so they have their own type.
export interface PostDraft {
  id: string
  title: string
  // Client derives "Shared with me" = creator.id !== current user id.
  creator: User
  collaborators: User[]
  updated_at: string
}

// Mirrors `app.routers.api.schemas.PostListDecisionResponse`. The index card's
// decision badge, kept off Post: sparse — only decided posts appear.
export interface PostListDecision {
  post_id: string
  // Total decisions; the card shows "{count} decisions" when >1, else the preview.
  count: number
  comment_preview: string | null
}

// Mirrors `PostListResponse`. The featured rail is the same collection fetched
// with ?pinned=true, not a field here. `draft_count` is the toggle badge,
// computed first-page-only.
export interface PostListResponse extends PaginatedResponse {
  posts: Post[]
  decisions: PostListDecision[]
  draft_count: number
}

// Mirrors `PostDraftListResponse`.
export interface PostDraftListResponse extends PaginatedResponse {
  drafts: PostDraft[]
}

// The published feed and the drafts collection are distinct views, not a status
// filter — each has its own endpoint and item shape. `status=drafts` in the
// browser URL is a client-side view marker, never sent to the API.
export type PostsView = "posts" | "drafts"
