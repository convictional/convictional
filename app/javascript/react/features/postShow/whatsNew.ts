import { markdownToPlainText } from "~/react/composites/markdown/toPlainText"
import type { PostComment, Decision, User } from "~/react/shared/types"

// Plain-text preview length for what's-new comment rows.
const COMMENT_PREVIEW_LENGTH = 80

export interface WhatsNewComment {
  id: string
  user: User
  preview: string
}

export interface WhatsNewGroup {
  parentCommentId: string | null
  // For reply groups, the parent comment's author name ("Replying to {name}").
  contextAuthorName: string | null
  comments: WhatsNewComment[]
}

export interface WhatsNewDecision {
  // The decided comment (for the author avatar + jump target).
  comment: PostComment
  // Who marked it ("marked by {name}"), distinct from the comment's author.
  decidedByName: string | null
}

export interface WhatsNew {
  totalCount: number
  lastVisitAt: string
  decisions: WhatsNewDecision[]
  firstNewCommentId: string | null
  groups: WhatsNewGroup[]
}

function isNewerThan(timestamp: string, since: number): boolean {
  const parsed = Date.parse(timestamp)
  return !Number.isNaN(parsed) && parsed > since
}

function toWhatsNewComment(comment: PostComment): WhatsNewComment {
  return {
    id: comment.id,
    user: comment.user,
    preview: markdownToPlainText(comment.content, { maxLength: COMMENT_PREVIEW_LENGTH }),
  }
}

// Builds the "what's new since last visit" summary entirely client-side. The
// server sends `last_visit_at` rather than a precomputed `whats_new` bag: a
// comment is new if it postdates the last visit and wasn't authored by the
// viewer; the decision is new under the same rule plus a different-decider
// check. Returns null when there's nothing new (or no prior visit), which the
// panel treats as "don't render".
export function computeWhatsNew(
  topLevel: PostComment[],
  decisions: Decision[],
  commentsByGid: Map<string, PostComment>,
  lastVisitAt: string | null,
  currentUserId: string
): WhatsNew | null {
  if (!lastVisitAt) return null
  const since = Date.parse(lastVisitAt)
  if (Number.isNaN(since)) return null

  const newTopLevel: WhatsNewComment[] = []
  const replyGroups: WhatsNewGroup[] = []
  let totalCount = 0
  let firstNewCommentId: string | null = null
  let firstNewCreatedAt = Infinity

  // A comment is "new" if it postdates the last visit and isn't the viewer's own.
  const isNew = (comment: PostComment) => comment.user.id !== currentUserId && isNewerThan(comment.created_at, since)

  // Tally an already-new comment toward the total and the first-new pointer.
  const trackNew = (comment: PostComment) => {
    totalCount += 1
    const created = Date.parse(comment.created_at)
    if (created < firstNewCreatedAt) {
      firstNewCreatedAt = created
      firstNewCommentId = comment.id
    }
  }

  for (const comment of topLevel) {
    if (isNew(comment)) {
      trackNew(comment)
      newTopLevel.push(toWhatsNewComment(comment))
    }
    const newReplies = comment.replies.filter(isNew)
    newReplies.forEach(trackNew)
    if (newReplies.length > 0) {
      replyGroups.push({
        parentCommentId: comment.id,
        contextAuthorName: comment.user.display_name,
        comments: newReplies.map(toWhatsNewComment),
      })
    }
  }

  // Every decision marked since the last visit by someone other than the viewer,
  // each counting toward the total. Only surface decisions whose comment is
  // resolvable in the tree — a row needs an author/jump target to render.
  const newDecisions: WhatsNewDecision[] = []
  for (const decision of decisions) {
    const comment = commentsByGid.get(decision.comment_gid)
    if (comment && decision.decided_by?.id !== currentUserId && isNewerThan(decision.decided_at, since)) {
      newDecisions.push({ comment, decidedByName: decision.decided_by?.display_name ?? null })
    }
  }
  totalCount += newDecisions.length

  // A decisions-only update leaves firstNewCommentId null (no new comments tracked
  // it), making the header "Jump to new" button a no-op. Seed it from the first new
  // decision's comment so the jump lands on a decision row.
  if (firstNewCommentId === null && newDecisions.length > 0) {
    firstNewCommentId = newDecisions[0].comment.id
  }

  if (totalCount === 0) return null

  const groups: WhatsNewGroup[] = []
  if (newTopLevel.length > 0) {
    groups.push({ parentCommentId: null, contextAuthorName: null, comments: newTopLevel })
  }
  groups.push(...replyGroups)

  return {
    totalCount,
    lastVisitAt,
    decisions: newDecisions,
    firstNewCommentId,
    groups,
  }
}
