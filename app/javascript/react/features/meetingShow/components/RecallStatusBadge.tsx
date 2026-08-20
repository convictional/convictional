import type { MeetingBotState } from "../types"

interface RecallStatusBadgeProps {
  bot: MeetingBotState
}

type Tone = "yellow" | "green" | "red"

// A hard failure renders as plain muted text (no box, no icon) — the page shell
// already shows the videocam_off heading. Every other state renders as a
// coloured status box with an icon or spinner.
type Frame = { kind: "plain" } | { kind: "box"; tone: Tone; icon: string | null; showSpinner: boolean }

// Picks the framing from booleans + bot_status. status_display + failure_reason
// are already pre-formatted server-side, so this component never re-runs the
// conditionals — it just chooses how to frame the message. Returns null when the
// server has nothing to say.
export function RecallStatusBadge({ bot }: RecallStatusBadgeProps) {
  if (!bot.status_display) return null

  const frame = pickFrame(bot)
  const reason =
    bot.failure_reason && bot.failure_reason !== bot.status_display ? (
      <p className="text-xs opacity-80">{bot.failure_reason}</p>
    ) : null

  if (frame.kind === "plain") {
    return (
      <div className="text-sm text-base-500 space-y-1">
        <p>{bot.status_display}</p>
        {reason}
      </div>
    )
  }

  return (
    <div className={`flex items-start gap-2 p-3 rounded-md border text-sm ${TONE_CLASSES[frame.tone]}`}>
      {frame.showSpinner ? (
        <span className="loading loading-spinner loading-xs mt-0.5" />
      ) : frame.icon ? (
        <span className="material-symbols-outlined text-lg leading-none">{frame.icon}</span>
      ) : null}
      <div className="space-y-1">
        <p>{bot.status_display}</p>
        {reason}
      </div>
    </div>
  )
}

function pickFrame(bot: MeetingBotState): Frame {
  // Failure → muted plain text.
  if (bot.is_failed) return { kind: "plain" }
  // Unschedulable is terminal, not in-progress — a red box, no spinner.
  if (bot.bot_status === "unschedulable") return { kind: "box", tone: "red", icon: null, showSpinner: false }
  if (bot.is_recording_in_progress)
    return { kind: "box", tone: "red", icon: "fiber_manual_record", showSpinner: false }
  if (bot.bot_status === "scheduled") return { kind: "box", tone: "green", icon: "schedule", showSpinner: false }
  // No bot has been dispatched (status NONE): the message is informational, not
  // in-progress — either "will be recorded" (a future intent) or "cannot be
  // recorded …" (terminal). Neither warrants a spinner.
  if (bot.bot_status === "") {
    return bot.will_record
      ? { kind: "box", tone: "green", icon: "schedule", showSpinner: false }
      : { kind: "box", tone: "yellow", icon: "info", showSpinner: false }
  }
  // Processing the recording, or any other in-progress state.
  return { kind: "box", tone: "yellow", icon: null, showSpinner: true }
}

const TONE_CLASSES: Record<Tone, string> = {
  yellow: "text-yellow-700 bg-yellow-100 border-yellow-700",
  green: "text-green-700 bg-green-100 border-green-700",
  red: "text-red-700 bg-red-100 border-red-700",
}
