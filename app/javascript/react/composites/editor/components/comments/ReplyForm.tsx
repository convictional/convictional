import { useCallback, useRef } from "react"

import { useCommentStore } from "~/react/composites/editor/features/comments/CommentStoreContext"
import { useCommentThreadsContext } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { CommentRichTextField, type CommentRichTextFieldHandle } from "./CommentRichTextField"

export function ReplyForm({ markId, quotedText }: { markId: string; quotedText: string }) {
  const { createComment } = useCommentThreadsContext()
  const setReplyTo = useCommentStore(s => s.setReplyTo)
  const mentionableUsers = useCommentStore(s => s.mentionableUsers)
  const fieldRef = useRef<CommentRichTextFieldHandle>(null)

  const handleSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim()
      if (!trimmed) return
      try {
        await createComment(trimmed, quotedText, markId)
        setReplyTo(null)
      } catch {
        // apiFetch handles session/CSRF errors — keep the form open so the user can retry
      }
    },
    [markId, quotedText, createComment, setReplyTo]
  )

  return (
    <div className="mt-3 pt-3 border-t border-neutral">
      <CommentRichTextField
        ref={fieldRef}
        autoFocus
        placeholder="Reply..."
        mentionableUsers={mentionableUsers}
        className="w-full text-sm p-2 bg-base-100 focus:outline-hidden leading-relaxed rounded-lg min-h-0 max-h-64 overflow-y-auto"
        onSend={handleSubmit}
        onEscape={() => setReplyTo(null)}
      />
      <div className="flex justify-end gap-1 mt-1">
        <button type="button" className="btn btn-ghost btn-xs" onClick={() => setReplyTo(null)}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary btn-xs" onClick={() => fieldRef.current?.submit()}>
          Reply
        </button>
      </div>
    </div>
  )
}
