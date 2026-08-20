import { useEffect, useRef, useState } from "react"

import { formatTimestamp } from "../formatTimestamp"

interface CopyTimestampButtonProps {
  meetingId: string
  currentTime: number
}

// Copies a deep-link to the meeting page at the current playback second so
// attendees can share "the bit at 12:34".
export function CopyTimestampButton({ meetingId, currentTime }: CopyTimestampButtonProps) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Clear the pending "copied" reset if we unmount before it fires.
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    []
  )

  function copy() {
    const url = `${window.location.origin}/meetings/${meetingId}#timestamp-${currentTime}`
    void navigator.clipboard.writeText(url)
    setCopied(true)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setCopied(false), 1500)
  }

  return (
    <button type="button" className="btn border border-neutral" onClick={copy}>
      <span className="material-symbols-outlined text-lg">{copied ? "check" : "link"}</span>
      Copy link at {formatTimestamp(currentTime)}
    </button>
  )
}
