import * as Sentry from "@sentry/browser"
import { useCallback, useMemo, useRef, useState } from "react"

import { EditorFeatureOverlays } from "~/react/composites/editor/components/EditorFeatureOverlays"
import type { ToolbarTool } from "~/react/composites/editor/components/Toolbar"
import { Toolbar } from "~/react/composites/editor/components/Toolbar"
import { Editor, EditorContent } from "~/react/composites/editor/Editor"
import { uploadFilesToView } from "~/react/composites/editor/features/useAttachments"
import { useCollaboration } from "~/react/composites/editor/features/useCollaboration"
import { useCommonFeatures } from "~/react/composites/editor/features/useCommonFeatures"
import { useViewPlugin } from "~/react/composites/editor/features/useViewPlugin"
import { useViewRef } from "~/react/composites/editor/features/useViewRef"
import { SyncStatusContent } from "~/react/composites/SyncStatus"
import { apiFetch } from "~/react/shared/apiFetch"
import { boostedNavigate } from "~/react/shared/boostedNavigate"
import { useChannelsClient } from "~/react/shared/hooks/useChannelsClient"
import { useCurrentUser } from "~/react/shared/hooks/useCurrentUser"
import { useDropzone } from "~/react/shared/hooks/useDropzone"
import { useIsMobile } from "~/react/shared/hooks/useIsMobile"
import { DropzoneOverlay } from "~/react/ui/DropzoneOverlay"
import { getCSRFToken } from "~/shared/csrf"
import { showFlash } from "~/shared/flash"
import { ChannelStream } from "~/types/channels"

import { AttachmentList } from "./components/AttachmentList"
import { ComposerFooter } from "./components/ComposerFooter"
import { EnvelopeFields } from "./components/EnvelopeFields"
import { ScheduledDraftPreview } from "./components/ScheduledDraftPreview"
import { SendableByPill } from "./components/SendableByPill"
import { useBeforeUnloadGuard } from "./hooks/useBeforeUnloadGuard"
import { useDraftBroadcast } from "./hooks/useDraftBroadcast"
import { useEnvelope } from "./hooks/useEnvelope"
import { useKeyboardSend } from "./hooks/useKeyboardSend"
import { useSender } from "./hooks/useSender"
import { serializeEditorBody } from "./serializeEditorBody"
import type { AttachmentResponse, EmailComposerProps } from "./types"

interface AttachmentListResponse {
  attachments: AttachmentResponse[]
}

// Default rich-text toolbar tools for the email composer.
const EMAIL_COMPOSER_TOOLS: readonly ToolbarTool[] = [
  "bold",
  "italic",
  "code",
  "heading",
  "quote",
  "bulletList",
  "orderedList",
  "link",
  "image",
]
const EMAIL_COMPOSER_MOBILE_TOOLS: readonly ToolbarTool[] = ["bold", "italic", "bulletList", "link"]

export function EmailComposer(props: EmailComposerProps) {
  const channelsClient = useChannelsClient()
  const isMobile = useIsMobile()
  const currentUser = useCurrentUser()
  const klipyApiKey = currentUser.clientConfig?.klipy_api_key ?? null
  const timeZone = currentUser.user?.time_zone ?? null

  const collaboration = useCollaboration({
    channelsClient,
    stream: ChannelStream.EMAIL_DRAFT,
    params: { message_id: props.draftMessageId },
    currentUser: props.currentUser,
    initialContent: null,
  })

  // Email mentions are org-wide (no collaborator split), matching the previous
  // /workspaces/collaborators/available behaviour.
  const commonFeatures = useCommonFeatures({ uploadUrl: props.uploadUrl })
  const { viewRef, plugin: viewRefPlugin } = useViewRef()
  const viewRefFeature = useMemo(() => ({ plugins: [viewRefPlugin] }), [viewRefPlugin])
  // Drives the inline richText attachment path (commonFeatures.attachments), the
  // direct analog of the old URL-insert tool — distinct from the local email
  // file-attachment tray (`attachments` state below).
  const { isDragOver, ref: dropzoneRef } = useDropzone({
    onFiles: files => uploadFilesToView(viewRef.current, commonFeatures.attachments, files),
  })

  // ProseMirror's onChange fires synchronously between keystroke and React's
  // next commit. A ref captures every keystroke; Cmd-Enter on the trailing
  // character reads the ref so the final keystroke is included in the send.
  const bodyMarkdownRef = useRef("")
  const viewPlugin = useViewPlugin({
    onChange: value => {
      bodyMarkdownRef.current = value
    },
  })

  const envelope = useEnvelope({
    patchUrl: props.patchUrl,
    initialEnvelope: props.initialEnvelope,
  })

  const [sendableBy, setSendableBy] = useState(props.initialSendableBy)
  const [canReply, setCanReply] = useState(props.initialCanReply)
  const [cannotReplyTooltip, setCannotReplyTooltip] = useState<string | null>(props.initialCannotSendReason)
  // The read-only scheduled state, or null when the draft is editable. Bundled because the
  // three fields are only ever meaningful together (a scheduled draft has all three; an
  // editable one has none), so `scheduled === null` is the single gate the render and the
  // send guards read.
  //   - `html`: the server's persisted body_html. The live editor is unmounted while
  //     scheduled, so the preview renders this through the same EmailMessageBody path as sent mail.
  //   - `envelope`: the recipients/subject the draft will send with. The preview must show
  //     exactly that — the live `envelope` can hold a passive collaborator's unsaved edits — so a
  //     schedule snapshots authoritative values. Seeded from the `envelope` hook (the single
  //     source of truth, itself seeded from props for a draft already scheduled on load); a
  //     schedule during the session overwrites it with the acting tab's values.
  const [scheduled, setScheduled] = useState<{
    for: string
    html: string | null
    envelope: { to: string[]; cc: string[]; bcc: string[]; subject: string }
  } | null>(() =>
    props.initialScheduledFor
      ? {
          for: props.initialScheduledFor,
          html: props.initialScheduledHtml,
          envelope: { to: envelope.to, cc: envelope.cc, bcc: envelope.bcc, subject: envelope.subject },
        }
      : null
  )

  const [attachments, setAttachments] = useState<AttachmentResponse[]>(props.initialAttachments)

  const sender = useSender({
    sendUrl: props.sendUrl,
    scheduleUrl: props.scheduleUrl,
    canReply,
    cannotSendReason: cannotReplyTooltip,
    envelope,
    hasAttachments: attachments.length > 0,
    mailboxIndexUrl: props.mailboxIndexUrl,
    resolveSendDestination: props.resolveSendDestination,
    onScheduled: (newScheduledFor, bodyHtml) => {
      // The acting tab scheduled with its own envelope, so the local values are authoritative.
      setScheduled({
        for: newScheduledFor,
        html: bodyHtml,
        envelope: { to: envelope.to, cc: envelope.cc, bcc: envelope.bcc, subject: envelope.subject },
      })
    },
  })

  const handleSend = useCallback(
    (options: { archive?: boolean; snooze?: boolean; snoozedUntil?: string }) => {
      void sender.send(
        { archive: options.archive, snooze: options.snooze, snoozedUntil: options.snoozedUntil ?? null },
        serializeEditorBody(viewRef.current, bodyMarkdownRef.current)
      )
    },
    [sender, viewRef]
  )

  const handleSchedule = useCallback(
    (scheduledForIso: string) => {
      void sender.schedule(scheduledForIso, serializeEditorBody(viewRef.current, bodyMarkdownRef.current))
    },
    [sender, viewRef]
  )

  const containerRef = useRef<HTMLDivElement>(null)

  useKeyboardSend({
    // A scheduled draft is read-only; containerRef is bound to its preview, so
    // Cmd+Enter must not fire a send the backend would only reject with a 409.
    canSend: sender.canSend && !scheduled,
    sending: sender.sending,
    onSend: () => handleSend({ archive: true }),
    containerRef,
  })

  useBeforeUnloadGuard(envelope.unsavedChanges)

  const refreshAttachments = useCallback(async () => {
    try {
      const response = await apiFetch<AttachmentListResponse>(props.attachmentsBaseUrl)
      setAttachments(response.attachments)
    } catch {
      // Best-effort refresh
    }
  }, [props.attachmentsBaseUrl])

  const deleteAttachment = useCallback(
    async (attachment: AttachmentResponse) => {
      try {
        await apiFetch(`${props.attachmentsBaseUrl}/${attachment.id}`, { method: "DELETE" })
        await refreshAttachments()
      } catch {
        // ApiFetch logs to Sentry; surface a flash if needed in the future
      }
    },
    [props.attachmentsBaseUrl, refreshAttachments]
  )

  const handleAttachFiles = useCallback(
    (files: FileList) => {
      // The richText attachments plugin handles inline images via paste/drag; this
      // upload path posts the same JSON endpoint and then refetches the non-inline list.
      // Raw fetch (not apiFetch) because the payload is FormData, but we still need
      // CSRF + Sentry reporting parity.
      const upload = async () => {
        const csrf = getCSRFToken()
        const headers: Record<string, string> = { Accept: "application/json" }
        if (csrf) headers["X-CSRFToken"] = csrf
        try {
          const responses = await Promise.all(
            Array.from(files).map(file => {
              const data = new FormData()
              data.append("files", file)
              data.append("inline", "false")
              return fetch(props.uploadUrl, { method: "POST", body: data, credentials: "same-origin", headers })
            })
          )
          const failed = responses.find(r => !r.ok)
          if (failed) throw new Error(`Attachment upload failed with status ${failed.status}`)
          await refreshAttachments()
        } catch (error) {
          Sentry.captureException(error)
        } finally {
          // The attach button click moved focus out of the editor; restore it
          // so the user can keep typing without re-clicking into the body.
          viewRef.current?.focus()
        }
      }
      void upload()
    },
    [props.uploadUrl, refreshAttachments, viewRef]
  )

  const handleDelete = useCallback(async () => {
    try {
      await apiFetch(props.deleteUrl, { method: "DELETE" })
    } catch {
      // Surface failures via Sentry; the row remains for the user to retry
      return
    }
    // A reply implies the thread has prior messages and will outlive the draft;
    // a new compose has only this draft, so removing it drops the thread too.
    const destination = envelope.inReplyToId ? `/email_threads/${props.threadId}` : props.mailboxIndexUrl
    boostedNavigate(destination)
  }, [props.deleteUrl, props.threadId, props.mailboxIndexUrl, envelope.inReplyToId])

  const handleUnschedule = useCallback(async () => {
    try {
      const response = await apiFetch<{
        sendable_by: string
        can_reply: boolean
        cannot_send_reason: string | null
        scheduled_for: string | null
      }>(props.unscheduleUrl, { method: "POST" })
      // A successful unschedule clears scheduled_for; keep the prior html/envelope only in the
      // unexpected case the server still reports a scheduled time, so the preview stays coherent.
      setScheduled(prev => (response.scheduled_for && prev ? { ...prev, for: response.scheduled_for } : null))
      setSendableBy(response.sendable_by)
      setCanReply(response.can_reply)
      setCannotReplyTooltip(response.cannot_send_reason)
    } catch {
      // Keep the read-only scheduled view so the user can retry; without feedback a
      // failed unschedule (already unscheduled, or a network error) looks inert.
      showFlash("Couldn't unschedule this draft. Please try again.")
    }
  }, [props.unscheduleUrl])

  const [removed, setRemoved] = useState(false)

  useDraftBroadcast({
    threadId: props.threadId,
    draftUrl: props.draftUrl,
    envelope,
    onRemoved: () => {
      setRemoved(true)
    },
    onAssignmentChanged: ({ sendableBy: newSendableBy, canReply: newCanReply, cannotSendReason }) => {
      setSendableBy(newSendableBy)
      setCanReply(newCanReply)
      setCannotReplyTooltip(cannotSendReason)
    },
    onScheduledChanged: ({ scheduledFor: newScheduledFor, bodyHtml, envelope: scheduledEnv }) => {
      setScheduled(newScheduledFor ? { for: newScheduledFor, html: bodyHtml, envelope: scheduledEnv } : null)
    },
    // The Yjs WebSocket must release before the host tears the React tree down,
    // otherwise a subsequent DRAFT_STARTED can race with the still-open socket.
    disconnectCollaboration: collaboration.disconnect,
  })

  const useRecipientFieldToggles = !isMobile
  const useCondensedRecipientsDisplay = isMobile

  if (removed) return null

  // A scheduled draft is read-only until unscheduled. Rendered before the
  // collaboration.ready gate below because the preview reads only persisted
  // state — it must not blank out while the Yjs socket connects.
  if (scheduled) {
    return (
      <ScheduledDraftPreview
        scheduledFor={scheduled.for}
        timeZone={timeZone}
        envelope={scheduled.envelope}
        bodyHtml={scheduled.html}
        attachments={attachments}
        canReply={canReply}
        cannotReplyTooltip={cannotReplyTooltip}
        isMobile={isMobile}
        onUnschedule={() => void handleUnschedule()}
        containerRef={containerRef}
      />
    )
  }

  // The editable composer mounts the collaborative editor, so it waits for the
  // Yjs socket; the read-only scheduled preview above does not.
  if (!collaboration.ready) return null

  return (
    <div data-testid="email-compose" ref={containerRef}>
      <div className="bg-base-50 rounded-xl border border-base-300 shadow-xs">
        <SendableByPill isShared={props.isSharedDraft} sendableBy={sendableBy} />

        <Editor
          features={[collaboration, viewPlugin, viewRefFeature, ...commonFeatures.features]}
          placeholder="Compose your message..."
          autoFocus={props.focusBody}
          className="w-full focus:outline-hidden rounded-none px-0 py-2 bg-transparent min-h-24"
          showDropCursor={false}
        >
          <EnvelopeFields
            envelope={envelope}
            draftMessageId={props.draftMessageId}
            useRecipientFieldToggles={useRecipientFieldToggles}
            useCondensedRecipientsDisplay={useCondensedRecipientsDisplay}
          />
          <div className="border-y border-base-300 p-2 flex items-center gap-2 flex-wrap">
            <Toolbar
              hasKlipy={klipyApiKey !== null}
              klipyApiKey={klipyApiKey}
              tools={isMobile ? EMAIL_COMPOSER_MOBILE_TOOLS : EMAIL_COMPOSER_TOOLS}
              attachments={commonFeatures.attachments}
            />
            <SyncStatusContent status={collaboration.status} docSynced={collaboration.docSynced} className="ml-auto" />
          </div>
          <div ref={dropzoneRef} data-testid="body-editor" className="relative px-4 @mobile:px-2">
            {isDragOver && <DropzoneOverlay />}
            <EditorContent />
          </div>
          <EditorFeatureOverlays bundle={commonFeatures} />
        </Editor>

        <AttachmentList attachments={attachments} onDelete={deleteAttachment} />

        <ComposerFooter
          canReply={canReply}
          cannotReplyTooltip={cannotReplyTooltip}
          canSend={sender.canSend}
          sending={sender.sending}
          cannotSendReason={sender.cannotSendReason}
          defaultSnoozeTimes={props.defaultSnoozeTimes}
          onSend={handleSend}
          onSchedule={handleSchedule}
          onDelete={handleDelete}
          onAttachFiles={handleAttachFiles}
          attachments={attachments}
        />
      </div>
    </div>
  )
}
