import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { PreviewPanel } from "~/react/features/research/scheduled/components/PreviewPanel"
import { ScheduleFormFields, type FormState } from "~/react/features/research/scheduled/components/ScheduleFormFields"
import type { PreviewStatus } from "~/react/features/research/scheduled/hooks/usePreviewStream"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { useScrollLock } from "~/react/ui/hooks/useScrollLock"

import { useResearchDialog } from "./hooks/useResearchDialog"

const SUGGESTIONS: Array<{ title: string; prompt: string }> = [
  {
    title: "Catch me up on last week",
    prompt: "Catch me up on work from last week. Use bullet points, no more than 10.",
  },
  { title: "Generate my to-do list", prompt: "Generate my to-do list based on the past day." },
]

const RUN_NOW_LABELS = { idle: "Run now", running: "Running…", just_ran: "Enqueued" } as const

export function ResearchDialog() {
  const isMobile = useIsMobile()
  const { user } = useCurrentUser()
  const currentUserTimezone = user?.time_zone ?? null
  const {
    isOpen,
    body,
    mode,
    frequency,
    hour,
    dayOfWeek,
    isEditing,
    submitting,
    runState,
    error,
    preview,
    setBody,
    setFrequency,
    setHour,
    setDayOfWeek,
    toggleMode,
    close,
    submit,
    deleteSchedule,
    runNow,
    startPreview,
  } = useResearchDialog({ currentUserTimezone })
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (isOpen) textareaRef.current?.focus()
  }, [isOpen])

  useLayoutEffect(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = "60px"
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`
  }, [body])

  useScrollLock(isOpen)

  if (!isOpen) return null

  const canSubmit = body.trim().length > 0 && !submitting
  const previewBusy = preview.status === "initiating" || preview.status === "streaming"
  const canPreview = body.trim().length > 0 && !submitting && !previewBusy
  const submitLabel = isEditing ? "Save changes" : mode === "schedule" ? "Create schedule" : "Submit research"

  const formState: FormState = {
    prompt: body,
    frequency,
    hour,
    day_of_week: dayOfWeek,
  }
  const handleFormChange = (next: FormState) => {
    setFrequency(next.frequency)
    setHour(next.hour)
    setDayOfWeek(next.day_of_week)
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation()
      close()
      return
    }
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault()
      if (canSubmit) submit()
      return
    }
    if (event.key === "Tab" && panelRef.current) {
      const focusables = panelRef.current.querySelectorAll<HTMLElement>(
        'button, textarea, [href], input, select, [tabindex]:not([tabindex="-1"])'
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (event.shiftKey && active === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && active === last) {
        event.preventDefault()
        first.focus()
      }
    }
  }

  if (isMobile) {
    return (
      <MobileResearchOverlay
        isOpen={isOpen}
        close={close}
        handleKeyDown={handleKeyDown}
        panelRef={panelRef}
        mode={mode}
        textareaRef={textareaRef}
        body={body}
        setBody={setBody}
        submitting={submitting}
        submit={submit}
        canSubmit={canSubmit}
        canPreview={canPreview}
        previewBusy={previewBusy}
        runState={runState}
        submitLabel={submitLabel}
        isEditing={isEditing}
        toggleMode={toggleMode}
        deleteSchedule={deleteSchedule}
        runNow={runNow}
        startPreview={startPreview}
        error={error}
        preview={preview}
        formState={formState}
        handleFormChange={handleFormChange}
        currentUserTimezone={currentUserTimezone}
      />
    )
  }

  const formContent = (
    <form
      onSubmit={event => {
        event.preventDefault()
        submit()
      }}
      className="grid max-h-[calc(100vh-6rem)] overflow-y-auto"
      data-testid="research-dialog-form"
    >
      <div className="px-4 pt-4">
        <textarea
          ref={textareaRef}
          name="body"
          value={body}
          onChange={event => setBody(event.target.value)}
          placeholder="What would you like to research?"
          className="textarea w-full min-h-[60px] max-h-[200px] p-0 !rounded-none border-none bg-transparent resize-none focus:outline-hidden text-base leading-relaxed"
          rows={2}
          disabled={submitting}
        />
      </div>

      {mode === "schedule" && (
        <div className="px-4 pt-2 pb-1">
          <ScheduleFormFields state={formState} onChange={handleFormChange} timezone={currentUserTimezone} />
        </div>
      )}

      {mode === "schedule" && (preview.status !== "idle" || preview.text) && (
        <div className="mt-3 mx-4 bg-base-200 rounded-lg px-4 py-3">
          <PreviewPanel status={preview.status} text={preview.text} errorMessage={preview.errorMessage} />
        </div>
      )}

      {error && (
        <div className="px-4 pb-2 text-xs text-error" data-testid="research-dialog-error">
          {error}
        </div>
      )}

      <DesktopActions
        mode={mode}
        isEditing={isEditing}
        canSubmit={canSubmit}
        canPreview={canPreview}
        submitting={submitting}
        previewBusy={previewBusy}
        runState={runState}
        submitLabel={submitLabel}
        suggestions={SUGGESTIONS}
        setBody={setBody}
        textareaRef={textareaRef}
        toggleMode={toggleMode}
        deleteSchedule={deleteSchedule}
        runNow={runNow}
        startPreview={startPreview}
      />
    </form>
  )

  return createPortal(
    <div
      className="fixed inset-0 z-50"
      onKeyDown={handleKeyDown}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label="Research"
      data-testid={mode === "schedule" ? "scheduled-research-dialog" : undefined}
    >
      <div className="overlay-backdrop fixed inset-0" onClick={close} aria-hidden="true" />
      <div
        className="fixed top-20 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4 max-h-[calc(100vh-5rem)]"
        ref={panelRef}
      >
        <div className="floating-card w-full !p-0 overflow-hidden !rounded-3xl">{formContent}</div>
      </div>
    </div>,
    document.body
  )
}

// --- Mobile full-screen overlay with pill morph ---

interface MobileResearchOverlayProps {
  isOpen: boolean
  close: () => void
  handleKeyDown: (event: React.KeyboardEvent) => void
  panelRef: React.RefObject<HTMLDivElement | null>
  mode: "once" | "schedule"
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  body: string
  setBody: (v: string) => void
  submitting: boolean
  submit: () => void
  canSubmit: boolean
  canPreview: boolean
  previewBusy: boolean
  runState: keyof typeof RUN_NOW_LABELS
  submitLabel: string
  isEditing: boolean
  toggleMode: () => void
  deleteSchedule: () => void
  runNow: () => void
  startPreview: () => void
  error: string | null
  preview: { status: PreviewStatus; text: string; errorMessage: string | null }
  formState: FormState
  handleFormChange: (next: FormState) => void
  currentUserTimezone: string | null
}

function MobileResearchOverlay({
  isOpen,
  close,
  handleKeyDown,
  panelRef,
  mode,
  textareaRef,
  body,
  setBody,
  submitting,
  submit,
  canSubmit,
  canPreview,
  previewBusy,
  runState,
  submitLabel,
  isEditing,
  toggleMode,
  deleteSchedule,
  runNow,
  startPreview,
  error,
  preview,
  formState,
  handleFormChange,
  currentUserTimezone,
}: MobileResearchOverlayProps) {
  const [expanded, setExpanded] = useState(false)
  const [visible, setVisible] = useState(false)
  const closingRef = useRef(false)

  useEffect(() => {
    if (!isOpen) {
      // If close() was called externally (e.g. after submit), clean up
      if (closingRef.current) return
      const id = requestAnimationFrame(() => {
        setExpanded(false)
        setVisible(false)
      })
      return () => cancelAnimationFrame(id)
    }
    closingRef.current = false
    const id = requestAnimationFrame(() => {
      setVisible(true)
      requestAnimationFrame(() => {
        setExpanded(true)
        setTimeout(() => textareaRef.current?.focus(), 50)
      })
    })
    return () => cancelAnimationFrame(id)
  }, [isOpen, textareaRef])

  const handleClose = () => {
    if (closingRef.current) return
    closingRef.current = true
    // Notify MobileTopBar immediately so it drops the active styling
    window.dispatchEvent(new CustomEvent("research-dialog:closed"))
    setExpanded(false)
    // Wait for animation to finish, then unmount
    setTimeout(() => {
      setVisible(false)
      close()
    }, 300)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.stopPropagation()
      handleClose()
      return
    }
    handleKeyDown(event)
  }

  if (!visible) return null

  const t = "300ms var(--ease-premium)"

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex flex-col"
      onKeyDown={onKeyDown}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label="Research"
      data-testid={mode === "schedule" ? "scheduled-research-dialog" : undefined}
    >
      <div className="absolute inset-0 bg-base-100" />

      <div className="relative px-2 pt-2" style={{ marginTop: "var(--safe-area-inset-top)" }}>
        <form
          onSubmit={event => {
            event.preventDefault()
            submit()
          }}
          data-testid="research-dialog-form"
        >
          <div
            className="border bg-base-200/80 border-base-300 overflow-hidden"
            style={{
              borderRadius: "24px",
              transition: `border-radius ${t}`,
            }}
          >
            {/* Top row: icon + textarea + X, all inline */}
            <div className="flex items-start">
              {/* Icon — slides left and collapses */}
              <div
                className="shrink-0 flex items-center justify-center overflow-hidden mt-[10px]"
                style={{
                  width: expanded ? "0px" : "18px",
                  marginLeft: expanded ? "0px" : "16px",
                  marginRight: expanded ? "0px" : "12px",
                  opacity: expanded ? 0 : 1,
                  transition: `width ${t}, margin ${t}, opacity 150ms var(--ease-premium)`,
                }}
              >
                <span className="material-symbols-outlined text-lg text-base-content/50">auto_awesome</span>
              </div>

              {/* Textarea / placeholder */}
              <div className="flex-1 relative min-h-[48px]">
                {/* "Research..." placeholder — pinned to top 48px, visible when collapsed */}
                <div
                  className="absolute top-0 left-0 right-0 h-[48px] flex items-center pointer-events-none"
                  style={{
                    opacity: expanded ? 0 : 1,
                    transition: `opacity 150ms var(--ease-premium)`,
                  }}
                >
                  <span className="text-base text-base-content/50">Research...</span>
                </div>

                {/* Actual textarea — fades in, grows taller when expanded */}
                <textarea
                  ref={textareaRef}
                  name="body"
                  value={body}
                  onChange={event => setBody(event.target.value)}
                  placeholder="What would you like to research?"
                  className="w-full min-h-[36px] max-h-[200px] pt-[10px] pb-1 pr-2 border-none bg-transparent resize-none focus:outline-hidden text-base leading-relaxed"
                  style={{
                    opacity: expanded ? 1 : 0,
                    paddingLeft: expanded ? "16px" : "0px",
                    transition: `opacity 200ms var(--ease-premium) ${expanded ? "100ms" : "0ms"}, padding-left ${t}`,
                  }}
                  rows={2}
                  disabled={submitting}
                />
              </div>

              {/* X button */}
              <button
                type="button"
                onClick={handleClose}
                aria-label="Close"
                className="flex items-center justify-center p-1.5 mr-0.5 mt-1 cursor-pointer shrink-0"
              >
                <span className="relative w-8 h-8">
                  <span
                    className="material-symbols-outlined text-lg w-8 h-8 flex items-center justify-center rounded-full bg-base-content/8 text-base-content/50 absolute inset-0"
                    style={{
                      opacity: expanded ? 0 : 1,
                      transform: expanded ? "rotate(90deg) scale(0.7)" : "rotate(0deg) scale(1)",
                      transition: `opacity 250ms var(--ease-premium), transform 250ms var(--ease-premium)`,
                    }}
                  >
                    search
                  </span>
                  <span
                    className="material-symbols-outlined text-lg w-8 h-8 flex items-center justify-center rounded-full bg-base-content/8 text-base-content/50 absolute inset-0"
                    style={{
                      opacity: expanded ? 1 : 0,
                      transform: expanded ? "rotate(0deg) scale(1)" : "rotate(-90deg) scale(0.7)",
                      transition: `opacity 250ms var(--ease-premium), transform 250ms var(--ease-premium)`,
                    }}
                  >
                    close
                  </span>
                </span>
              </button>
            </div>

            {/* Expandable: schedule fields, preview, error, actions */}
            <div
              style={{
                maxHeight: expanded ? "calc(100vh - 14rem)" : "0px",
                opacity: expanded ? 1 : 0,
                transition: `max-height ${t}, opacity 200ms var(--ease-premium) ${expanded ? "100ms" : "0ms"}`,
                overflow: expanded ? "auto" : "hidden",
              }}
              ref={panelRef}
            >
              {mode === "schedule" && (
                <div className="px-4 pt-2 pb-1">
                  <ScheduleFormFields state={formState} onChange={handleFormChange} timezone={currentUserTimezone} />
                </div>
              )}

              {mode === "schedule" && (preview.status !== "idle" || preview.text) && (
                <div className="mt-3 mx-4 bg-base-200 rounded-lg px-4 py-3">
                  <PreviewPanel status={preview.status} text={preview.text} errorMessage={preview.errorMessage} />
                </div>
              )}

              {error && (
                <div className="px-4 pb-2 text-xs text-error" data-testid="research-dialog-error">
                  {error}
                </div>
              )}

              <MobileActions
                mode={mode}
                isEditing={isEditing}
                canSubmit={canSubmit}
                canPreview={canPreview}
                submitting={submitting}
                previewBusy={previewBusy}
                runState={runState}
                submitLabel={submitLabel}
                toggleMode={toggleMode}
                deleteSchedule={deleteSchedule}
                runNow={runNow}
                startPreview={startPreview}
              />
            </div>
          </div>
        </form>
      </div>
    </div>,
    document.body
  )
}

// --- Desktop action bar (unchanged from original) ---

interface DesktopActionsProps {
  mode: "once" | "schedule"
  isEditing: boolean
  canSubmit: boolean
  canPreview: boolean
  submitting: boolean
  previewBusy: boolean
  runState: keyof typeof RUN_NOW_LABELS
  submitLabel: string
  suggestions: typeof SUGGESTIONS
  setBody: (v: string) => void
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
  toggleMode: () => void
  deleteSchedule: () => void
  runNow: () => void
  startPreview: () => void
}

function DesktopActions({
  mode,
  isEditing,
  canSubmit,
  canPreview,
  submitting,
  previewBusy,
  runState,
  submitLabel,
  suggestions,
  setBody,
  textareaRef,
  toggleMode,
  deleteSchedule,
  runNow,
  startPreview,
}: DesktopActionsProps) {
  return (
    <div className={`flex items-center justify-between gap-2 px-2 pb-2 ${mode === "schedule" ? "pt-4" : "pt-1"}`}>
      <div className="flex items-center gap-1">
        {isEditing && (
          <button
            type="button"
            data-testid="scheduled-research-delete"
            onClick={async () => {
              if (await confirm({ message: "Delete this schedule?" })) deleteSchedule()
            }}
            className="py-1.5 px-3 rounded-full text-sm text-base-content/60 hover:text-base-content hover:bg-base-200 transition-colors cursor-pointer"
          >
            Delete
          </button>
        )}
        {mode === "once" &&
          suggestions.map(({ title, prompt }) => (
            <button
              key={title}
              type="button"
              onClick={() => {
                setBody(prompt)
                textareaRef.current?.focus()
              }}
              className="py-1.5 px-3 rounded-full text-sm text-base-content/50 hover:text-base-content hover:bg-base-200 transition-colors cursor-pointer"
            >
              {title}
            </button>
          ))}
      </div>
      <div className="flex items-center gap-2">
        {!isEditing && (
          <button
            type="button"
            data-testid="research-dialog-schedule-toggle"
            aria-pressed={mode === "schedule"}
            onClick={toggleMode}
            className={`py-1.5 px-3 rounded-full text-sm transition-colors cursor-pointer inline-flex items-center gap-1 ${
              mode === "schedule"
                ? "bg-base-200 text-base-content font-medium"
                : "text-base-content/70 hover:text-base-content hover:bg-base-200"
            }`}
          >
            <span className="material-symbols-outlined text-base">
              {mode === "schedule" ? "check_box" : "check_box_outline_blank"}
            </span>
            Schedule
          </button>
        )}
        {isEditing && (
          <button
            type="button"
            onClick={runNow}
            disabled={runState !== "idle"}
            data-testid="research-dialog-run-now"
            className="py-1.5 px-3 rounded-full text-sm text-base-content/60 hover:text-base-content hover:bg-base-200 transition-colors cursor-pointer disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-base-content/60"
          >
            {RUN_NOW_LABELS[runState]}
          </button>
        )}
        {mode === "schedule" && (
          <button
            type="button"
            onClick={startPreview}
            disabled={!canPreview}
            data-testid="research-dialog-preview-run"
            className="py-1.5 px-3 rounded-full text-sm text-base-content/60 hover:text-base-content hover:bg-base-200 transition-colors cursor-pointer disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-base-content/60"
          >
            {previewBusy ? "Previewing…" : "Preview"}
          </button>
        )}
        {mode === "schedule" ? (
          <button
            type="submit"
            className="btn btn-primary"
            disabled={!canSubmit}
            aria-label={submitLabel}
            data-testid="research-dialog-submit"
          >
            {submitting ? <span className="loading loading-spinner loading-xs"></span> : submitLabel}
          </button>
        ) : (
          <button
            type="submit"
            className="btn btn-circle btn-primary"
            disabled={!canSubmit}
            aria-label={submitLabel}
            data-testid="research-dialog-submit"
          >
            {submitting ? (
              <span className="loading loading-spinner loading-xs"></span>
            ) : (
              <span className="material-symbols-outlined text-lg">arrow_upward</span>
            )}
          </button>
        )}
      </div>
    </div>
  )
}

// --- Mobile action bar: no suggestions, full-width CTA, schedule toggle as a row ---

interface MobileActionsProps {
  mode: "once" | "schedule"
  isEditing: boolean
  canSubmit: boolean
  canPreview: boolean
  submitting: boolean
  previewBusy: boolean
  runState: keyof typeof RUN_NOW_LABELS
  submitLabel: string
  toggleMode: () => void
  deleteSchedule: () => void
  runNow: () => void
  startPreview: () => void
}

function MobileActions({
  mode,
  isEditing,
  canSubmit,
  canPreview,
  submitting,
  previewBusy,
  runState,
  submitLabel,
  toggleMode,
  deleteSchedule,
  runNow,
  startPreview,
}: MobileActionsProps) {
  return (
    <div className="px-4 pb-3 pt-2 space-y-3">
      {/* Schedule toggle / secondary actions */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {!isEditing && (
            <button
              type="button"
              data-testid="research-dialog-schedule-toggle"
              aria-pressed={mode === "schedule"}
              onClick={toggleMode}
              className={`py-1.5 px-3 rounded-full text-sm transition-colors cursor-pointer inline-flex items-center gap-1.5 ${
                mode === "schedule"
                  ? "bg-primary/10 text-primary font-medium"
                  : "text-base-content/50 active:text-base-content/70"
              }`}
            >
              <span className="material-symbols-outlined text-base">
                {mode === "schedule" ? "check_box" : "check_box_outline_blank"}
              </span>
              Schedule
            </button>
          )}
          {isEditing && (
            <button
              type="button"
              data-testid="scheduled-research-delete"
              onClick={async () => {
                if (await confirm({ message: "Delete this schedule?" })) deleteSchedule()
              }}
              className="py-1.5 px-3 rounded-full text-sm text-error/70 active:text-error transition-colors cursor-pointer"
            >
              Delete
            </button>
          )}
        </div>
        <div className="flex items-center gap-2">
          {isEditing && (
            <button
              type="button"
              onClick={runNow}
              disabled={runState !== "idle"}
              data-testid="research-dialog-run-now"
              className="py-1.5 px-3 rounded-full text-sm text-base-content/50 active:text-base-content/70 transition-colors cursor-pointer disabled:opacity-50"
            >
              {RUN_NOW_LABELS[runState]}
            </button>
          )}
          {mode === "schedule" && (
            <button
              type="button"
              onClick={startPreview}
              disabled={!canPreview}
              data-testid="research-dialog-preview-run"
              className="py-1.5 px-3 rounded-full text-sm text-base-content/50 active:text-base-content/70 transition-colors cursor-pointer disabled:opacity-50"
            >
              {previewBusy ? "Previewing…" : "Preview"}
            </button>
          )}
        </div>
      </div>

      {/* Full-width submit */}
      <button
        type="submit"
        className="btn btn-primary w-full rounded-full h-11 text-sm font-medium"
        disabled={!canSubmit}
        aria-label={submitLabel}
        data-testid="research-dialog-submit"
      >
        {submitting ? (
          <span className="loading loading-spinner loading-sm"></span>
        ) : (
          <>
            <span className="material-symbols-outlined text-base">
              {mode === "schedule" ? "event_repeat" : "arrow_upward"}
            </span>
            {submitLabel}
          </>
        )}
      </button>
    </div>
  )
}
