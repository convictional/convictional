import { useCallback, useMemo, useState } from "react"

import { LinkPreviewCard } from "~/react/composites/chat/LinkPreviewCard"
import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import { Toolbar, type ToolbarTool } from "~/react/composites/editor/components/Toolbar"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { uploadFilesToView } from "~/react/composites/editor/features/useAttachments"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { useEnterToSend } from "~/react/composites/editor/features/useEnterToSend"
import { useViewPlugin } from "~/react/composites/editor/features/useViewPlugin"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useLinkPreviewUnfurl } from "~/react/shared/hooks/useLinkPreviewUnfurl"
import { Avatar } from "~/react/ui/Avatar"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { isBlankMarkdown, serialize } from "~/richText/schema"

// Posts are long-form and async, so the comment composer is a document-style
// editor (Enter inserts a newline; Cmd/Ctrl+Enter submits) rather than the
// chat-style send-on-Enter bar. At rest it looks like the chat composer — a slim
// rounded bar with the author avatar — and expands to reveal a formatting
// toolbar and submit button once focused.
const POST_TOOLS: readonly ToolbarTool[] = [
  "bold",
  "italic",
  "heading",
  "quote",
  "bulletList",
  "orderedList",
  "link",
  "image",
]

// Mobile has no room for the formatting palette, so its toolbar drops to just
// the attach-file button (the "image" tool); the GIF picker renders alongside it
// on its own (gated by klipy, not this list).
const MOBILE_POST_TOOLS: readonly ToolbarTool[] = ["image"]

interface PostCommentComposerProps {
  uploadUrl: string
  // Resolves to the created comment (truthy) on success, which clears and
  // collapses the composer. A falsy/throwing result keeps the draft. The third
  // arg is false when the user dismissed the link preview, so the server skips
  // unfurling that URL.
  onSubmit: (content: string, attachmentClaimId: string, unfurlLinks: boolean) => Promise<unknown>
  autoFocus?: boolean
  placeholder?: string
}

export function PostCommentComposer({
  uploadUrl,
  onSubmit,
  autoFocus = false,
  placeholder = "Write a comment…",
}: PostCommentComposerProps) {
  const { user, clientConfig } = useCurrentUser()
  const isMobile = useIsMobile()
  const klipyApiKey = clientConfig?.klipy_api_key ?? null
  // Rotating the claim id remounts the editor with a clean doc and a fresh
  // attachment scope after a successful submit, mirroring the chat composers.
  const [claimId, setClaimId] = useState(() => crypto.randomUUID())
  const [expanded, setExpanded] = useState(autoFocus)
  // `content` lags the live editor by the onChange debounce; it drives the send
  // button's disabled state and the link-preview URL scan, never the payload —
  // the editor re-serializes the live doc on send.
  const [content, setContent] = useState("")
  const [submitting, setSubmitting] = useState(false)
  // Match the shared CommentComposer's blank check: isBlankMarkdown ignores a
  // stray <br> that a typed-then-cleared doc serializes to, which a bare trim
  // would count as content.
  const isEmpty = isBlankMarkdown(content)

  const { viewRef, plugin: viewRefPlugin } = useViewRef()
  const viewRefFeature = useMemo(() => ({ plugins: [viewRefPlugin] }), [viewRefPlugin])
  // Posts have no collaborator concept, so mentions are org-wide (no
  // collaboratorIds), matching the post body and goal-comment composers.
  const commonFeatures = useCommonFeatures({ uploadUrl, claimId })
  const viewPlugin = useViewPlugin({ onChange: setContent })

  const {
    composePreview,
    dismissComposePreview,
    isUrlDismissed,
    reset: resetLinkPreview,
  } = useLinkPreviewUnfurl(content)

  const submit = useCallback(async () => {
    const view = viewRef.current
    if (!view || submitting) return
    const markdown = serialize(view.state.doc)
    if (isBlankMarkdown(markdown)) return
    setSubmitting(true)
    try {
      // isUrlDismissed re-scans the fresh markdown so a submit landing inside the
      // onChange debounce window can't mis-flag the unfurl decision.
      const result = await onSubmit(markdown, claimId, !isUrlDismissed(markdown))
      if (result) {
        setClaimId(crypto.randomUUID())
        setContent("")
        setExpanded(false)
        resetLinkPreview()
      }
    } finally {
      setSubmitting(false)
    }
  }, [viewRef, submitting, onSubmit, claimId, isUrlDismissed, resetLinkPreview])

  // Shared hook owns the ⌘↵-to-submit keymap (plain Enter inserts a newline via
  // requireModifier) and stops the keystroke from bubbling to ancestor keydown
  // listeners. It keeps onSend current internally, and re-serializes the live
  // doc itself; we ignore its markdown and route through submit() for the
  // submitting guard, claim rotation, and link-preview reset.
  const enterToSend = useEnterToSend({ onSend: () => void submit(), requireModifier: true })

  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => uploadFilesToView(viewRef.current, commonFeatures.attachments, files),
  })

  // Focus anywhere inside the composer expands it; blurring out of it collapses
  // again only when empty. Toolbar buttons preventDefault on mousedown so they
  // never steal focus, keeping the composer open while formatting.
  const handleBlur = (event: React.FocusEvent<HTMLDivElement>) => {
    if (event.currentTarget.contains(event.relatedTarget)) return
    if (isEmpty) setExpanded(false)
  }

  return (
    <div
      ref={dropzoneRef}
      onFocus={() => setExpanded(true)}
      onBlur={handleBlur}
      className="relative rounded-3xl border border-neutral bg-base-300 px-2 py-1.5"
    >
      {isDragOver && <DropzoneOverlay compact />}
      <Editor
        key={claimId}
        features={[enterToSend, viewPlugin, viewRefFeature, ...commonFeatures.features]}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className="flex-1 focus:outline-hidden text-sm"
      >
        <div className={`flex gap-2 ${expanded ? "items-start" : "items-center"}`}>
          <div className={`shrink-0 ${expanded ? "pt-1" : ""}`}>
            <Avatar picture={user?.picture ?? null} displayName={user?.display_name ?? ""} size="large" />
          </div>
          <div className="flex-1 min-w-0">
            <div
              className={`flex flex-col ${
                expanded ? (isMobile ? "max-h-[50vh] overflow-y-auto" : "min-h-20 max-h-[50vh] overflow-y-auto") : ""
              }`}
            >
              <EditorContent />
            </div>
            {composePreview && (
              <div className="mt-2">
                <LinkPreviewCard linkPreview={composePreview} onDismiss={dismissComposePreview} />
              </div>
            )}
            {expanded && (
              <div className="mt-1 flex items-center gap-1">
                <div className="min-w-0 flex-1">
                  <Toolbar
                    hasKlipy={klipyApiKey !== null}
                    klipyApiKey={klipyApiKey}
                    tools={isMobile ? MOBILE_POST_TOOLS : POST_TOOLS}
                    attachments={commonFeatures.attachments}
                  />
                </div>
                <button
                  type="button"
                  className="btn btn-primary shrink-0"
                  disabled={isEmpty || submitting}
                  onClick={submit}
                >
                  {submitting ? <span className="loading loading-spinner loading-xs" /> : "Comment"}
                </button>
              </div>
            )}
          </div>
        </div>
        <EditorFeatureOverlays bundle={commonFeatures} />
      </Editor>
    </div>
  )
}
