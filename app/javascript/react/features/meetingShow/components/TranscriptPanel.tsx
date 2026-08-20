import { useEffect, useMemo, useRef } from "react"

import { LoadingState } from "~/react/ui/LoadingState"

import { formatTimestamp } from "../formatTimestamp"
import type { TranscriptStatus } from "../hooks/useTranscript"
import type { TranscriptLine } from "../types"

interface TranscriptPanelProps {
  status: TranscriptStatus
  currentTime: number
  hasRecording: boolean
  onSeek: (seconds: number) => void
}

export function TranscriptPanel({ status, currentTime, hasRecording, onSeek }: TranscriptPanelProps) {
  // Blank lines are an artifact of the default transcript parser, which keeps
  // the empty lines that separate speaker turns in the raw text. They carry no
  // content, so drop them rather than render empty bordered rows.
  const loadedLines = status.kind === "loaded" ? status.lines : null
  const visibleLines = useMemo(() => loadedLines?.filter(line => line.content.trim() !== "") ?? null, [loadedLines])
  const activeLineNumber = useMemo(() => findActiveLineNumber(visibleLines, currentTime), [visibleLines, currentTime])

  const containerRef = useRef<HTMLDivElement | null>(null)
  const previousActiveRef = useRef<number | null>(null)
  useEffect(() => {
    if (activeLineNumber === previousActiveRef.current) return
    previousActiveRef.current = activeLineNumber
    if (activeLineNumber === null) return
    const container = containerRef.current
    if (!container) return
    // rAF defers the read of offsetTop until after the active-line className
    // change has been committed, so we measure the post-paint position.
    requestAnimationFrame(() => {
      const lineEl = container.querySelector<HTMLDivElement>(`[data-line-number="${activeLineNumber}"]`)
      if (!lineEl) return
      const containerTop = container.getBoundingClientRect().top
      container.scrollTop = lineEl.offsetTop - containerTop
    })
  }, [activeLineNumber])

  if (status.kind === "processing") {
    // "processing" is only reached when a bot/upload job is still working (see
    // useTranscript), so the caption uses bot-present wording rather than the
    // bare spinner.
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-8">
        <span className="loading loading-ring loading-lg" />
        <p className="text-sm text-base-500">Waiting for transcript from Convictional recording bot.</p>
      </div>
    )
  }

  if (status.kind === "loading") {
    return <LoadingState className="py-8" />
  }

  if (!visibleLines || visibleLines.length === 0) {
    return <p className="text-sm text-base-500 p-2">No transcript available.</p>
  }

  return (
    <div ref={containerRef} className="text-xs text-start scroll-smooth flex flex-col h-full overflow-y-auto">
      <div className="flex-1 space-y-1">
        {visibleLines.map(line => (
          <TranscriptLineRow
            key={line.line_number}
            line={line}
            active={line.line_number === activeLineNumber}
            seekable={hasRecording}
            onSeek={onSeek}
          />
        ))}
      </div>
    </div>
  )
}

interface TranscriptLineRowProps {
  line: TranscriptLine
  active: boolean
  seekable: boolean
  onSeek: (seconds: number) => void
}

function TranscriptLineRow({ line, active, seekable, onSeek }: TranscriptLineRowProps) {
  // Round to whole seconds so the seek target and the active-line comparison
  // agree.
  const startTime = line.start_time === null ? 0 : Math.round(line.start_time)
  return (
    <div data-line-number={line.line_number}>
      <div
        className={`flex items-start gap-1 p-2 rounded-md border ${
          active ? "bg-base-300 border-neutral" : "bg-base-100 border-base-100"
        }`}
      >
        {seekable && line.start_time !== null && (
          <button
            type="button"
            className="cursor-pointer"
            onClick={() => onSeek(startTime)}
            aria-label={`Play from ${formatTimestamp(startTime)}`}
          >
            <span className="material-symbols-outlined text-base-400 hover:text-base-500 transition-colors">
              play_circle
            </span>
          </button>
        )}
        <p>
          {line.speaker && <span className="font-semibold mr-1">{line.speaker}:</span>}
          {line.content}
        </p>
      </div>
    </div>
  )
}

function findActiveLineNumber(lines: TranscriptLine[] | null, currentTime: number): number | null {
  if (!lines || lines.length === 0) return null
  // Walk lines in order; the active line is the last one whose start_time
  // does not exceed the current playback second. Lines without start_time are
  // skipped — they're pre-recording metadata.
  let active: number | null = null
  for (const line of lines) {
    if (line.start_time === null) continue
    // Compare rounded start times (currentTime is already floored to whole
    // seconds by VideoPlayer).
    if (Math.round(line.start_time) <= currentTime) {
      active = line.line_number
    } else {
      break
    }
  }
  return active
}
