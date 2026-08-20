import { useCallback, useEffect, useRef } from "react"

import { apiFetch } from "~/react/shared/apiFetch"
import { useChannel } from "~/react/shared/hooks/useChannel"
import { useChannelsClient } from "~/react/shared/hooks/useChannelsClient"
import { ChannelEventAction, ChannelEventResource, ChannelStream } from "~/types/channels"
import { assignmentChangedPayloadSchema, draftBroadcastEnvelopeSchema, type DraftBroadcastEnvelope } from "../types"
import type { UseEnvelopeResult } from "./useEnvelope"

interface DraftEnvelopeResponse {
  to: string[]
  cc: string[]
  bcc: string[]
  subject: string
  in_reply_to_id: string | null
  sendable_by: string
  can_reply: boolean
  cannot_send_reason: string | null
  is_scheduled: boolean
  scheduled_for: string | null
  body_html: string | null
}

export interface UseDraftBroadcastOptions {
  threadId: string
  draftUrl: string
  envelope: UseEnvelopeResult
  onRemoved: () => void
  onAssignmentChanged?: (payload: { sendableBy: string; canReply: boolean; cannotSendReason: string | null }) => void
  // Fired when a collaborator schedules or unschedules the draft. The broadcast
  // carries only the action, so we refetch the envelope for the authoritative
  // scheduled_for (null once unscheduled), the persisted body, and the recipients
  // so the read-only preview shows exactly what will be sent (not local edits).
  onScheduledChanged?: (payload: {
    scheduledFor: string | null
    bodyHtml: string | null
    envelope: { to: string[]; cc: string[]; bcc: string[]; subject: string }
  }) => void
  // Called before unmount on DRAFT_REMOVED so the body Yjs WebSocket
  // releases cleanly. Effect cleanup is too late — a quick subsequent
  // DRAFT_STARTED could race the still-open socket.
  disconnectCollaboration?: () => void
}

export function useDraftBroadcast({
  threadId,
  draftUrl,
  envelope,
  onRemoved,
  onAssignmentChanged,
  onScheduledChanged,
  disconnectCollaboration,
}: UseDraftBroadcastOptions): void {
  const channelsClient = useChannelsClient()

  const applyEnvelope = useCallback(
    (incoming: DraftBroadcastEnvelope) => {
      if (incoming.to !== undefined) envelope.applyRemoteTo(incoming.to)
      if (incoming.cc !== undefined) envelope.applyRemoteCc(incoming.cc)
      if (incoming.bcc !== undefined) envelope.applyRemoteBcc(incoming.bcc)
      if (incoming.subject !== undefined) envelope.applyRemoteSubject(incoming.subject)
    },
    [envelope]
  )

  const handleEvent = useCallback(
    (action: ChannelEventAction, data: Record<string, unknown>) => {
      switch (action) {
        case ChannelEventAction.DRAFT_UPDATED: {
          const incoming = draftBroadcastEnvelopeSchema.safeParse(data.envelope)
          if (incoming.success) applyEnvelope(incoming.data)
          return
        }
        case ChannelEventAction.ASSIGNMENT_CHANGED: {
          const payload = assignmentChangedPayloadSchema.safeParse(data)
          if (!payload.success) return
          onAssignmentChanged?.({
            sendableBy: payload.data.sendable_by ?? "",
            canReply: payload.data.can_reply ?? false,
            cannotSendReason: payload.data.cannot_send_reason ?? null,
          })
          return
        }
        case ChannelEventAction.DRAFT_SCHEDULED:
        case ChannelEventAction.DRAFT_UNSCHEDULED: {
          if (!onScheduledChanged) return
          void (async () => {
            try {
              const response = await apiFetch<DraftEnvelopeResponse>(draftUrl)
              onScheduledChanged({
                scheduledFor: response.scheduled_for,
                bodyHtml: response.body_html,
                envelope: { to: response.to, cc: response.cc, bcc: response.bcc, subject: response.subject },
              })
            } catch {
              // Best-effort; the acting tab already reflects the change locally.
            }
          })()
          return
        }
        case ChannelEventAction.DRAFT_REMOVED:
          disconnectCollaboration?.()
          onRemoved()
          return
      }
    },
    [applyEnvelope, disconnectCollaboration, draftUrl, onAssignmentChanged, onScheduledChanged, onRemoved]
  )

  useChannel(
    threadId ? { stream: ChannelStream.EMAIL_THREAD_DRAFT, params: { thread_id: threadId } } : null,
    ChannelEventResource.EMAIL_DRAFT,
    handleEvent
  )

  // After a reconnect, refetch the envelope: we may have missed broadcasts
  // while disconnected. Dirty-field gating still applies via applyRemoteField.
  const draftUrlRef = useRef(draftUrl)
  const envelopeRef = useRef(envelope)
  const onAssignmentChangedRef = useRef(onAssignmentChanged)
  const onScheduledChangedRef = useRef(onScheduledChanged)
  useEffect(() => {
    draftUrlRef.current = draftUrl
    envelopeRef.current = envelope
    onAssignmentChangedRef.current = onAssignmentChanged
    onScheduledChangedRef.current = onScheduledChanged
  })

  useEffect(() => {
    if (!channelsClient) return

    const handleReconnected = async () => {
      try {
        const response = await apiFetch<DraftEnvelopeResponse>(draftUrlRef.current)
        const env = envelopeRef.current
        env.applyRemoteTo(response.to)
        env.applyRemoteCc(response.cc)
        env.applyRemoteBcc(response.bcc)
        env.applyRemoteSubject(response.subject)
        onAssignmentChangedRef.current?.({
          sendableBy: response.sendable_by,
          canReply: response.can_reply,
          cannotSendReason: response.cannot_send_reason,
        })
        // Recover a schedule/unschedule that landed while we were disconnected — the
        // scheduled-state broadcast for it was missed, so the refetch is the only signal.
        onScheduledChangedRef.current?.({
          scheduledFor: response.scheduled_for,
          bodyHtml: response.body_html,
          envelope: { to: response.to, cc: response.cc, bcc: response.bcc, subject: response.subject },
        })
      } catch {
        // Best-effort refetch; next user save will resync.
      }
    }

    channelsClient.on("reconnected", handleReconnected)
    return () => {
      channelsClient.off("reconnected", handleReconnected)
    }
  }, [channelsClient])
}
