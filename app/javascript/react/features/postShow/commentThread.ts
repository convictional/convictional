import type { ReactionType } from "~/react/shared/reactions"
import type { Decision, PostComment } from "~/react/shared/types"

// Shared state + actions threaded from the island down to every Comment so each
// row is self-sufficient (calls the hook actions with its own id) without
// CommentList pre-binding a fan of callbacks per comment and per reply. Drilled
// as the `ctx` prop, not React context.
export interface CommentThreadProps {
  workspaceId: string
  currentUserId: string
  // Decisions keyed by comment_gid; drives the inline DecisionMarker per comment.
  // Any workspace member can mark/clear (no per-role gate — R5), so there's no
  // canDecide flag.
  decisionsByGid: Map<string, Decision>
  toggleDecision: (commentGid: string) => void
  // Comment ids considered "new since last visit" — drives the inline New badge.
  newCommentIds: Set<string>
  highlightedId: string | null
  createComment: (
    content: string,
    options?: { parentId?: string; attachmentClaimId?: string; unfurlLinks?: boolean }
  ) => Promise<PostComment | null>
  editComment: (
    commentId: string,
    content: string,
    options?: { attachmentClaimId?: string; unfurlLinks?: boolean }
  ) => Promise<PostComment | null>
  deleteComment: (commentId: string) => Promise<void>
  toggleReaction: (commentId: string, reactionType: ReactionType) => void
}
