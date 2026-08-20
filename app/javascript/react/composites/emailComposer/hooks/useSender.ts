import { useCallback, useRef, useState } from "react"

import { confirm } from "~/react/composites/confirmationDialog/confirm"
import { apiFetch } from "~/react/shared/apiFetch"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { isBlankMarkdown } from "~/richText/schema"
import { EmailAddress } from "~/shared/emailAddress"
import { showFlash } from "~/shared/flash"
import type { SendOptions } from "../types"
import type { UseEnvelopeResult } from "./useEnvelope"

interface ScheduleResponse {
  scheduled_for: string
  body_html: string | null
}

export interface UseSenderResult {
  sending: boolean
  canSend: boolean
  cannotSendReason: string
  send: (options: SendOptions, bodyMarkdown: string) => Promise<void>
  schedule: (scheduledFor: string, bodyMarkdown: string) => Promise<void>
}

interface UseSenderOptions {
  sendUrl: string
  scheduleUrl: string
  canReply: boolean
  cannotSendReason: string | null
  envelope: Pick<UseEnvelopeResult, "to" | "cc" | "bcc" | "subject" | "resetDirty">
  hasAttachments: boolean
  // Where a successful send lands when there's no next entry to advance to (the
  // last thread in the list, or a brand-new compose with no navigable list): the
  // mailbox index the composer was opened from.
  mailboxIndexUrl: string
  onSendStart?: () => void
  // Called with the server's authoritative scheduled_for and rendered body after a
  // successful schedule, so the composer can switch to its read-only scheduled state.
  onScheduled?: (scheduledFor: string, bodyHtml: string | null) => void
  // Resolve the next mailbox entry to advance to after a successful send, mirroring
  // the archive/snooze advance in MailboxActionBar. Receives the send options so the
  // host can drop an archived/snoozed entry from its list cache. Returns null when
  // there's no next entry, and we fall back to mailboxIndexUrl.
  resolveSendDestination?: (options: SendOptions) => Promise<string | null>
}

function isValidList(addresses: string[]): boolean {
  return addresses.every(a => EmailAddress.isValidEmail(a))
}

export function useSender({
  sendUrl,
  scheduleUrl,
  canReply,
  cannotSendReason,
  envelope,
  hasAttachments,
  mailboxIndexUrl,
  onSendStart,
  onScheduled,
  resolveSendDestination,
}: UseSenderOptions): UseSenderResult {
  const [sending, setSending] = useState(false)
  // Synchronous gate: React state updates are async, so two same-frame calls
  // to `send` (Cmd-Enter held, or keypress racing a click) both observe
  // `sending === false` and fire duplicate POSTs.
  const sendingRef = useRef(false)

  let canSend = true
  let reason = ""

  if (!canReply) {
    canSend = false
    reason = cannotSendReason ?? "You cannot send this draft"
  } else if (envelope.to.length === 0) {
    canSend = false
    reason = "To is required"
  } else if (!isValidList(envelope.to)) {
    canSend = false
    reason = "To contains invalid email addresses"
  } else if (envelope.cc.length > 0 && !isValidList(envelope.cc)) {
    canSend = false
    reason = "Cc contains invalid email addresses"
  } else if (envelope.bcc.length > 0 && !isValidList(envelope.bcc)) {
    canSend = false
    reason = "Bcc contains invalid email addresses"
  }

  // Reading the envelope primitives (not the whole object) keeps `send`
  // referentially stable across renders, so `useKeyboardSend`'s effect doesn't
  // rebind the keydown listener every time the parent re-renders.
  const { to, cc, bcc, subject, resetDirty } = envelope

  // Shared entry for both send and schedule: claim the synchronous guard, run the
  // empty-subject/body confirm (its copy differs per action), and start the spinner.
  // Returns false when the submission should abort (already in flight, or the user
  // declined the confirm) — leaving the guard released in that case.
  const beginSubmission = useCallback(
    async (bodyMarkdown: string, confirmCopy: { title: string; message: string; confirmLabel: string }) => {
      if (sendingRef.current) return false
      // Claim the guard before awaiting the confirm dialog, otherwise a second
      // same-frame call slips past the check above while the first is suspended.
      sendingRef.current = true
      // An email with no subject and no body is almost always accidental — confirm
      // first. Attachments make an empty-text submission intentional, so skip it.
      if (!subject.trim() && isBlankMarkdown(bodyMarkdown) && !hasAttachments) {
        const confirmed = await confirm(confirmCopy)
        if (!confirmed) {
          sendingRef.current = false
          return false
        }
      }
      setSending(true)
      onSendStart?.()
      return true
    },
    [subject, hasAttachments, onSendStart]
  )

  const send = useCallback(
    async (options: SendOptions, bodyMarkdown: string) => {
      const proceed = await beginSubmission(bodyMarkdown, {
        title: "Send without subject or body?",
        message: "This email has no subject and no body. Send it anyway?",
        confirmLabel: "Send",
      })
      if (!proceed) return
      try {
        await apiFetch(sendUrl, {
          method: "POST",
          body: JSON.stringify({
            subject,
            to,
            cc,
            bcc,
            message_body: bodyMarkdown,
            should_archive: options.archive ?? false,
            should_snooze: options.snooze ?? false,
            snoozed_until: options.snoozedUntil ?? null,
          }),
        })
        // Clear unsaved-changes only after the server accepted the send, so
        // beforeunload still warns if the user retries after a failure.
        resetDirty()
        // Advance to the next entry in the originating mailbox list ("progress to
        // next message"), mirroring the archive/snooze advance. The resolver also
        // drops an archived/snoozed entry from the list cache. A failed resolution
        // must not strand the user on the sent draft, so fall back to the inbox.
        let destination = mailboxIndexUrl
        try {
          destination = (await resolveSendDestination?.(options)) ?? mailboxIndexUrl
        } catch {
          // Keep the inbox fallback.
        }
        // Navigation unmounts the composer, so the guard is never released on
        // success — only the failure path below re-opens it for a retry.
        boostedNavigate(destination)
      } catch {
        sendingRef.current = false
        setSending(false)
      }
    },
    [beginSubmission, sendUrl, to, cc, bcc, subject, resetDirty, mailboxIndexUrl, resolveSendDestination]
  )

  const schedule = useCallback(
    async (scheduledFor: string, bodyMarkdown: string) => {
      const proceed = await beginSubmission(bodyMarkdown, {
        title: "Schedule without subject or body?",
        message: "This email has no subject and no body. Schedule it anyway?",
        confirmLabel: "Schedule",
      })
      if (!proceed) return
      try {
        const response = await apiFetch<ScheduleResponse>(scheduleUrl, {
          method: "POST",
          body: JSON.stringify({
            subject,
            to,
            cc,
            bcc,
            message_body: bodyMarkdown,
            should_archive: false,
            scheduled_for: scheduledFor,
          }),
        })
        // A scheduled draft stays put (unlike a send, which navigates away); the
        // composer flips to its read-only scheduled state with the server's time.
        resetDirty()
        onScheduled?.(response.scheduled_for, response.body_html)
      } catch {
        // Leave the composer editable so the user can retry; a rejected schedule
        // (past time, beyond the 30-day horizon, already scheduled) otherwise looks
        // like a no-op since the menu has closed.
        showFlash("Couldn't schedule this draft. Please try again.")
      } finally {
        sendingRef.current = false
        setSending(false)
      }
    },
    [beginSubmission, scheduleUrl, to, cc, bcc, subject, resetDirty, onScheduled]
  )

  return { sending, canSend, cannotSendReason: reason, send, schedule }
}
