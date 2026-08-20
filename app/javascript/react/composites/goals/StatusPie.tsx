import type { ReactNode } from "react"

import { Tooltip } from "~/react/ui/Tooltip"

/**
 * Single ring that doubles as progress display and (via ProgressRingSlider) the input handle.
 * Two readings:
 *   - untracked (progress == null) → an indeterminate disc: grey fill, dotted hollow ring, and a
 *     chart glyph, distinct from 0%. Used both in the composer and in historical updates.
 *   - tracked → filled wedge (stroke-dasharray trick: r = size/4, strokeWidth = size/2 fills
 *     center-to-edge; dashoffset sets the filled fraction)
 */
export function StatusPie({
  progress,
  size = 14,
  tooltipContent,
  className = "",
}: {
  progress: number | null
  size?: number
  tooltipContent?: ReactNode
  className?: string
}) {
  const tracked = progress != null
  const cx = size / 2

  let mark
  if (!tracked) {
    // Dotted hollow outline — "no number here", not 0%. The gap is derived so a whole number of
    // dots fits exactly around the circumference; otherwise the pattern wraps unevenly and dots
    // collide at the seam.
    const ringR = cx - 1
    const ringCircumference = 2 * Math.PI * ringR
    const dotCount = Math.max(6, Math.round(ringCircumference / 3.5))
    const dotGap = ringCircumference / dotCount - 0.5
    mark = (
      <circle
        cx={cx}
        cy={cx}
        r={ringR}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeDasharray={`0.5 ${dotGap}`}
      />
    )
  } else {
    const clampedPercent = Math.min(100, Math.max(0, Math.round(progress * 100)))
    const r = size / 4
    const circumference = 2 * Math.PI * r
    const offset = circumference * (1 - clampedPercent / 100)
    mark = (
      <>
        {/* Background track */}
        <circle cx={cx} cy={cx} r={cx} fill="currentColor" fillOpacity={0.2} />
        {/* Progress fill */}
        <circle
          cx={cx}
          cy={cx}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={size / 2}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform={`rotate(-90 ${cx} ${cx})`}
        />
      </>
    )
  }

  const pie = (
    <span
      className={`relative inline-flex items-center justify-center shrink-0 text-base-content/40 transition-colors duration-150 hover:text-primary ${tracked ? "" : "rounded-full bg-base-200"} ${className}`}
      style={{ width: size, height: size }}
      aria-label={tracked ? `${Math.round(progress * 100)}% complete` : "Progress not tracked"}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {mark}
      </svg>
      {!tracked && (
        <span
          className="material-symbols-outlined pointer-events-none absolute inset-0 flex items-center justify-center"
          style={{ fontSize: `${Math.round(size * 0.6)}px` }}
        >
          show_chart
        </span>
      )}
    </span>
  )

  if (tooltipContent) {
    return (
      <Tooltip content={tooltipContent} placement="bottom" className="flex items-center">
        {pie}
      </Tooltip>
    )
  }
  return pie
}
