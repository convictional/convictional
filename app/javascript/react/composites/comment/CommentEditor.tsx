import { useCallback, useRef, useState } from "react"

import { ChatComposerEditor, type ChatEditorHandle } from "~/react/composites/chat/ChatComposerEditor"
import { GifPicker, type KlipyGif } from "~/react/composites/editor/components/GifPicker"
import { attachmentUploadUrl } from "~/react/shared/attachmentUrls"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { useMentionableUsers } from "~/react/shared/hooks/useMentionableUsers"
import { useWorkspaceCollaboratorIds } from "~/react/shared/hooks/useWorkspaceCollaboratorIds"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { SubmitButton } from "~/react/ui/SubmitButton"
import { isBlankMarkdown } from "~/richText/schema"

interface CommentEditorProps {
  initialContent: string
  workspaceId: string
  onSave: (content: string, attachmentClaimId: string) => Promise<unknown>
  onCancel: () => void
  // "enter" (default): Enter saves. "mod-enter": only Cmd/Ctrl+Enter saves and
  // plain Enter inserts a newline. Post comment editing uses "mod-enter"; email
  // uses the Enter default.
  submitOn?: "enter" | "mod-enter"
  // Email threads expose collaborators, so their mentions stay collaborator-split
  // (the "Collaborators" section in the dropdown). Posts have no collaborator
  // concept and mention org-wide.
  scopeMentionsToCollaborators?: boolean
}

// Shared inline edit composer for the post and email-thread islands, so both
// comment surfaces share one edit implementation. Escape or Cancel returns to
// display untouched.
export function CommentEditor({
  initialContent,
  workspaceId,
  onSave,
  onCancel,
  submitOn,
  scopeMentionsToCollaborators,
}: CommentEditorProps) {
  const { clientConfig } = useCurrentUser()
  const klipyApiKey = clientConfig?.klipy_api_key ?? null
  const uploadUrl = attachmentUploadUrl(workspaceId)
  // Passing null when unscoped skips the collaborator fetch/subscription entirely.
  const collaboratorIds = useWorkspaceCollaboratorIds(scopeMentionsToCollaborators ? workspaceId : null)
  const mentionableUsers = useMentionableUsers(scopeMentionsToCollaborators ? { collaboratorIds } : undefined)

  // `content` lags the editor by the onChange debounce and only drives Save's
  // disabled state; the send path re-serializes the live doc and no-ops on empty.
  const [content, setContent] = useState(initialContent)
  const [saving, setSaving] = useState(false)
  // Fresh per-edit-session id so attachments added during this edit don't collide
  // with the parent's in-flight compose claim.
  const [claimId] = useState(() => crypto.randomUUID())
  const editorRef = useRef<ChatEditorHandle | null>(null)

  const handleSave = useCallback(
    async (next: string) => {
      if (saving) return
      setSaving(true)
      try {
        await onSave(next, claimId)
        // No setSaving(false) on success: the parent unmounts this editor when it
        // leaves edit mode, and flipping back to !saving first would briefly
        // re-enable Save and allow a double-submit on slow networks. A rejecting
        // save re-enables below so the user can retry.
      } catch {
        setSaving(false)
      }
    },
    [saving, onSave, claimId]
  )

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

  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => editorRef.current?.uploadFiles(files),
  })

  return (
    <div
      ref={dropzoneRef}
      className="relative rounded-xl border border-neutral bg-base-300 p-1"
      onKeyDown={handleKeyDown}
    >
      {isDragOver && <DropzoneOverlay compact />}
      <form onSubmit={handleFormSubmit} className="block w-full rounded-xl">
        <div className="px-3 pt-1">
          <ChatComposerEditor
            ref={editorRef}
            autoFocus
            onSend={handleSave}
            onChange={setContent}
            onEditPrevious={() => false}
            uploadUrl={uploadUrl}
            mentionableUsers={mentionableUsers}
            claimId={claimId}
            initialContent={initialContent}
            submitOn={submitOn}
            handleDrops
            showDropCursor={false}
          />
        </div>
        <div className="mt-2 flex items-center gap-1 px-1">
          <button
            type="button"
            className="btn btn-sm btn-ghost btn-square"
            onClick={() => editorRef.current?.triggerUpload()}
            aria-label="Attach file"
          >
            <span className="material-symbols-outlined text-lg">attach_file</span>
          </button>
          {klipyApiKey && (
            <GifPicker klipyApiKey={klipyApiKey} onSelectGif={handleSelectGif} buttonClassName="btn-sm" />
          )}
          <div className="ml-auto flex gap-1">
            <button type="button" onClick={onCancel} className="btn btn-ghost btn-sm" disabled={saving}>
              Cancel
            </button>
            <SubmitButton className="btn btn-primary btn-sm" submitting={saving} disabled={isBlankMarkdown(content)}>
              Save
            </SubmitButton>
          </div>
        </div>
      </form>
    </div>
  )
}
