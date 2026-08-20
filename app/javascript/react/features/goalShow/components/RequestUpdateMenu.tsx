import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { BottomSheet } from "~/react/ui/BottomSheet"
import { Dropdown } from "~/react/ui/Dropdown"
import { showFlash } from "~/shared/flash"

interface RequestUpdateMenuProps {
  goalId: string
  ownerName: string
}

// Header-anchored "Request update" affordance for non-owners. Resting footprint is a single
// header button; the note input only appears on demand — a dropdown on desktop, a bottom sheet
// on mobile (the house pattern, see WorkspaceAssignment).
export function RequestUpdateMenu({ goalId, ownerName }: RequestUpdateMenuProps) {
  const isMobile = useIsMobile()
  const [questionText, setQuestionText] = useState("")

  useEffect(() => {
    let cancelled = false
    apiFetch<{ question_text: string }>(`/api/goals/${goalId}/updates/latest`).then(
      data => {
        if (!cancelled && data?.question_text) setQuestionText(data.question_text)
      },
      () => {}
    )
    return () => {
      cancelled = true
    }
  }, [goalId])

  const sendRequest = useCallback(
    async (note: string) => {
      const questionToSend = note.trim() || questionText
      if (!questionToSend) return
      try {
        await apiFetch(`/api/goals/${goalId}/updates/request`, {
          method: "POST",
          body: JSON.stringify({ question_text: questionToSend }),
        })
        showFlash("Request sent.", "success")
      } catch {
        showFlash("Failed to request update. Please try again.", "error")
      }
    },
    [goalId, questionText]
  )

  const triggerLabel = `Request an update from ${ownerName}`
  const triggerClassName = "btn border border-neutral font-normal text-base-600 flex items-center gap-1"
  const triggerContent = (
    <>
      <span className="material-symbols-outlined text-[16px]">rate_review</span>
      <span>Request update</span>
    </>
  )

  const renderPanel = (close: () => void, showHeader: boolean) => (
    <RequestPanel
      ownerName={ownerName}
      questionText={questionText}
      showHeader={showHeader}
      onSend={async note => {
        await sendRequest(note)
        close()
      }}
    />
  )

  if (isMobile) {
    return (
      <MobileVariant
        triggerLabel={triggerLabel}
        triggerClassName={triggerClassName}
        triggerContent={triggerContent}
        renderPanel={close => renderPanel(close, false)}
      />
    )
  }

  return (
    <Dropdown
      placement="bottom-end"
      ariaLabel="Request an update"
      className="dropdown-card p-0 w-80 z-50"
      trigger={
        <button type="button" className={triggerClassName} aria-label={triggerLabel}>
          {triggerContent}
        </button>
      }
    >
      {({ close }) => renderPanel(close, true)}
    </Dropdown>
  )
}

function MobileVariant({
  triggerLabel,
  triggerClassName,
  triggerContent,
  renderPanel,
}: {
  triggerLabel: string
  triggerClassName: string
  triggerContent: ReactNode
  renderPanel: (close: () => void) => ReactNode
}) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" className={triggerClassName} aria-label={triggerLabel} onClick={() => setOpen(true)}>
        {triggerContent}
      </button>
      {open && (
        <BottomSheet title="Request an update" onClose={() => setOpen(false)}>
          <div className="overflow-y-auto pb-4">{renderPanel(() => setOpen(false))}</div>
        </BottomSheet>
      )}
    </>
  )
}

function RequestPanel({
  ownerName,
  questionText,
  showHeader,
  onSend,
}: {
  ownerName: string
  questionText: string
  showHeader: boolean
  onSend: (note: string) => Promise<void>
}) {
  const [note, setNote] = useState(questionText)
  const [requesting, setRequesting] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const selectedRef = useRef(false)

  // Seed the field with the question once it loads, unless the user has already typed.
  useEffect(() => {
    setNote(prev => prev || questionText)
  }, [questionText])

  // Select the prefilled question on open so typing instantly replaces it. Deferred a frame so
  // it runs after the dropdown's own focus management, and guarded to fire only once.
  useEffect(() => {
    if (selectedRef.current || !note) return
    const el = textareaRef.current
    if (!el) return
    selectedRef.current = true
    const id = requestAnimationFrame(() => {
      el.focus()
      el.select()
    })
    return () => cancelAnimationFrame(id)
  }, [note])

  const handleSend = async () => {
    if (requesting) return
    setRequesting(true)
    try {
      await onSend(note)
    } finally {
      setRequesting(false)
    }
  }

  return (
    <div className="p-3">
      {showHeader && (
        <div className="flex items-center gap-2 mb-2">
          <span className="material-symbols-outlined text-primary" style={{ fontSize: "16px" }}>
            rate_review
          </span>
          <span className="text-sm font-medium text-base-content">Request an update from {ownerName}</span>
        </div>
      )}
      <textarea
        ref={textareaRef}
        placeholder={questionText || "How's it going?"}
        value={note}
        onChange={e => setNote(e.target.value)}
        onClick={e => e.stopPropagation()}
        className="w-full min-h-24 max-h-96 overflow-y-auto focus:outline-none border border-base-300 rounded-lg px-3 py-2 bg-base-50 text-sm resize-none"
      />
      <div className="flex justify-end mt-2">
        <button
          type="button"
          onClick={handleSend}
          disabled={requesting || (!questionText && !note.trim())}
          className="btn btn-sm btn-primary"
        >
          {requesting ? "Sending..." : "Send request"}
        </button>
      </div>
    </div>
  )
}
