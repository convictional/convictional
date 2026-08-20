import { useLayoutEffect, useRef } from "react"

import { useCommentStore } from "~/react/composites/editor/features/comments/CommentStoreContext"
import type { CommentThread as CommentThreadType } from "~/react/composites/editor/features/comments/commentThreads"
import { useCommentThreadsContext } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { Markdown } from "~/react/composites/markdown/Markdown"
import { Avatar } from "~/react/ui/Avatar"
import { DateTime } from "~/react/ui/DateTime"
import { CommentMenu } from "./CommentMenu"
import { CommentReactions } from "./CommentReactions"
import { EditableComment } from "./EditableComment"
import { ReplyForm } from "./ReplyForm"

interface CommentThreadProps {
  thread: CommentThreadType
  onRemoveMark: (markId: string) => void
  inSheet?: boolean
}

export function CommentThread({ thread, onRemoveMark, inSheet = false }: CommentThreadProps) {
  const { deleteComment, resolveThread, getThreads } = useCommentThreadsContext()
  const activeCommentId = useCommentStore(s => s.activeCommentId)
  const editingCommentId = useCommentStore(s => s.editingCommentId)
  const replyToId = useCommentStore(s => s.replyToId)
  const setActiveComment = useCommentStore(s => s.setActiveComment)
  const setEditingComment = useCommentStore(s => s.setEditingComment)
  const setReplyTo = useCommentStore(s => s.setReplyTo)

  const cardRef = useRef<HTMLDivElement>(null)

  const isActive = activeCommentId === thread.markId
  const isReplying = replyToId === thread.markId

  useLayoutEffect(() => {
    if (inSheet) return
    const el = cardRef.current
    if (!el) return
    el.scrollTop = el.scrollHeight
    // When the card is anchored near the bottom of the doc, max-h-[70vh] alone leaves the
    // card extending past the viewport bottom. Page-scroll to bring its bottom into view so
    // the Reply button is reachable without manual scrolling. Deferred via double rAF: the
    // parent CommentSystem's useEffect schedules positionGutter in its own rAF after our
    // child useEffect runs, so we have to wait one extra frame for the card's `top` to land
    // and for the page's scrollable area to grow to fit the absolutely-positioned card.
    let inner: number | undefined
    const outer = requestAnimationFrame(() => {
      inner = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect()
        const overflowBottom = rect.bottom - window.innerHeight
        if (overflowBottom > 0) {
          window.scrollBy({ top: overflowBottom + 16, behavior: "instant" })
        }
      })
    })
    return () => {
      cancelAnimationFrame(outer)
      if (inner !== undefined) cancelAnimationFrame(inner)
    }
  }, [isActive, isReplying, inSheet])

  if (!isActive) return null

  const handleResolve = async () => {
    const firstComment = thread.comments[0]
    if (!firstComment) return
    try {
      await resolveThread(firstComment.id)
      onRemoveMark(thread.markId)
    } catch {
      // apiFetch handles session/CSRF errors
    }
  }

  const handleDelete = async (commentId: string) => {
    try {
      await deleteComment(commentId)
      // If the thread was removed from the cache (no comments left), remove the editor mark.
      // Read from the cache after the await — the closure's thread.comments is stale.
      const remaining = getThreads().find(t => t.markId === thread.markId)
      if (!remaining) {
        onRemoveMark(thread.markId)
      }
    } catch {
      // apiFetch handles session/CSRF errors
    }
  }

  return (
    <div
      ref={cardRef}
      className={
        inSheet
          ? "group w-full text-xs"
          : "group absolute w-full floating-card !p-3 text-xs max-h-[70vh] overflow-y-auto"
      }
      data-for-comment-id={thread.markId}
      style={inSheet ? undefined : { transition: "opacity 150ms" }}
    >
      <div className="space-y-3">
        {thread.comments.map((comment, index) => (
          <div key={comment.id} className={index > 0 ? "pt-3 border-t border-neutral" : ""}>
            <div className="flex items-start gap-2 mb-1">
              <Avatar displayName={comment.user.display_name} picture={comment.user.picture} />
              <div className="flex flex-col">
                <span className="font-medium">{comment.user.display_name}</span>
                <DateTime datetime={comment.created_at} format="relative" className="text-base-500 text-[10px]" />
              </div>
              <CommentMenu
                comment={comment}
                isFirst={index === 0}
                onEdit={() => setEditingComment(comment.id)}
                onDelete={() => handleDelete(comment.id)}
                onResolve={handleResolve}
              />
            </div>
            {editingCommentId === comment.id ? (
              <EditableComment comment={comment} onCancel={() => setEditingComment(null)} />
            ) : (
              <Markdown source={comment.content} variant="compact" className="mt-0.5" />
            )}
            <CommentReactions comment={comment} />
          </div>
        ))}
      </div>

      {replyToId === thread.markId ? (
        <ReplyForm markId={thread.markId} quotedText={thread.comments[0]?.quoted_text ?? ""} />
      ) : (
        <button
          type="button"
          className="text-xs text-primary mt-2"
          onClick={() => {
            setReplyTo(thread.markId)
            setActiveComment(thread.markId)
          }}
        >
          Reply
        </button>
      )}
    </div>
  )
}
