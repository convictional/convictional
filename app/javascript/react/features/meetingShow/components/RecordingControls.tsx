import { useState } from "react"

import { apiFetch, ApiError } from "~/react/shared/apiFetch"
import { Tooltip } from "~/react/ui/Tooltip"
import { showFlash } from "~/shared/flash"

import type { MeetingBotState } from "../types"

const CANCEL_HINT = "To cancel recording, do not admit the notetaker to the call."
const UNSUPPORTED_PLATFORM =
  "This meeting couldn't be recorded. Convictional supports meetings in Zoom, Google Meet, and Microsoft Teams."
const NOT_SCHEDULABLE = "This meeting couldn't be recorded because it is scheduled to start within 20 minutes."

// The no-calendar case is intentionally absent: when has_calendar_event is
// false the CalendarMismatchBanner renders directly above these controls and
// explains it (with an actionable "add it to your calendar" prompt), so a
// duplicate tooltip on the disabled button would just double-signal.
function buttonTooltip(bot: MeetingBotState, isGoogleAuthenticated: boolean): string | null {
  if (bot.will_record) return CANCEL_HINT
  // UNSUPPORTED_PLATFORM is Google-recording specific; a Microsoft user has no
  // recording backend, so don't surface it.
  if (!bot.is_supported_meeting_platform) return isGoogleAuthenticated ? UNSUPPORTED_PLATFORM : null
  if (!bot.is_schedulable) return NOT_SCHEDULABLE
  return null
}

interface RecordingControlsProps {
  meetingId: string
  bot: MeetingBotState
  isGoogleAuthenticated: boolean
  onBotUpdated: (bot: MeetingBotState) => void
}

export function RecordingControls({ meetingId, bot, isGoogleAuthenticated, onBotUpdated }: RecordingControlsProps) {
  const [submitting, setSubmitting] = useState(false)

  async function toggle() {
    if (submitting) return
    setSubmitting(true)
    try {
      const updated = await apiFetch<MeetingBotState>(`/api/meetings/${meetingId}/bot`, {
        method: "PATCH",
        body: JSON.stringify({ will_record: !bot.will_record }),
      })
      onBotUpdated(updated)
    } catch (err) {
      if (err instanceof ApiError) {
        const detail = typeof err.body?.detail === "string" ? err.body.detail : null
        showFlash(detail ?? "Could not update recording.", "error")
      } else {
        showFlash("Could not update recording.", "error")
      }
    } finally {
      setSubmitting(false)
    }
  }

  const disabled = submitting || !bot.is_schedulable || !bot.is_supported_meeting_platform || !bot.has_calendar_event
  const tooltip = buttonTooltip(bot, isGoogleAuthenticated)

  const button = (
    <button type="button" className="btn" disabled={disabled} onClick={toggle}>
      {submitting ? (
        <span className="loading loading-spinner loading-xs" />
      ) : (
        <span className="material-symbols-outlined text-lg">
          {bot.will_record ? "stop_circle" : "fiber_manual_record"}
        </span>
      )}
      {bot.will_record ? "Don't record" : "Record this meeting"}
    </button>
  )

  return (
    <div className="flex flex-col items-center gap-2">
      {tooltip ? <Tooltip content={tooltip}>{button}</Tooltip> : button}
      <p className="text-xs text-base-500 text-center">{bot.status_display}</p>
    </div>
  )
}
