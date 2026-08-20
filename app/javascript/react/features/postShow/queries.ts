import { queryOptions } from "@tanstack/react-query"

import { apiFetch } from "~/react/shared/apiFetch"
import { updateReactions } from "~/react/shared/commentThreads"
import { channelQueryDefaults } from "~/react/shared/queryClient"
import { toggleReactionInMap, type ReactionType } from "~/react/shared/reactions"
import type { PostComment, PostCommentListResponse, PostShowResponse, ReactionUser } from "~/react/shared/types"

import { postShowUrl } from "./urls"

// Nested so a future invalidatePost could drop both the entity and its comments.
export const postQueryKey = (postId: string) => ["post", postId] as const
export const postCommentsQueryKey = (postId: string) => ["post", postId, "comments"] as const

// A draft 404s at GET /api/posts/{id} (the show endpoint excludes drafts) — the
// component turns that 404 into the draft→edit redirect. Declaring it expected
// keeps it out of Sentry while apiFetch still throws so the query surfaces it —
// the posts analogue of documents' ACCESS_DENIED.
const DRAFT_REDIRECT: { expectedStatuses: number[] } = { expectedStatuses: [404] }

// The post entity (+ its mailbox entry). STANDARD Query defaults, deliberately
// NOT channelQueryDefaults: no channel keeps the post metadata live — it changes
// only through the viewer's own PATCH/pin/mailbox actions, exactly like a
// document's title/sharing. With no channel to invalidate on, a channel-first
// query would strand indefinitely stale state; standard defaults recover on
// remount and the mutations patch the cache explicitly (documents.ts posture).
export function postQueryOptions(postId: string, mailboxEntryId?: string) {
  return queryOptions({
    queryKey: postQueryKey(postId),
    queryFn: ({ signal }) =>
      apiFetch<PostShowResponse>(postShowUrl(postId, mailboxEntryId), { signal }, DRAFT_REDIRECT),
  })
}

// The comments cache holds the full nested tree the list endpoint returns, which
// INCLUDES the post-body "original" comment as one top-level entry. channelQueryDefaults
// (channel-first): the post_comments channel is the freshness and recovery source.
// `enabled` gates on originalId so the split always has an id to route the original
// by, and so the seed (see usePostComments) is in place before the first fetch.
export function postCommentsQueryOptions(postId: string, originalId: string | undefined) {
  return queryOptions({
    ...channelQueryDefaults,
    queryKey: postCommentsQueryKey(postId),
    enabled: !!originalId,
    queryFn: async ({ signal }) => {
      const { comments } = await apiFetch<PostCommentListResponse>(`/api/posts/${postId}/comments`, { signal })
      return comments
    },
  })
}

// Split the flat cache tree into the render shape: the post-body original (by id)
// and the top-level list (everything else). Mirrors useDecisions' selectDecisions
// and useCommentThreads' groupIntoThreads. A null originalId (a post with no
// original comment) routes everything to topLevel.
export function splitPostComments(
  comments: PostComment[],
  originalId: string | undefined
): { original: PostComment | null; topLevel: PostComment[] } {
  if (!originalId) return { original: null, topLevel: comments }
  let original: PostComment | null = null
  const topLevel: PostComment[] = []
  for (const comment of comments) {
    if (comment.id === originalId) original = comment
    else topLevel.push(comment)
  }
  return { original, topLevel }
}

// True when a comment with `id` already lives in the tree — top-level (so also the
// original, itself a top-level entry) or as a reply. Makes the CREATED channel
// handler and the create mutation idempotent: insertComment does not dedup, and
// the broadcast has no author-skip, so the creating tab receives the echo of a
// comment it already inserted.
export function commentInTree(comments: PostComment[], id: string): boolean {
  return comments.some(c => c.id === id || c.replies.some(r => r.id === id))
}

// Optimistically flip the viewer's reaction on a comment anywhere in the tree.
// Posts keep their own (rather than reusing shared/commentThreads.ts) because that
// shared helper's updateReactions sets reactions wholesale; the optimistic path
// has to compute the toggled map first, which toggleReactionInMap does.
export function toggleReactionInTree(
  comments: PostComment[],
  commentId: string,
  reactionType: ReactionType,
  user: ReactionUser
): PostComment[] {
  const target =
    comments.find(c => c.id === commentId) ?? comments.flatMap(c => c.replies).find(r => r.id === commentId)
  if (!target) return comments
  return updateReactions(comments, commentId, toggleReactionInMap(target.reactions, reactionType, user))
}
