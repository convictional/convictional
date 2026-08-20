import type { ReactionUser } from "~/react/shared/types"

// The one-level parent/reply threading shape shared by goal comments and post
// comments. The helpers below only ever touch id, parent_id, reactions, and the
// replies array, so the self-referential constraint lets each caller keep its
// own concrete comment type (GoalComment, PostComment) without casting.
export interface ThreadedComment<T extends ThreadedComment<T>> {
  id: string
  parent_id: string | null
  reactions: Record<string, ReactionUser[]>
  replies: T[]
}

export function insertComment<T extends ThreadedComment<T>>(threads: T[], comment: T): T[] {
  if (comment.parent_id) {
    return threads.map(thread =>
      thread.id === comment.parent_id ? { ...thread, replies: [...thread.replies, comment] } : thread
    )
  }
  return [...threads, comment]
}

export function updateComment<T extends ThreadedComment<T>>(threads: T[], updated: T): T[] {
  if (!updated.parent_id) {
    return threads.map(thread => (thread.id === updated.id ? updated : thread))
  }
  return threads.map(thread => {
    if (thread.replies.some(reply => reply.id === updated.id)) {
      return { ...thread, replies: thread.replies.map(reply => (reply.id === updated.id ? updated : reply)) }
    }
    return thread
  })
}

export function removeComment<T extends ThreadedComment<T>>(threads: T[], commentId: string): T[] {
  const filtered = threads.filter(thread => thread.id !== commentId)
  if (filtered.length !== threads.length) return filtered
  return threads.map(thread => ({
    ...thread,
    replies: thread.replies.filter(reply => reply.id !== commentId),
  }))
}

export function updateReactions<T extends ThreadedComment<T>>(
  threads: T[],
  commentId: string,
  reactions: Record<string, ReactionUser[]>
): T[] {
  return threads.map(thread => {
    if (thread.id === commentId) return { ...thread, reactions }
    if (thread.replies.some(reply => reply.id === commentId)) {
      return {
        ...thread,
        replies: thread.replies.map(reply => (reply.id === commentId ? { ...reply, reactions } : reply)),
      }
    }
    return thread
  })
}
