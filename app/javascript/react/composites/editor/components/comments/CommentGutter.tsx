import { useCallback } from "react"

import { useCommentStore } from "~/react/composites/editor/features/comments/CommentStoreContext"
import type { CommentThread } from "~/react/composites/editor/features/comments/commentThreads"
import { useCommentThreadsContext } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { Avatar } from "~/react/ui/Avatar"

// Deduplicate thread participants (preserving order)
function threadParticipants(thread: CommentThread, limit = 3) {
  const seen = new Set<string>()
  const users: CommentThread["comments"][0]["user"][] = []
  for (const c of thread.comments) {
    if (!seen.has(c.user.id)) {
      seen.add(c.user.id)
      users.push(c.user)
      if (users.length >= limit) break
    }
  }
  return users
}

interface CommentGutterProps {
  reactions: readonly { emoji: string; label: string }[]
  onOpenComment: () => void
  onOpenReaction: () => void
  onAddReaction: (emoji: string) => void
  editorFocused: boolean
  cursorBlockHasContent: boolean
  cursorTop: number
}

export function CommentGutter({
  reactions,
  onOpenComment,
  onOpenReaction,
  onAddReaction,
  editorFocused,
  cursorBlockHasContent,
  cursorTop,
}: CommentGutterProps) {
  const { threads } = useCommentThreadsContext()
  const activeCommentId = useCommentStore(s => s.activeCommentId)
  const activating = useCommentStore(s => s.activating)
  const showCommentCard = useCommentStore(s => s.showCommentCard)
  const showReactionPicker = useCommentStore(s => s.showReactionPicker)
  const setActiveComment = useCommentStore(s => s.setActiveComment)

  const handleAvatarClick = useCallback(
    (markId: string, e: React.MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()
      setActiveComment(markId)
    },
    [setActiveComment]
  )

  const showCursor =
    editorFocused &&
    cursorBlockHasContent &&
    !showCommentCard &&
    !showReactionPicker &&
    !activeCommentId &&
    !activating

  return (
    <>
      {/* Cursor buttons + reaction picker — positioned in the parent wrapper's pr-12 padding area */}
      <div
        id="comment-gutter-actions"
        className="hidden md:block absolute top-0 -right-10 w-8 z-10"
        data-comment-gutter-actions
      >
        {showCursor && (
          <div className="absolute left-1/2 -translate-x-1/2" data-gutter-cursor>
            <div className="join join-vertical">
              <button
                type="button"
                className="btn btn-square join-item"
                title="Add comment"
                onMouseDown={e => {
                  e.preventDefault()
                  e.stopPropagation()
                  onOpenComment()
                }}
              >
                <span className="material-symbols-outlined text-lg">comment</span>
              </button>
              <button
                type="button"
                className="btn btn-square join-item"
                title="Add reaction"
                onMouseDown={e => {
                  e.preventDefault()
                  e.stopPropagation()
                  onOpenReaction()
                }}
              >
                <span className="material-symbols-outlined text-lg">add_reaction</span>
              </button>
            </div>
          </div>
        )}
        {showReactionPicker && (
          <div className="absolute right-0" style={{ top: cursorTop }}>
            <div className="floating-card !p-1 flex gap-0.5">
              {reactions.map(r => (
                <button
                  key={r.emoji}
                  type="button"
                  className="btn btn-ghost btn-xs btn-square"
                  onClick={() => onAddReaction(r.emoji)}
                >
                  <span role="img" aria-label={r.label}>
                    {r.emoji}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Avatar gutter */}
      <div
        id="comment-gutter"
        className="hidden md:block absolute top-0 -right-10 w-8 z-10"
        data-comment-gutter-avatars
      >
        {threads.map(thread => {
          const participants = threadParticipants(thread)
          return (
            <div
              key={thread.markId}
              className="absolute cursor-pointer -mt-1"
              data-avatar-for={thread.markId}
              style={{ display: activeCommentId === thread.markId ? "none" : undefined }}
              onMouseDown={e => handleAvatarClick(thread.markId, e)}
            >
              <div className="flex flex-row-reverse">
                {[...participants].reverse().map((user, i) => (
                  <div
                    key={user.id}
                    className={i < participants.length - 1 ? "-ml-2" : ""}
                    style={{ zIndex: participants.length - i }}
                  >
                    <Avatar displayName={user.display_name} picture={user.picture} />
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}
