import { useEffect, useRef } from "react"
import { EmailContactsTypeahead } from "~/react/composites/EmailContactsTypeahead"
import type { UseEnvelopeResult } from "../hooks/useEnvelope"

interface EnvelopeFieldsProps {
  envelope: UseEnvelopeResult
  // Prefixed onto field IDs so multiple composers don't collide on `id="to"`, `id="subject"`, etc.
  draftMessageId: string
  useRecipientFieldToggles: boolean
  useCondensedRecipientsDisplay: boolean
}

// Focus the input with `id` when `visible` transitions false → true. Skip on
// initial mount so SSR-revealed fields (Cc/Bcc populated, reply with subject)
// don't steal focus from the body editor.
function useFocusOnReveal(visible: boolean, id: string) {
  const prevRef = useRef(visible)
  useEffect(() => {
    if (!prevRef.current && visible) {
      document.getElementById(id)?.focus()
    }
    prevRef.current = visible
  }, [visible, id])
}

export function EnvelopeFields({
  envelope,
  draftMessageId,
  useRecipientFieldToggles,
  useCondensedRecipientsDisplay,
}: EnvelopeFieldsProps) {
  const toId = `draft-${draftMessageId}-to`
  const ccId = `draft-${draftMessageId}-cc`
  const bccId = `draft-${draftMessageId}-bcc`
  const subjectId = `draft-${draftMessageId}-subject`

  useFocusOnReveal(envelope.showCc, ccId)
  useFocusOnReveal(envelope.showBcc, bccId)
  useFocusOnReveal(envelope.showSubject, subjectId)

  const showAnyToggle = useRecipientFieldToggles && (!envelope.showCc || !envelope.showBcc || !envelope.showSubject)

  return (
    <div className="p-4 pb-0 grid gap-2 @mobile:p-0 @mobile:gap-0 divide-y divide-base-300">
      <div className="flex items-center gap-2 @mobile:p-2">
        <EmailContactsTypeahead
          value={envelope.to}
          onChange={envelope.setTo}
          placeholder={useRecipientFieldToggles ? "" : "To"}
          label={useRecipientFieldToggles ? "To" : undefined}
          testId="to"
          inputId={toId}
          useCondensedDisplay={useCondensedRecipientsDisplay}
        />
        {showAnyToggle && (
          <div className="flex justify-end gap-1">
            {!envelope.showCc && (
              <button type="button" className="btn btn-sm" onClick={() => envelope.setShowCc(true)}>
                Cc
              </button>
            )}
            {!envelope.showBcc && (
              <button type="button" className="btn btn-sm" onClick={() => envelope.setShowBcc(true)}>
                Bcc
              </button>
            )}
            {!envelope.showSubject && (
              <button
                type="button"
                className="btn btn-sm btn-square btn-ghost"
                onClick={() => envelope.setShowSubject(true)}
                aria-label="Show subject"
              >
                <span className="material-symbols-outlined text-sm">subject</span>
              </button>
            )}
          </div>
        )}
      </div>

      {(envelope.showCc || !useRecipientFieldToggles) && (
        <div className="flex items-center gap-3 @mobile:p-2">
          <EmailContactsTypeahead
            value={envelope.cc}
            onChange={envelope.setCc}
            placeholder={useRecipientFieldToggles ? "" : "Cc"}
            label={useRecipientFieldToggles ? "Cc" : undefined}
            testId="cc"
            inputId={ccId}
            useCondensedDisplay={useCondensedRecipientsDisplay}
          />
          {useRecipientFieldToggles && (
            <button
              type="button"
              className="btn btn-sm btn-square btn-ghost"
              onClick={envelope.cancelCc}
              aria-label="Remove Cc field"
            >
              <span className="material-symbols-outlined text-base">delete</span>
            </button>
          )}
        </div>
      )}

      {(envelope.showBcc || !useRecipientFieldToggles) && (
        <div className="flex items-center gap-3 @mobile:p-2">
          <EmailContactsTypeahead
            value={envelope.bcc}
            onChange={envelope.setBcc}
            placeholder={useRecipientFieldToggles ? "" : "Bcc"}
            label={useRecipientFieldToggles ? "Bcc" : undefined}
            testId="bcc"
            inputId={bccId}
            useCondensedDisplay={useCondensedRecipientsDisplay}
          />
          {useRecipientFieldToggles && (
            <button
              type="button"
              className="btn btn-sm btn-square btn-ghost"
              onClick={envelope.cancelBcc}
              aria-label="Remove Bcc field"
            >
              <span className="material-symbols-outlined text-base">delete</span>
            </button>
          )}
        </div>
      )}

      {envelope.showSubject && (
        <div className="flex items-center gap-3 @mobile:p-2">
          {useRecipientFieldToggles && (
            <label className="text-xs font-medium text-base-500" htmlFor={subjectId}>
              Subject
            </label>
          )}
          <input
            id={subjectId}
            data-testid="subject"
            className="input input-sm flex-1 bg-transparent border-0 !rounded-none focus:border-primary focus:outline-none px-0"
            value={envelope.subject}
            onChange={e => envelope.setSubject(e.target.value)}
            placeholder={useRecipientFieldToggles ? "" : "Subject"}
            autoComplete="off"
          />
          {useRecipientFieldToggles && (
            <button
              type="button"
              className="btn btn-sm btn-square btn-ghost"
              onClick={() => envelope.setShowSubject(false)}
              aria-label="Hide subject"
            >
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          )}
        </div>
      )}
    </div>
  )
}
