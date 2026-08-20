import { useRef } from "react"

import type { AttachmentResponse, SnoozePreset } from "../types"
import { SendMenu } from "./SendMenu"

interface ComposerFooterProps {
  canReply: boolean
  cannotReplyTooltip: string | null
  canSend: boolean
  sending: boolean
  cannotSendReason: string
  defaultSnoozeTimes: SnoozePreset[]
  onSend: (options: { archive?: boolean; snooze?: boolean; snoozedUntil?: string }) => void
  onSchedule: (scheduledFor: string) => void
  onDelete: () => void
  onAttachFiles: (files: FileList) => void
  attachments: AttachmentResponse[]
}

export function ComposerFooter({
  canReply,
  cannotReplyTooltip,
  canSend,
  sending,
  cannotSendReason,
  defaultSnoozeTimes,
  onSend,
  onSchedule,
  onDelete,
  onAttachFiles,
}: ComposerFooterProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="p-2 flex items-center justify-between">
      <div className="flex items-center gap-1">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          className="hidden"
          accept="*/*"
          onChange={event => {
            if (event.target.files && event.target.files.length > 0) {
              onAttachFiles(event.target.files)
              event.target.value = ""
            }
          }}
        />
        <button
          type="button"
          className="btn btn-sm btn-ghost btn-square"
          aria-label="Attach file"
          onClick={() => fileInputRef.current?.click()}
        >
          <span className="material-symbols-outlined text-base">attach_file</span>
        </button>
      </div>
      <div className="flex items-center gap-2">
        <button type="button" className="btn btn-ghost btn-square" aria-label="Delete draft" onClick={onDelete}>
          <span className="material-symbols-outlined text-lg" title="Delete draft">
            delete
          </span>
        </button>
        {canReply ? (
          <SendMenu
            canSend={canSend}
            sending={sending}
            cannotSendReason={cannotSendReason}
            defaultSnoozeTimes={defaultSnoozeTimes}
            onSend={onSend}
            onSchedule={onSchedule}
          />
        ) : (
          <button
            type="button"
            className="btn btn-primary btn-disabled"
            disabled
            title={cannotReplyTooltip ?? undefined}
          >
            <span className="material-symbols-outlined text-base">send</span>
            Send
          </button>
        )}
      </div>
    </div>
  )
}
