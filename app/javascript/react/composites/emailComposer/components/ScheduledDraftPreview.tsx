import type { RefObject } from "react"

import { EmailMessageBody } from "~/react/composites/EmailMessageBody"
import { formatScheduledFor } from "~/react/ui/DateTime"

import type { AttachmentResponse } from "../types"

interface ScheduledDraftPreviewProps {
  scheduledFor: string
  timeZone: string | null
  // The recipients/subject captured at schedule time — exactly what will be sent.
  envelope: { to: string[]; cc: string[]; bcc: string[]; subject: string }
  // The server's persisted body_html, rendered through the same path as sent mail.
  bodyHtml: string | null
  attachments: AttachmentResponse[]
  canReply: boolean
  cannotReplyTooltip: string | null
  isMobile: boolean
  onUnschedule: () => void
  // Bound so the composer's Cmd+Enter guard can target the preview container.
  containerRef: RefObject<HTMLDivElement | null>
}

// Read-only view of a scheduled draft: what will be sent, and when. The live
// editor is unmounted while scheduled, so the envelope/body/attachments render
// from persisted state. Unschedule returns it to an editable draft.
export function ScheduledDraftPreview({
  scheduledFor,
  timeZone,
  envelope,
  bodyHtml,
  attachments,
  canReply,
  cannotReplyTooltip,
  isMobile,
  onUnschedule,
  containerRef,
}: ScheduledDraftPreviewProps) {
  const previewHtml = bodyHtml?.trim() ? bodyHtml : null
  const previewAttachments = attachments.filter(a => !a.is_inline)

  return (
    <div data-testid="email-compose-scheduled" ref={containerRef}>
      <div className="bg-base-50 rounded-xl border border-base-300 shadow-xs">
        <div className="flex items-center justify-between gap-4 border-b border-base-300 p-4">
          <span className="flex items-center gap-2 text-sm">
            <span className="material-symbols-outlined text-lg">schedule_send</span>
            {formatScheduledFor(scheduledFor, timeZone)}
          </span>
          {/* Unschedule requires reply permission (backend enforces the same); a
              non-sender on a shared thread sees it disabled with the reason, mirroring
              the composer footer's send button. */}
          <button
            type="button"
            className={`btn btn-sm btn-ghost${canReply ? "" : " btn-disabled"}`}
            disabled={!canReply}
            title={canReply ? undefined : (cannotReplyTooltip ?? undefined)}
            onClick={canReply ? onUnschedule : undefined}
          >
            Unschedule
          </button>
        </div>
        <dl className="space-y-1 border-b border-base-300 px-4 py-3 text-sm">
          <div className="flex gap-2">
            <dt className="w-14 flex-shrink-0 opacity-60">To</dt>
            <dd className="min-w-0 break-words">
              {envelope.to.join(", ") || <span className="opacity-60">(no recipients)</span>}
            </dd>
          </div>
          {envelope.cc.length > 0 && (
            <div className="flex gap-2">
              <dt className="w-14 flex-shrink-0 opacity-60">Cc</dt>
              <dd className="min-w-0 break-words">{envelope.cc.join(", ")}</dd>
            </div>
          )}
          {envelope.bcc.length > 0 && (
            <div className="flex gap-2">
              <dt className="w-14 flex-shrink-0 opacity-60">Bcc</dt>
              <dd className="min-w-0 break-words">{envelope.bcc.join(", ")}</dd>
            </div>
          )}
          <div className="flex gap-2">
            <dt className="w-14 flex-shrink-0 opacity-60">Subject</dt>
            <dd className="min-w-0 break-words font-medium">
              {envelope.subject || <span className="font-normal opacity-60">(no subject)</span>}
            </dd>
          </div>
        </dl>
        <div className="px-4 py-3">
          {previewHtml ? (
            <EmailMessageBody contentHtml={previewHtml} isMobile={isMobile} isAuthored />
          ) : (
            <p className="text-sm opacity-60">(no message body)</p>
          )}
        </div>
        {previewAttachments.length > 0 && (
          <div className="px-4 pb-4">
            <h3 className="mb-2 text-sm font-medium">Attachments</h3>
            <ul className="list-disc space-y-1 pl-5">
              {previewAttachments.map(attachment => (
                <li key={attachment.id} className="max-w-96 truncate">
                  <a href={attachment.download_url} className="link" target="_blank" rel="noopener noreferrer">
                    {attachment.filename}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
