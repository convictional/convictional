import { useCallback, useEffect, useRef, type KeyboardEvent, type PointerEvent } from "react"

import { StatusPie } from "~/react/composites/goals/StatusPie"

interface ProgressRingSliderProps {
  // 0..1 when tracked (0 is a real tracked 0%), null when untracked.
  value: number | null
  onChange: (value: number | null) => void
}

const STEP = 0.05

export function ProgressRingSlider({ value, onChange }: ProgressRingSliderProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const draggingRef = useRef(false)

  const tracked = value != null
  const fraction = value == null ? 0 : Math.min(1, Math.max(0, value))
  const percent = Math.round(fraction * 100)

  // Dragging always lands on 0%–100% — 0% sits at the very left, the same spot the untracked disc
  // rests, so engaging tracking never makes the handle jump. Untracking is an explicit action.
  const setFromClientX = useCallback(
    (clientX: number) => {
      const el = trackRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const ratio = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
      onChange(Math.round(ratio * 100) / 100)
    },
    [onChange]
  )

  // Track move/release on the window, not the element, so a release is always caught even when the
  // pointer ends up off the track (e.g. dragged past either end). draggingRef gates the move.
  useEffect(() => {
    const onMove = (e: globalThis.PointerEvent) => {
      if (draggingRef.current) setFromClientX(e.clientX)
    }
    const onUp = () => {
      draggingRef.current = false
    }
    window.addEventListener("pointermove", onMove)
    window.addEventListener("pointerup", onUp)
    window.addEventListener("pointercancel", onUp)
    return () => {
      window.removeEventListener("pointermove", onMove)
      window.removeEventListener("pointerup", onUp)
      window.removeEventListener("pointercancel", onUp)
    }
  }, [setFromClientX])

  const handlePointerDown = (e: PointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    e.stopPropagation()
    draggingRef.current = true
    setFromClientX(e.clientX)
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowUp") {
      e.preventDefault()
      // First step off untracked enters tracking at a real 0%.
      onChange(value == null ? 0 : Math.min(1, value + STEP))
    } else if (e.key === "ArrowLeft" || e.key === "ArrowDown") {
      e.preventDefault()
      // Stepping left off 0% clears to untracked.
      if (value == null || value === 0) onChange(null)
      else onChange(Math.max(0, value - STEP))
    } else if (e.key === "Home") {
      e.preventDefault()
      onChange(null)
    } else if (e.key === "End") {
      e.preventDefault()
      onChange(1)
    }
  }

  return (
    <div className="flex items-center gap-2 flex-1">
      {/* mx-3 insets the rail so the handle is fully visible at both 0% and 100%. */}
      <div
        ref={trackRef}
        className={`relative mx-3 flex-1 h-6 flex items-center select-none touch-none ${tracked ? "cursor-pointer" : "cursor-default"}`}
        onPointerDown={tracked ? handlePointerDown : undefined}
      >
        {/* Rail + fill exist only when tracking; untracked shows just the disc. */}
        {tracked && (
          <>
            <div className="absolute inset-x-0 top-1/2 -translate-y-1/2 h-1.5 rounded-full bg-base-200" />
            <div
              className="absolute left-0 top-1/2 -translate-y-1/2 h-1.5 rounded-full bg-base-content/40"
              style={{ width: `${percent}%` }}
            />
          </>
        )}
        {/* Handle = the ring. 0% and untracked share the far-left position, so flipping between them
            never moves the handle. */}
        <div
          role="slider"
          tabIndex={0}
          aria-label="Progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={tracked ? percent : undefined}
          aria-valuetext={tracked ? `${percent}%` : "Not tracked"}
          onKeyDown={handleKeyDown}
          onPointerDown={handlePointerDown}
          className="absolute top-1/2 flex h-6 w-6 -translate-x-1/2 -translate-y-1/2 cursor-grab items-center justify-center rounded-full outline-none active:cursor-grabbing focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-1"
          style={{ left: `${fraction * 100}%` }}
        >
          {tracked ? (
            <span className="inline-flex items-center justify-center rounded-full border border-base-content/20 bg-base-100 p-0.5 shadow-sm">
              <StatusPie progress={value} size={18} tooltipContent={`${percent}% complete`} />
            </span>
          ) : (
            <StatusPie
              progress={value}
              size={24}
              tooltipContent={
                <>
                  <div className="font-medium">Track progress</div>
                  <div className="mt-0.5 opacity-70">Drag right to set how far along</div>
                </>
              }
            />
          )}
        </div>
      </div>
      {tracked && (
        <div className="flex items-center gap-1 shrink-0">
          <span className="text-xs text-base-500 w-9 text-right">{percent}%</span>
          <button
            type="button"
            onClick={() => onChange(null)}
            aria-label="Stop tracking progress"
            className="flex items-center text-base-content/30 hover:text-base-content/60 transition-colors"
          >
            <span className="material-symbols-outlined" style={{ fontSize: "16px" }}>
              close
            </span>
          </button>
        </div>
      )}
    </div>
  )
}
