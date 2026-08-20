import { useState } from "react"

import { formatDateTime } from "~/react/ui/DateTime"
import { Tooltip } from "~/react/ui/Tooltip"

import type { MeetingDetail, TranscriptLine } from "../types"

interface CopyTranscriptButtonProps {
  meeting: MeetingDetail
  lines: TranscriptLine[]
}

export function CopyTranscriptButton({ meeting, lines }: CopyTranscriptButtonProps) {
  const [copied, setCopied] = useState(false)

  function handleClick(e: React.MouseEvent<HTMLButtonElement>) {
    // Stop propagation so clicking copy doesn't also activate the parent tab.
    e.stopPropagation()
    void navigator.clipboard.writeText(formatMeetingText(meeting, lines)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  return (
    <Tooltip content="Copy transcript">
      <button type="button" onClick={handleClick} aria-label="Copy transcript">
        <span className="material-symbols-outlined text-sm hover:text-primary mt-1">
          {copied ? "check" : "content_copy"}
        </span>
      </button>
    </Tooltip>
  )
}

// Mirrors the server-side Meeting.__str__ structure (title heading, optional
// scheduled-at marker, then the transcript lines) for the Audio tab's
// copy-to-clipboard. The date marker is intentionally formatted as a
// human-readable, viewer-local date — matching the date shown in the header —
// rather than the raw datetime that __str__ (and a bare ISO string) would emit.
function formatMeetingText(meeting: MeetingDetail, lines: TranscriptLine[]): string {
  let text = `# ${meeting.title ?? ""}\n\n`
  if (meeting.scheduled_at) text += `*${formatDateTime(meeting.scheduled_at, "short_month_day_year_time")}*\n\n`
  text += lines.map(line => (line.speaker ? `${line.speaker}: ${line.content}` : line.content)).join("\n") + "\n"
  return text
}
