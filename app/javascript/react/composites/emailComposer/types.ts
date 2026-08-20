import { z } from "zod"

export type EnvelopeField = "to" | "cc" | "bcc" | "subject"

export const attachmentResponseSchema = z.object({
  id: z.string(),
  filename: z.string(),
  content_type: z.string().nullable(),
  is_inline: z.boolean(),
  download_url: z.string(),
})
export type AttachmentResponse = z.infer<typeof attachmentResponseSchema>

export interface EmailEnvelope {
  to: string[]
  cc: string[]
  bcc: string[]
  subject: string
  inReplyToId: string | null
}

export const snoozePresetSchema = z.object({
  value: z.string(),
  description: z.string(),
})
export type SnoozePreset = z.infer<typeof snoozePresetSchema>

export interface ComposerCurrentUser {
  id: string
  displayName: string
  picture: string | null | undefined
}

// The triage options a send was invoked with (archive-on-send, snooze-on-send).
// Passed to resolveSendDestination so the host can drop the archived/snoozed entry
// from its mailbox list cache before advancing. Also drives useSender's `send`.
export interface SendOptions {
  archive?: boolean
  snooze?: boolean
  snoozedUntil?: string | null
}

// Snake_case wire schema for GET /api/email_threads/{id}/composer. Consumers
// validate the server response against this, then normalize it to the
// camelCase EmailComposerProps interface in one pass (matching the convention
// documented in docs/plans/archive/2026-04-29-main-nav-react-migration.md).
export const composerWireSchema = z.object({
  thread_id: z.string(),
  draft_message_id: z.string(),
  current_user: z.object({
    id: z.string(),
    display_name: z.string(),
    picture: z.string().nullish(),
  }),
  upload_url: z.string(),
  attachments_base_url: z.string(),
  patch_url: z.string(),
  send_url: z.string(),
  schedule_url: z.string(),
  unschedule_url: z.string(),
  delete_url: z.string(),
  draft_url: z.string(),
  initial_envelope: z.object({
    to: z.array(z.string()),
    cc: z.array(z.string()),
    bcc: z.array(z.string()),
    subject: z.string(),
    in_reply_to_id: z.string().nullable(),
    attachments: z.array(attachmentResponseSchema),
    sendable_by: z.string(),
    can_reply: z.boolean(),
    cannot_send_reason: z.string().nullable(),
    is_scheduled: z.boolean(),
    scheduled_for: z.string().nullable(),
    // Persisted rendered body HTML, present once scheduled/sent. Nullish so older
    // payloads and envelope-only fixtures still parse.
    body_html: z.string().nullish(),
  }),
  is_shared_draft: z.boolean(),
  mailbox_index_url: z.string(),
  default_snooze_times: z.array(snoozePresetSchema),
})
export type ComposerWireResponse = z.infer<typeof composerWireSchema>

export interface EmailComposerProps {
  threadId: string
  draftMessageId: string
  currentUser: ComposerCurrentUser
  uploadUrl: string
  attachmentsBaseUrl: string
  patchUrl: string
  sendUrl: string
  scheduleUrl: string
  unscheduleUrl: string
  deleteUrl: string
  draftUrl: string
  initialEnvelope: EmailEnvelope
  initialAttachments: AttachmentResponse[]
  initialSendableBy: string
  initialCanReply: boolean
  initialCannotSendReason: string | null
  initialScheduledFor: string | null
  // Rendered body HTML of an already-scheduled draft, for the read-only preview.
  // Null for an editable draft (its live body lives in the collaborative doc).
  initialScheduledHtml: string | null
  isSharedDraft: boolean
  mailboxIndexUrl: string
  defaultSnoozeTimes: SnoozePreset[]
  // focusBody comes from the bootstrap data-props, not the server response —
  // different mount paths (initial SSR vs. bridge-fetched post-DRAFT_STARTED)
  // want different defaults.
  focusBody: boolean
  // After a successful send, resolve the next mailbox entry to advance to — the
  // "progress to next message" behavior. Injected by the email-thread surface,
  // which owns the mailbox navigation; the reusable composer stays list-agnostic.
  // Returns null (no next entry / no navigable list) so the send falls back to
  // mailboxIndexUrl. Absent entirely on surfaces without mailbox navigation.
  resolveSendDestination?: (options: SendOptions) => Promise<string | null>
}

export const draftBroadcastEnvelopeSchema = z.object({
  to: z.array(z.string()).optional(),
  cc: z.array(z.string()).optional(),
  bcc: z.array(z.string()).optional(),
  subject: z.string().optional(),
  in_reply_to_id: z.string().nullable().optional(),
})
export type DraftBroadcastEnvelope = z.infer<typeof draftBroadcastEnvelopeSchema>

export const assignmentChangedPayloadSchema = z.object({
  sendable_by: z.string().optional(),
  can_reply: z.boolean().optional(),
  cannot_send_reason: z.string().nullable().optional(),
})
export type AssignmentChangedPayload = z.infer<typeof assignmentChangedPayloadSchema>
