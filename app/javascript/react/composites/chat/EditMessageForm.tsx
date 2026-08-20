import { useCallback, useRef, useState } from "react"

import { ChatComposerEditor, type ChatEditorHandle } from "~/react/composites/chat/ChatComposerEditor"
import { GifPicker, type KlipyGif } from "~/react/composites/editor/components/GifPicker"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import type { ChatType } from "~/react/shared/types"
import { SubmitButton } from "~/react/ui/SubmitButton"
import { isBlankMarkdown } from "~/richText/schema"

interface EditMessageFormProps {
  initialContent: string
  chatType: ChatType
  uploadUrl: string | null
  mentionableUsers: MentionUser[]
  mentionsEnabled?: boolean
  klipyApiKey: string | null
  onSave: (content: string, attachmentClaimId: string | null, retainedAttachmentIds: string[]) => Promise<void>
  onCancel: () => void
}

export function EditMessageForm({
  initialContent,
  chatType,
  uploadUrl,
  mentionableUsers,
  mentionsEnabled,
  klipyApiKey,
  onSave,
  onCancel,
}: EditMessageFormProps) {
  // `content` lags the live editor by DEBOUNCE_MS and only drives Save's disabled
  // state. handleSubmit re-checks `!trimmed` against the live editor content,
  // which is the authoritative empty guard.
  const [content, setContent] = useState(initialContent)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(false)
  // Fresh per-edit-session id so attachments added during this edit don't
  // collide with the parent's in-flight compose claim.
  const [claimId] = useState(() => crypto.randomUUID())
  const editorRef = useRef<ChatEditorHandle>(null)

  const handleSubmit = useCallback(
    async (next: string) => {
      const trimmed = next.trimEnd()
      if (isBlankMarkdown(next) || saving) return
      setSaving(true)
      setError(false)
      try {
        const retainedAttachmentIds = editorRef.current?.getReferencedAttachmentIds() ?? []
        await onSave(trimmed, claimId, retainedAttachmentIds)
        // Intentionally no setSaving(false) on success: parent unmounts this
        // form when it clears editingMessageId, and flipping back to !saving
        // briefly would re-enable Save and allow a double-submit on slow networks.
      } catch {
        setError(true)
        setSaving(false)
      }
    },
    [onSave, saving, claimId]
  )

  const handleSend = useCallback((c: string) => void handleSubmit(c), [handleSubmit])

  const handleSelectGif = useCallback((gif: KlipyGif) => {
    editorRef.current?.insertImage(gif.content_url, gif.title)
  }, [])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        e.preventDefault()
        onCancel()
      }
    },
    [onCancel]
  )

  const handleFormSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    editorRef.current?.send()
  }, [])

  return (
    <div className="rounded-xl border border-neutral bg-base-300 p-1" onKeyDown={handleKeyDown}>
      <form onSubmit={handleFormSubmit} className="block rounded-xl w-full">
        <div className="px-3 pt-1">
          {error && <div className="text-xs text-error mb-1">Failed to save. Try again.</div>}
          <ChatComposerEditor
            ref={editorRef}
            onSend={handleSend}
            onChange={setContent}
            onEditPrevious={() => false}
            chatType={chatType}
            uploadUrl={uploadUrl}
            mentionableUsers={mentionableUsers}
            mentionsEnabled={mentionsEnabled}
            claimId={claimId}
            initialContent={initialContent}
            autoFocus
          />
        </div>
        <div className="mt-2 flex items-center gap-1 px-1">
          {uploadUrl && (
            <button
              type="button"
              className="btn btn-sm btn-ghost btn-square"
              onClick={() => editorRef.current?.triggerUpload()}
              aria-label="Attach file"
            >
              <span className="material-symbols-outlined text-lg">attach_file</span>
            </button>
          )}
          {klipyApiKey && (
            <GifPicker klipyApiKey={klipyApiKey} onSelectGif={handleSelectGif} buttonClassName="btn-sm" />
          )}
          <div className="ml-auto flex gap-1">
            <button type="button" onClick={onCancel} className="btn btn-ghost sm:btn-sm" disabled={saving}>
              Cancel
            </button>
            <SubmitButton className="btn sm:btn-sm" submitting={saving} disabled={isBlankMarkdown(content)}>
              Save
            </SubmitButton>
          </div>
        </div>
      </form>
    </div>
  )
}
