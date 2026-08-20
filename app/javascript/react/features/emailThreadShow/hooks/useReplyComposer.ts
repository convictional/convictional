import { useCallback, useEffect, useRef, useState } from "react"

import {
  composerWireSchema,
  type ComposerWireResponse,
  type EmailComposerProps,
} from "~/react/composites/emailComposer/types"
import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import type { EmailThreadDraft } from "~/react/shared/types"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"

interface UseReplyComposerOptions {
  threadId: string
  initialDraft: EmailThreadDraft | null
  currentUserId: string | null
}

interface UseReplyComposerResult {
  composerProps: EmailComposerProps | null
  // Imperative mount after a successful reply/forward action. The server will
  // broadcast DRAFT_STARTED — but we mount immediately so the actor doesn't
  // wait on the round trip.
  mountAfterAction: () => void
  unmount: () => void
}

function fromWire(wire: ComposerWireResponse, focusBody: boolean): EmailComposerProps {
  return {
    threadId: wire.thread_id,
    draftMessageId: wire.draft_message_id,
    currentUser: {
      id: wire.current_user.id,
      displayName: wire.current_user.display_name,
      picture: wire.current_user.picture,
    },
    uploadUrl: wire.upload_url,
    attachmentsBaseUrl: wire.attachments_base_url,
    patchUrl: wire.patch_url,
    sendUrl: wire.send_url,
    scheduleUrl: wire.schedule_url,
    unscheduleUrl: wire.unschedule_url,
    deleteUrl: wire.delete_url,
    draftUrl: wire.draft_url,
    initialEnvelope: {
      to: wire.initial_envelope.to,
      cc: wire.initial_envelope.cc,
      bcc: wire.initial_envelope.bcc,
      subject: wire.initial_envelope.subject,
      inReplyToId: wire.initial_envelope.in_reply_to_id,
    },
    initialAttachments: wire.initial_envelope.attachments,
    initialSendableBy: wire.initial_envelope.sendable_by,
    initialCanReply: wire.initial_envelope.can_reply,
    initialCannotSendReason: wire.initial_envelope.cannot_send_reason,
    initialScheduledFor: wire.initial_envelope.scheduled_for,
    initialScheduledHtml: wire.initial_envelope.body_html ?? null,
    isSharedDraft: wire.is_shared_draft,
    mailboxIndexUrl: wire.mailbox_index_url,
    defaultSnoozeTimes: wire.default_snooze_times,
    focusBody,
  }
}

// Owns the lifecycle of the embedded EmailComposer for the email thread show
// island. Subscribes to the per-thread `email_thread_draft` channel and
// fetches the composer wire shape on DRAFT_STARTED. Skips sender-broadcasts
// for that channel (the composer owns its own draft state in the local tab).
//
// Always calls GET /api/email_threads/{id}/composer for the props — never
// /draft, which returns the envelope-only response and is not what
// EmailComposer expects.
export function useReplyComposer({
  threadId,
  initialDraft,
  currentUserId,
}: UseReplyComposerOptions): UseReplyComposerResult {
  const [composerProps, setComposerProps] = useState<EmailComposerProps | null>(null)
  // A single controller tracks the latest in-flight fetch. Rapid Reply →
  // broadcast → DRAFT_STARTED bursts would otherwise race and let an older
  // response stomp a newer one. Aborting before each call discards stale
  // responses without paying for them.
  const fetchControllerRef = useRef<AbortController | null>(null)

  const fetchComposer = useCallback(
    (focusBody: boolean) => {
      fetchControllerRef.current?.abort()
      const controller = new AbortController()
      fetchControllerRef.current = controller
      void (async () => {
        try {
          const raw = await apiFetch<unknown>(`/api/email_threads/${threadId}/composer`, { signal: controller.signal })
          if (controller.signal.aborted) return
          const wire = composerWireSchema.parse(raw)
          setComposerProps(fromWire(wire, focusBody))
        } catch {
          // apiFetch + zod log to Sentry via their own paths; abort is
          // expected and silent. Failed fetch leaves the composer unmounted;
          // the next broadcast retries.
        }
      })()
    },
    [threadId]
  )

  useEffect(() => {
    return () => {
      fetchControllerRef.current?.abort()
    }
  }, [])

  // Bootstrap from the initial show response: if a draft already exists when
  // the page loads, mount the composer immediately without waiting for a
  // broadcast. focusBody is false on bootstrap — the user navigated here, the
  // body shouldn't steal focus. Depend on the draft id (not the object
  // identity) so parent re-renders that pass an equivalent draft don't refetch.
  const initialDraftId = initialDraft?.message_id ?? null
  useEffect(() => {
    if (!initialDraftId) return
    fetchComposer(false)
  }, [initialDraftId, fetchComposer])

  const handleEvent = useCallback(
    (action: ChannelEventAction, data: Record<string, unknown>) => {
      if (action === ChannelEventAction.DRAFT_STARTED) {
        const payloadThreadId = typeof data.thread_id === "string" ? data.thread_id : null
        const payloadUserId = typeof data.user_id === "string" ? data.user_id : null
        if (payloadThreadId && payloadThreadId !== threadId) return
        // Same-user skip: the composer in the actor's tab manages its own
        // mount via mountAfterAction(); the broadcast is for other tabs.
        if (currentUserId && payloadUserId === currentUserId) return
        fetchComposer(false)
        return
      }
      if (action === ChannelEventAction.DRAFT_REMOVED) {
        const payloadUserId = typeof data.user_id === "string" ? data.user_id : null
        // Same-user skip mirrors DRAFT_STARTED. The server already filters
        // the actor's subscription (api/email_drafts.py), but a stale
        // DRAFT_REMOVED arriving after the user has started a new local
        // draft would otherwise rip the newly-mounted composer out.
        if (currentUserId && payloadUserId === currentUserId) return
        setComposerProps(null)
      }
    },
    [threadId, currentUserId, fetchComposer]
  )

  useChannel(
    threadId ? { stream: ChannelStream.EMAIL_THREAD_DRAFT, params: { thread_id: threadId } } : null,
    ChannelEventResource.EMAIL_DRAFT,
    handleEvent
  )

  const mountAfterAction = useCallback(() => {
    fetchComposer(true)
  }, [fetchComposer])

  const unmount = useCallback(() => {
    setComposerProps(null)
  }, [])

  return { composerProps, mountAfterAction, unmount }
}
