import { useEffect, useRef, useState } from "react"
import { useStore } from "zustand"

import { ApiError, apiFetch } from "~/react/shared/apiFetch"
import { feedbackDialogStore } from "~/react/shared/stores/feedbackDialog"
import { Dialog } from "~/react/ui/Dialog"
import { isBlankMarkdown } from "~/richText/schema"
import { FeedbackEditor, type FeedbackEditorHandle } from "./FeedbackEditor"
import { captureFeedback } from "./sentry"

export interface FeedbackDialogProps {
  uploadUrl: string | null
}

interface FeedbackPayload {
  description: string
  attachment_claim_id: string | null
  sentry_event_id: string | null
  current_url: string | null
}

const SUBMIT_URL = "/api/feedback"
const SPINNER_DELAY_MS = 250
const TITLE_ID = "feedback-dialog-title"

export function FeedbackDialog({ uploadUrl }: FeedbackDialogProps) {
  const isOpen = useStore(feedbackDialogStore, s => s.isOpen)
  const close = useStore(feedbackDialogStore, s => s.close)

  const editorRef = useRef<FeedbackEditorHandle>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showSpinner, setShowSpinner] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isEmpty, setIsEmpty] = useState(true)
  // Synchronous re-entry guard: `useState` reads stale closure values on
  // synchronous click bursts; the ref mutates immediately so subsequent
  // calls within the same task see it set.
  const isSubmittingRef = useRef(false)

  // FeedbackEditorHandle is not an HTMLElement, so we can't pass editorRef to
  // Dialog's initialFocus. Focus the editor imperatively once it has mounted.
  useEffect(() => {
    if (isOpen) editorRef.current?.focus()
  }, [isOpen])

  useEffect(() => {
    if (isOpen) return
    setError(null)
    setIsSubmitting(false)
    isSubmittingRef.current = false
    setShowSpinner(false)
    setIsEmpty(true)
  }, [isOpen])

  useEffect(() => {
    if (!isSubmitting) {
      setShowSpinner(false)
      return
    }
    const id = window.setTimeout(() => setShowSpinner(true), SPINNER_DELAY_MS)
    return () => window.clearTimeout(id)
  }, [isSubmitting])

  async function handleSubmit() {
    if (isSubmittingRef.current) return

    const editor = editorRef.current
    if (!editor || editor.isEmpty()) {
      setError("Please describe your feedback before submitting.")
      return
    }

    isSubmittingRef.current = true
    const description = editor.getContent()
    setError(null)
    setIsSubmitting(true)

    const result = await captureFeedback({
      message: description,
      url: window.location.href,
    })
    const sentryEventId = result.success ? (result.eventId ?? null) : null

    const payload: FeedbackPayload = {
      description,
      attachment_claim_id: editor.attachmentClaimId,
      sentry_event_id: sentryEventId,
      current_url: window.location.href,
    }

    try {
      await apiFetch<void>(SUBMIT_URL, {
        method: "POST",
        body: JSON.stringify(payload),
      })
      close()
    } catch (err) {
      const fallback =
        err instanceof ApiError && err.status >= 500
          ? "Something went wrong on our end. Please try again."
          : "We couldn't send your feedback. Please try again."
      setError(fallback)
    } finally {
      isSubmittingRef.current = false
      setIsSubmitting(false)
    }
  }

  const submitDisabled = isSubmitting || isEmpty

  return (
    <Dialog
      isOpen={isOpen}
      onClose={close}
      labelledBy={TITLE_ID}
      testId="feedback-dialog"
      className="floating-card w-11/12 max-w-xl"
    >
      <div id="feedback-form">
        <div>
          <h3 id={TITLE_ID} className="font-semibold">
            Feedback
          </h3>
          <p className="text-sm opacity-50">
            We&apos;ll record your email address and the page you&apos;re currently on so you can focus on your
            feedback.
          </p>
        </div>
        <div className="relative w-full gap-4 mt-4">
          <div className="w-full flex flex-col gap-4 mt-4">
            <div className="pb-2 relative">
              {/* Lazy: the dialog mounts on every authenticated page, so defer
                  ProseMirror EditorView construction until the form opens. */}
              {isOpen && (
                <FeedbackEditor
                  ref={editorRef}
                  uploadUrl={uploadUrl}
                  onChange={markdown => setIsEmpty(isBlankMarkdown(markdown))}
                />
              )}
            </div>
            {error && (
              <div role="alert" data-testid="feedback-dialog-error" className="alert alert-error text-sm">
                {error}
              </div>
            )}
            <div className="w-full flex px-2 justify-between">
              <p className="flex items-center gap-1 text-xs">
                <span className="material-symbols-outlined text-sm">markdown</span>
                Markdown is supported
              </p>
              <div className="flex items-center gap-4">
                <button type="button" className="btn justify-self-end" onClick={() => close()} disabled={isSubmitting}>
                  Cancel
                </button>
                <button
                  type="button"
                  data-testid="feedback-dialog-submit"
                  className={`btn btn-primary ${submitDisabled ? "cursor-not-allowed btn-disabled" : ""} ${
                    showSpinner ? "loading loading-sm loading-spinner" : ""
                  }`}
                  onClick={handleSubmit}
                  disabled={submitDisabled}
                  aria-busy={isSubmitting}
                >
                  Submit
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Dialog>
  )
}
