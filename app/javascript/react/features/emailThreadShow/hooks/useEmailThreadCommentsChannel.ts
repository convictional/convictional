import { useCallback, useEffect, useRef, useState } from "react"

import { useChannel } from "~/react/shared/hooks/useChannel"
import type { ReactionUser, User, EmailThreadComment } from "~/react/shared/types"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

// Stale-typing cleanup interval. The server emits typing payloads on every
// keystroke (debounced client-side), so if the channel goes silent we clear
// the indicator after this much idle time (3000ms allows for natural pauses).
const TYPING_TIMEOUT_MS = 3000

function isUser(value: unknown): value is User {
  if (!value || typeof value !== "object") return false
  const u = value as Record<string, unknown>
  return typeof u.id === "string" && typeof u.display_name === "string"
}

function isUserArray(value: unknown): value is User[] {
  return Array.isArray(value) && value.every(isUser)
}

function isEmailThreadComment(value: unknown): value is EmailThreadComment {
  if (!value || typeof value !== "object") return false
  const c = value as Record<string, unknown>
  return typeof c.id === "string" && typeof c.content === "string" && typeof c.created_at === "string"
}

function isReactionMap(value: unknown): value is Record<string, ReactionUser[]> {
  if (!value || typeof value !== "object") return false
  return Object.values(value as Record<string, unknown>).every(isUserArray)
}

interface UseEmailThreadCommentsChannelOptions {
  emailThreadId: string | null
  onCommentCreated: (comment: EmailThreadComment) => void
  onCommentUpdated: (comment: EmailThreadComment) => void
  onCommentRemoved: (commentId: string) => void
  onReactionToggled: (commentId: string, reactions: Record<string, ReactionUser[]>) => void
}

interface UseEmailThreadCommentsChannelResult {
  typingUsers: User[]
}

// Subscribes to the thread-scoped `email_thread_comments` channel. Branches on
// action:
//   - TYPING: replaces the typing-user set wholesale (server already filters
//     the actor out). A timeout clears the indicator if the channel goes
//     silent.
//   - CREATED: fires onCommentCreated with the serialized comment. Sender is
//     not skipped — the comment list has a single writer (this channel).
//   - UPDATED: fires onCommentUpdated with the serialized comment. Sender is
//     not skipped, same reasoning.
//   - REMOVED: fires onCommentRemoved with the comment id. Sender is not
//     skipped, same reasoning.
//   - REACTION_TOGGLED: fires onReactionToggled with the comment id and its
//     full reactions map (the server broadcasts the recomputed map, not a
//     delta).
export function useEmailThreadCommentsChannel({
  emailThreadId,
  onCommentCreated,
  onCommentUpdated,
  onCommentRemoved,
  onReactionToggled,
}: UseEmailThreadCommentsChannelOptions): UseEmailThreadCommentsChannelResult {
  const [typingUsers, setTypingUsers] = useState<User[]>([])
  const typingTimeoutRef = useRef<number | null>(null)

  const handleEvent = useCallback(
    (action: ChannelEventAction, data: Record<string, unknown>) => {
      switch (action) {
        case ChannelEventAction.TYPING: {
          const users = isUserArray(data.typing_users) ? data.typing_users : []
          setTypingUsers(users)
          if (typingTimeoutRef.current !== null) window.clearTimeout(typingTimeoutRef.current)
          if (users.length > 0) {
            typingTimeoutRef.current = window.setTimeout(() => setTypingUsers([]), TYPING_TIMEOUT_MS)
          }
          return
        }
        case ChannelEventAction.CREATED: {
          if (!isEmailThreadComment(data.comment)) return
          onCommentCreated(data.comment)
          return
        }
        case ChannelEventAction.UPDATED: {
          if (!isEmailThreadComment(data.comment)) return
          onCommentUpdated(data.comment)
          return
        }
        case ChannelEventAction.REMOVED: {
          const commentId = data.comment_id
          if (typeof commentId === "string") onCommentRemoved(commentId)
          return
        }
        case ChannelEventAction.REACTION_TOGGLED: {
          const commentId = data.comment_id
          if (typeof commentId !== "string" || !isReactionMap(data.reactions)) return
          onReactionToggled(commentId, data.reactions)
          return
        }
      }
    },
    [onCommentCreated, onCommentUpdated, onCommentRemoved, onReactionToggled]
  )

  useChannel(
    emailThreadId ? { stream: ChannelStream.EMAIL_THREAD_COMMENTS, params: { email_thread_id: emailThreadId } } : null,
    ChannelEventResource.EMAIL_THREAD_COMMENT,
    handleEvent
  )

  useEffect(() => {
    return () => {
      if (typingTimeoutRef.current !== null) window.clearTimeout(typingTimeoutRef.current)
    }
  }, [])

  return { typingUsers }
}
