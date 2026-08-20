import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from "react"

import { ChatComposerEditor, type ChatEditorHandle } from "~/react/composites/chat/ChatComposerEditor"
import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import { GifPicker, type KlipyGif } from "~/react/composites/editor/components/GifPicker"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"
import type { MentionUser } from "~/react/shared/hooks/useMentionableUsers"
import { Avatar } from "~/react/ui/Avatar"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { isBlankMarkdown } from "~/richText/schema"

interface CommentComposerProps {
  // Rendered as the leading avatar on desktop; hidden on the mobile pill.
  currentUser: { display_name: string; picture: string | null } | null
  mentionableUsers: MentionUser[]
  mentionsEnabled?: boolean
  uploadUrl: string
  // Resolve truthy on success (clears the draft and rotates the attachment claim
  // id) or falsy on failure (keeps the draft for a retry and surfaces the error).
  onSubmit: (content: string, attachmentClaimId: string, unfurlLinks: boolean) => Promise<unknown>
  // Slack-style "Up in an empty composer edits your last item". Returns true if
  // it entered edit mode (consuming the key), false otherwise. Defaults to
  // declining, so a surface that doesn't supply it keeps native caret movement on Up.
  onEditPrevious?: () => boolean
  placeholder?: string
  autoFocus?: boolean
  // "enter" (default): plain Enter sends. "mod-enter": only Cmd/Ctrl+Enter sends
  // and plain Enter inserts a newline. Post comments use "mod-enter"; email uses
  // the Enter default.
  submitOn?: "enter" | "mod-enter"
  // Copy shown above the composer when a submit fails. Omit when the surface
  // reports failures another way (e.g. a flash) and no inline error is wanted.
  errorText?: string
  // Optional typing-indicator hooks. onType fires on each keystroke of a
  // non-empty draft; onStopTyping fires when the draft empties or a send lands.
  // Surfaces without a typing channel (e.g. post comments) omit both.
  onType?: () => void
  onStopTyping?: () => void
  // Optional banner rendered above the editor in both layouts, e.g. a quote-reply
  // preview. Surfaces without a reply affordance leave it unset.
  replyPreview?: React.ReactNode
  // "bar": bottom-of-page composer (mobile pill + backdrop, desktop box + spacer).
  // "inline": embedded composer (e.g. inside an expanded replies thread) with no
  // page chrome.
  variant?: "bar" | "inline"
  testId?: string
}

// Focus handle for callers that need to return focus to the composer (e.g. after
// an inline edit closes). Kept to `focus` only so the editor's send/upload
// internals stay encapsulated.
export interface CommentComposerFocusHandle {
  focus: () => void
}

// Shared add-comment composer for the post and email-thread islands, so both
// comment surfaces share one send/affordance implementation rather than drifting.
// Owns the attachment claim id and rotates it after each successful send so the
// remounted editor starts on a clean namespace; a failed submit keeps the draft.
export const CommentComposer = forwardRef<CommentComposerFocusHandle, CommentComposerProps>(function CommentComposer(
  {
    currentUser,
    mentionableUsers,
    mentionsEnabled = true,
    uploadUrl,
    onSubmit,
    onEditPrevious = () => false,
    placeholder,
    autoFocus,
    submitOn,
    errorText,
    onType,
    onStopTyping,
    replyPreview,
    variant = "bar",
    testId,
  },
  ref
) {
  const isMobile = useIsMobile()
  const { clientConfig } = useCurrentUser()
  const klipyApiKey = clientConfig?.klipy_api_key ?? null
  const [claimId, setClaimId] = useState(() => crypto.randomUUID())
  // The parent's `autoFocus` governs the first mount. A rotated claimId means a
  // send just succeeded and remounted the editor (key={claimId}) — refocus it so
  // the user can keep typing.
  const [initialClaimId] = useState(claimId)
  // `content` lags the live editor by the onChange debounce; it drives the send
  // button's disabled state and the link-preview URL scan, never the payload —
  // the editor re-serializes the live doc on send.
  const [content, setContent] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [sendError, setSendError] = useState(false)
  const editorRef = useRef<ChatEditorHandle | null>(null)

  // Reads the live editor ref, so it stays valid across the key={claimId} remount
  // that follows each successful send.
  useImperativeHandle(ref, () => ({ focus: () => editorRef.current?.focus() }), [])

  const {
    composePreview,
    dismissComposePreview,
    isUrlDismissed,
    reset: resetLinkPreview,
  } = useLinkPreviewUnfurl(content)

  const handleChange = useCallback(
    (next: string) => {
      setContent(next)
      setSendError(false)
      if (next.trim()) onType?.()
      else onStopTyping?.()
    },
    [onType, onStopTyping]
  )

  const handleSend = useCallback(
    async (markdown: string) => {
      if (submitting) return
      setSubmitting(true)
      // isUrlDismissed re-scans the fresh markdown so a submit landing inside the
      // onChange debounce window can't mis-flag the unfurl decision.
      const result = await onSubmit(markdown, claimId, !isUrlDismissed(markdown))
      setSubmitting(false)
      if (result) {
        setClaimId(crypto.randomUUID())
        setContent("")
        setSendError(false)
        resetLinkPreview()
        // The editor remounts on the rotated claimId, so onChange won't fire for
        // the cleared draft — signal the stop explicitly.
        onStopTyping?.()
      } else {
        setSendError(true)
      }
    },
    [submitting, onSubmit, claimId, isUrlDismissed, resetLinkPreview, onStopTyping]
  )

  const handleSelectGif = useCallback((gif: KlipyGif) => {
    editorRef.current?.insertImage(gif.content_url, gif.title)
  }, [])

  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => editorRef.current?.uploadFiles(files),
  })

  const canSend = !submitting && !isBlankMarkdown(content)

  const editor = (
    <ChatComposerEditor
      key={claimId}
      ref={editorRef}
      autoFocus={autoFocus || claimId !== initialClaimId}
      onSend={handleSend}
      onChange={handleChange}
      onEditPrevious={onEditPrevious}
      uploadUrl={uploadUrl}
      mentionableUsers={mentionableUsers}
      mentionsEnabled={mentionsEnabled}
      claimId={claimId}
      placeholder={placeholder}
      submitOn={submitOn}
      className={
        isMobile
          ? "max-h-24 overflow-y-auto focus:outline-hidden text-sm"
          : "max-h-96 overflow-y-auto focus:outline-hidden text-sm leading-6"
      }
      handleDrops
      showDropCursor={false}
    />
  )

  const error = errorText && sendError ? <div className="text-xs text-error mb-1 px-1">{errorText}</div> : null
  const linkPreview = composePreview ? (
    <div className="mb-2">
      <LinkPreviewCard linkPreview={composePreview} onDismiss={dismissComposePreview} />
    </div>
  ) : null

  if (isMobile) {
    const inner = (
      <>
        {replyPreview}
        {error}
        {linkPreview}
        <div ref={dropzoneRef} className="relative flex items-center gap-2">
          {isDragOver && <DropzoneOverlay compact />}
          <div className="flex-1 min-w-0 flex items-center gap-0.5 bg-base-200/80 border border-base-300 rounded-3xl py-1 pl-4 pr-1.5">
            <div className="flex-1 min-w-0">{editor}</div>
            {klipyApiKey && (
              <GifPicker
                klipyApiKey={klipyApiKey}
                onSelectGif={handleSelectGif}
                naked
                buttonClassName="w-8 h-8 text-base-content/50 active:bg-base-300"
              />
            )}
            <button
              type="button"
              onClick={() => editorRef.current?.triggerUpload()}
              aria-label="Attach file"
              className="flex items-center justify-center w-8 h-8 shrink-0 rounded-full text-base-content/50 active:bg-base-300 cursor-pointer"
            >
              <span className="material-symbols-outlined text-xl">attach_file</span>
            </button>
          </div>
          <button
            type="button"
            onClick={() => editorRef.current?.send()}
            disabled={!canSend}
            aria-label="Send"
            className="flex items-center justify-center w-10 h-10 shrink-0 rounded-full bg-primary text-primary-content cursor-pointer disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-lg">arrow_upward</span>
          </button>
        </div>
      </>
    )

    if (variant === "inline") {
      return (
        <div data-testid={testId} className="relative">
          {inner}
        </div>
      )
    }
    return (
      <div data-testid={testId} className="border-t border-base-300 bg-base-100/90 backdrop-blur-xl px-3 pt-2">
        {inner}
        <div className="w-full h-2 bg-base-100/90" />
      </div>
    )
  }

  const box = (
    <div className="flex items-start gap-2 border border-neutral rounded-3xl px-2 py-1 bg-base-300">
      {currentUser && (
        <div className="shrink-0 flex h-9 items-center">
          <Avatar picture={currentUser.picture} displayName={currentUser.display_name} size="large" />
        </div>
      )}
      <div className="relative flex-1 min-w-0">
        {replyPreview}
        {error}
        {linkPreview}
        <div ref={dropzoneRef} className="relative">
          {isDragOver && <DropzoneOverlay compact />}
          <div
            className={`grid ${klipyApiKey ? "grid-cols-[1fr_auto_auto_auto]" : "grid-cols-[1fr_auto_auto]"} gap-1 items-end`}
          >
            <div className="min-w-0 self-center">{editor}</div>
            {klipyApiKey && (
              <GifPicker klipyApiKey={klipyApiKey} onSelectGif={handleSelectGif} buttonClassName="btn-ghost" />
            )}
            <button
              type="button"
              onClick={() => editorRef.current?.triggerUpload()}
              aria-label="Attach file"
              className="btn btn-square btn-ghost"
            >
              <span className="material-symbols-outlined text-lg">attach_file</span>
            </button>
            <button
              type="button"
              onClick={() => editorRef.current?.send()}
              disabled={!canSend}
              aria-label="Send"
              className="btn btn-square btn-ghost disabled:opacity-50"
            >
              <span className="material-symbols-outlined text-lg">arrow_upward</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  )

  if (variant === "inline") {
    return <div data-testid={testId}>{box}</div>
  }
  return (
    <div data-testid={testId}>
      {box}
      <div className="w-full h-4 bg-base-100" />
    </div>
  )
})
