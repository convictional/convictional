import { useCallback, useEffect, useRef } from "react"

import { useCommentStore } from "~/react/composites/editor/features/comments/CommentStoreContext"
import { useCommentThreadsContext } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { Avatar } from "~/react/ui/Avatar"
import { BottomSheet } from "~/react/ui/BottomSheet"
import { CommentRichTextField, type CommentRichTextFieldHandle } from "./CommentRichTextField"
import { CommentThread } from "./CommentThread"

interface CommentCardsProps {
  currentUser: { id: string; displayName: string; picture?: string | null }
  onRemoveMark: (markId: string) => void
  onCommitPendingComment: (pendingId: string) => void
  onClearPendingComment: (pendingId: string) => void
}

export function CommentCards({
  currentUser,
  onRemoveMark,
  onCommitPendingComment,
  onClearPendingComment,
}: CommentCardsProps) {
  const isMobile = useIsMobile()
  const { threads, createComment } = useCommentThreadsContext()
  const showCommentCard = useCommentStore(s => s.showCommentCard)
  const commentCardTop = useCommentStore(s => s.commentCardTop)
  const pendingCommentId = useCommentStore(s => s.pendingCommentId)
  const selectedQuotedText = useCommentStore(s => s.selectedQuotedText)
  const activeCommentId = useCommentStore(s => s.activeCommentId)
  const closeCommentCard = useCommentStore(s => s.closeCommentCard)
  const setActiveComment = useCommentStore(s => s.setActiveComment)
  const mentionableUsers = useCommentStore(s => s.mentionableUsers)

  const handleSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim()
      if (!trimmed) return
      try {
        await createComment(trimmed, selectedQuotedText, pendingCommentId)
        // Comment now exists in the cache; promote the pending decoration to the
        // real synced mark before clearing pendingCommentId.
        onCommitPendingComment(pendingCommentId)
        closeCommentCard()
      } catch {
        // apiFetch handles session/CSRF errors — keep the card open so the user can retry
      }
    },
    [selectedQuotedText, pendingCommentId, createComment, closeCommentCard, onCommitPendingComment]
  )

  // Close on Escape
  useEffect(() => {
    if (!showCommentCard) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClearPendingComment(pendingCommentId)
        closeCommentCard()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [showCommentCard, pendingCommentId, closeCommentCard, onClearPendingComment])

  const newCommentForm = showCommentCard ? (
    <NewCommentForm
      currentUser={currentUser}
      mentionableUsers={mentionableUsers}
      onSubmit={handleSubmit}
      onCancel={() => {
        onClearPendingComment(pendingCommentId)
        closeCommentCard()
      }}
    />
  ) : null

  if (isMobile) {
    const activeThread = activeCommentId ? threads.find(t => t.markId === activeCommentId) : undefined
    if (showCommentCard) {
      return (
        <BottomSheet
          ariaLabel="Add comment"
          onClose={() => {
            onClearPendingComment(pendingCommentId)
            closeCommentCard()
          }}
        >
          <div className="p-3 pt-0 overflow-y-auto">{newCommentForm}</div>
        </BottomSheet>
      )
    }
    if (activeThread) {
      return (
        <BottomSheet ariaLabel="Comment thread" onClose={() => setActiveComment(null)}>
          <div className="p-3 pt-0 overflow-y-auto">
            <CommentThread thread={activeThread} onRemoveMark={onRemoveMark} inSheet />
          </div>
        </BottomSheet>
      )
    }
    return null
  }

  return (
    <div data-comment-cards className="absolute top-0 -right-64 w-64 z-40">
      {showCommentCard && (
        <div data-comment-form className="absolute w-full floating-card !p-3 z-10" style={{ top: commentCardTop }}>
          {newCommentForm}
        </div>
      )}

      {/* Existing thread cards */}
      {threads.map(thread => (
        <CommentThread key={thread.markId} thread={thread} onRemoveMark={onRemoveMark} />
      ))}
    </div>
  )
}

function NewCommentForm({
  currentUser,
  mentionableUsers,
  onSubmit,
  onCancel,
}: {
  currentUser: { displayName: string; picture?: string | null }
  mentionableUsers: MentionUser[]
  onSubmit: (content: string) => void
  onCancel: () => void
}) {
  const fieldRef = useRef<CommentRichTextFieldHandle>(null)

  return (
    <>
      <div className="flex items-center gap-2 mb-2">
        <Avatar displayName={currentUser.displayName} picture={currentUser.picture ?? null} />
        <span className="text-xs font-medium">{currentUser.displayName}</span>
      </div>
      <CommentRichTextField
        ref={fieldRef}
        autoFocus
        placeholder="Add a comment..."
        mentionableUsers={mentionableUsers}
        className="w-full text-sm p-2 bg-base-100 focus:outline-hidden leading-relaxed rounded-lg min-h-0 max-h-64 overflow-y-auto"
        onSend={onSubmit}
      />
      <div className="flex justify-end gap-2 mt-2">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => fieldRef.current?.submit()}>
          Comment
        </button>
      </div>
    </>
  )
}
