import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from "react"

import { ChatComposerEditor, type ChatEditorHandle } from "~/react/composites/chat/ChatComposerEditor"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"

export interface CommentRichTextFieldHandle {
  submit: () => void
  focus: () => void
}

interface CommentRichTextFieldProps {
  // Edit surfaces seed the editor with the existing comment; composers omit it.
  initialContent?: string
  placeholder?: string
  autoFocus?: boolean
  mentionableUsers: MentionUser[]
  // Pass-through box styling so each surface matches its old textarea exactly.
  className?: string
  // Serialized markdown, fired on Cmd/Ctrl+Enter or via the handle's submit().
  onSend: (markdown: string) => void
  // Lags the live doc by the editor's debounce; only used to drive a surface's
  // disabled state, never the payload (onSend re-serializes the live doc).
  onChange?: (markdown: string) => void
  // Escape-to-cancel for edit/reply surfaces. The editor has no onEscape prop,
  // so we intercept it on the wrapping container.
  onEscape?: () => void
}

// The comment-flavoured wrapper around the shared inline editor: markdown in/out,
// typed syntax + shortcuts, @-mentions and :-emoji, and Cmd/Ctrl+Enter to submit.
// Renders only the editor — each call site keeps its own chrome (buttons, borders)
// so the composer looks identical to the textarea it replaces. Attachments are off
// (uploadUrl=null builds no attachments plugin, leaving claimId inert).
export const CommentRichTextField = forwardRef<CommentRichTextFieldHandle, CommentRichTextFieldProps>(
  function CommentRichTextField(
    { initialContent, placeholder, autoFocus, mentionableUsers, className, onSend, onChange, onEscape },
    ref
  ) {
    const editorRef = useRef<ChatEditorHandle | null>(null)
    const [claimId] = useState(() => crypto.randomUUID())

    useImperativeHandle(
      ref,
      () => ({
        submit: () => editorRef.current?.send(),
        focus: () => editorRef.current?.focus(),
      }),
      []
    )

    const handleKeyDown = useMemo(
      () =>
        onEscape
          ? (e: React.KeyboardEvent<HTMLDivElement>) => {
              if (e.key === "Escape") {
                e.preventDefault()
                e.stopPropagation()
                onEscape()
              }
            }
          : undefined,
      [onEscape]
    )

    return (
      <div onKeyDown={handleKeyDown}>
        <ChatComposerEditor
          ref={editorRef}
          autoFocus={autoFocus}
          onSend={onSend}
          onChange={onChange ?? (() => {})}
          onEditPrevious={() => false}
          uploadUrl={null}
          mentionableUsers={mentionableUsers}
          claimId={claimId}
          initialContent={initialContent}
          placeholder={placeholder}
          submitOn="mod-enter"
          className={className}
          showDropCursor={false}
        />
      </div>
    )
  }
)
