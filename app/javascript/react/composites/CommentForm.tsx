import { useRef, useState } from "react"

import {
  CommentRichTextField,
  type CommentRichTextFieldHandle,
} from "~/react/composites/editor/components/comments/CommentRichTextField"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"

interface CommentFormProps {
  placeholder?: string
  onSubmit: (content: string) => Promise<void>
  autoFocus?: boolean
  mentionableUsers?: MentionUser[]
}

export function CommentForm({
  placeholder = "Add a comment...",
  onSubmit,
  autoFocus,
  mentionableUsers = [],
}: CommentFormProps) {
  const [content, setContent] = useState("")
  const [submitting, setSubmitting] = useState(false)
  // Bumped on each successful send to remount a clean editor (ProseMirror is
  // uncontrolled after mount, so clearing means starting a fresh instance).
  const [editorKey, setEditorKey] = useState(0)
  const fieldRef = useRef<CommentRichTextFieldHandle>(null)

  async function handleSend(markdown: string) {
    const trimmed = markdown.trim()
    if (!trimmed || submitting) return
    setSubmitting(true)
    try {
      await onSubmit(trimmed)
      setContent("")
      setEditorKey(k => k + 1)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form
      className="relative"
      onSubmit={e => {
        e.preventDefault()
        fieldRef.current?.submit()
      }}
    >
      <div className="textarea textarea-bordered w-full text-sm min-h-[2.5rem] pr-9 overflow-hidden">
        <CommentRichTextField
          key={editorKey}
          ref={fieldRef}
          placeholder={placeholder}
          // Refocus a fresh editor after a send, matching the old textarea's post-submit focus.
          autoFocus={autoFocus || editorKey > 0}
          mentionableUsers={mentionableUsers}
          className="max-h-40 overflow-y-auto focus:outline-hidden"
          onSend={handleSend}
          onChange={setContent}
        />
      </div>
      <button
        type="submit"
        className="absolute right-2 bottom-2 text-primary hover:text-primary/80 disabled:opacity-30 cursor-pointer"
        disabled={!content.trim() || submitting}
      >
        <span className="material-symbols-outlined text-base">arrow_upward</span>
      </button>
    </form>
  )
}
