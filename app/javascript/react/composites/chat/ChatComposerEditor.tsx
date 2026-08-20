import { forwardRef, useCallback } from "react"

import { EmojiSuggester } from "~/react/composites/editor/components/EmojiSuggester"
import { MentionSuggester } from "~/react/composites/editor/components/MentionSuggester"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { useArrowUpToEdit } from "~/react/composites/editor/features/useArrowUpToEdit"
import { useAttachments } from "~/react/composites/editor/features/useAttachments"
import { type ChatEditorHandle, useChatEditorHandle } from "~/react/composites/editor/features/useChatEditorHandle"
import { useEmojis } from "~/react/composites/editor/features/useEmojis"
import { useEnterToSend } from "~/react/composites/editor/features/useEnterToSend"
import { useMentions } from "~/react/composites/editor/features/useMentions"
import { DEBOUNCE_MS, useViewPlugin } from "~/react/composites/editor/features/useViewPlugin"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import type { ChatType } from "~/react/shared/types"
import { parse } from "~/richText/schema"

export type { ChatEditorHandle }

interface ChatComposerEditorProps {
  onSend: (content: string) => void
  onChange: (markdown: string) => void
  onEditPrevious: () => boolean
  // Optional: only feeds the placeholder default, so a caller that passes an
  // explicit `placeholder` (or accepts the "Message" default) can omit it.
  chatType?: ChatType
  uploadUrl: string | null
  mentionableUsers: MentionUser[]
  // Whether mentions are available here at all (e.g. dm/self chats don't support them).
  mentionsEnabled?: boolean
  claimId: string
  initialContent?: string
  autoFocus?: boolean
  className?: string
  // Lets a consumer supply its own copy instead of the chatType-derived
  // default (e.g. the email-thread comment composer).
  placeholder?: string
  // "enter" (default): plain Enter sends, Shift+Enter inserts a newline (chat).
  // "mod-enter": only Cmd/Ctrl+Enter sends, plain Enter inserts a newline (post comments).
  submitOn?: "enter" | "mod-enter"
  // When true, the editor handles drops landing on it natively, inserting at
  // the drop point. Chat leaves this off (false): its surface-level dropzone
  // owns drops. Post composers turn it on so an in-editor drop lands at the
  // caret, while their box dropzone still catches drops outside the editable.
  handleDrops?: boolean
  // Off when a surrounding box dropzone shows its own "Drop to upload" overlay.
  showDropCursor?: boolean
}

export const ChatComposerEditor = forwardRef<ChatEditorHandle, ChatComposerEditorProps>(function ChatComposerEditor(
  {
    onSend,
    onChange,
    onEditPrevious,
    chatType,
    uploadUrl,
    mentionableUsers,
    mentionsEnabled = true,
    claimId,
    initialContent,
    autoFocus,
    className,
    placeholder: placeholderProp,
    submitOn = "enter",
    handleDrops = false,
    showDropCursor = true,
  },
  ref
) {
  const isMobile = useIsMobile()
  const placeholder = placeholderProp ?? (chatType === "self" ? "Write a note ..." : "Message")
  const viewPlugin = useViewPlugin({ onChange, debounceMs: DEBOUNCE_MS })
  // Drop the pending serialize before send so the post-send remount's
  // destroy() doesn't flush stale pre-send markdown back into draftContent
  // after sendMessage clears it and rotates claimId.
  const wrappedOnSend = useCallback(
    (content: string) => {
      viewPlugin.cancel()
      onSend(content)
    },
    [onSend, viewPlugin]
  )
  // On mobile there's no Shift key on the soft keyboard, so Enter inserts a
  // newline and sending happens via the dedicated Send button in ComposeBar.
  const enterToSend = useEnterToSend({
    onSend: wrappedOnSend,
    interceptEnter: !isMobile,
    requireModifier: submitOn === "mod-enter",
  })
  const arrowUpToEdit = useArrowUpToEdit({ onEditPrevious })
  const emoji = useEmojis()
  const mentions = useMentions({ users: mentionableUsers, enabled: mentionsEnabled })
  const attachments = useAttachments({ uploadUrl, claimId, handleDrops })
  const { viewRef, plugin: viewRefPlugin } = useViewRef()

  useChatEditorHandle(ref, enterToSend, viewRef, attachments)

  return (
    <Editor
      features={[enterToSend, arrowUpToEdit, viewPlugin, emoji, mentions, attachments, { plugins: [viewRefPlugin] }]}
      placeholder={placeholder}
      className={className ?? "min-h-8 max-h-24 overflow-y-auto focus:outline-hidden text-sm"}
      doc={initialContent ? parse(initialContent) : undefined}
      autoFocus={autoFocus}
      showDropCursor={showDropCursor}
    >
      <EditorContent />
      <EmojiSuggester {...emoji.state} />
      <MentionSuggester {...mentions.state} />
    </Editor>
  )
})
