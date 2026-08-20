import { useCallback, useRef } from "react"

import { useCommentStore } from "~/react/composites/editor/features/comments/CommentStoreContext"
import type { Comment } from "~/react/composites/editor/features/comments/commentThreads"
import { useCommentThreadsContext } from "~/react/composites/editor/features/comments/CommentThreadsContext"
import { CommentRichTextField, type CommentRichTextFieldHandle } from "./CommentRichTextField"

export function EditableComment({ comment, onCancel }: { comment: Comment; onCancel: () => void }) {
  const { editComment } = useCommentThreadsContext()
  const mentionableUsers = useCommentStore(s => s.mentionableUsers)
  const fieldRef = useRef<CommentRichTextFieldHandle>(null)

  const handleSubmit = useCallback(
    async (value: string) => {
      const trimmed = value.trim()
      if (!trimmed) return
      try {
        await editComment(comment.id, trimmed)
      } catch {
        // apiFetch handles session/CSRF errors — keep edit mode open so the user can retry
      }
    },
    [comment.id, editComment]
  )

  return (
    <div className="mt-1">
      <CommentRichTextField
        ref={fieldRef}
        autoFocus
        initialContent={comment.content}
        mentionableUsers={mentionableUsers}
        className="w-full text-sm p-2 bg-base-100 focus:outline-hidden leading-relaxed rounded-lg min-h-0 max-h-64 overflow-y-auto"
        onSend={handleSubmit}
        onEscape={onCancel}
      />
      <div className="flex justify-end gap-1 mt-1">
        <button type="button" className="btn btn-ghost btn-xs" onClick={onCancel}>
          Cancel
        </button>
        <button type="button" className="btn btn-primary btn-xs" onClick={() => fieldRef.current?.submit()}>
          Save
        </button>
      </div>
    </div>
  )
}
