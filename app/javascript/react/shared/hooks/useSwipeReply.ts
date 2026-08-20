import { useCallback, useEffect, useRef, useState } from "react"

import { CLICK_SUPPRESSION_MS, classifyAxis, rubberBand } from "~/react/shared/swipePhysics"

// Left-swipe-to-reply for chat messages. Sibling in spirit to the inbox's
// useSwipeGesture, but tuned for a different interaction: a single direction
// (left), springs back after committing instead of removing the row, and binds
// a NON-PASSIVE touchmove listener so it can preventDefault — React's synthetic
// touch handlers are passive, so they can't stop the page from scrolling
// vertically mid-swipe.

// Pull this far left to arm a reply; release while armed to commit.
const TRIGGER_PX = 72
// 1:1 (after damping) up to here, then soft resistance so the row can't run away.
const MAX_PULL_PX = 104
const RUBBER_BAND_FACTOR = 0.4
// The row trails the finger by this factor — a little weight so the swipe takes
// deliberate intent rather than triggering on a light brush.
const DRAG_RESISTANCE = 0.82

interface GestureState {
  startX: number
  startY: number
  tracking: boolean
  axis: "undecided" | "horizontal" | "vertical"
  offset: number
  armed: boolean
  committedAt: number
}

function initialState(): GestureState {
  return { startX: 0, startY: 0, tracking: false, axis: "undecided", offset: 0, armed: false, committedAt: 0 }
}

function vibrate(ms: number) {
  if (typeof navigator !== "undefined" && typeof navigator.vibrate === "function") {
    navigator.vibrate(ms)
  }
}

interface UseSwipeReplyArgs {
  enabled: boolean
  onReply: () => void
}

export function useSwipeReply({ enabled, onReply }: UseSwipeReplyArgs) {
  // offset (<= 0) drives the transform; armed flags that release will commit.
  // swiping disables the spring transition mid-drag.
  const [offset, setOffset] = useState(0)
  const [armed, setArmed] = useState(false)
  const [swiping, setSwiping] = useState(false)
  const state = useRef<GestureState>(initialState())

  // Refs so the listeners (bound once per node) always see current values.
  const enabledRef = useRef(enabled)
  const onReplyRef = useRef(onReply)
  useEffect(() => {
    enabledRef.current = enabled
    onReplyRef.current = onReply
  }, [enabled, onReply])

  const settle = useCallback(() => {
    const s = state.current
    s.tracking = false
    s.axis = "undecided"
    s.offset = 0
    s.armed = false
    setSwiping(false)
    setArmed(false)
    setOffset(0)
  }, [])

  const teardownRef = useRef<(() => void) | null>(null)

  // Callback ref: (re)bind native listeners whenever the node attaches. A
  // non-passive touchmove is the only way to preventDefault the vertical scroll.
  const ref = useCallback(
    (node: HTMLElement | null) => {
      teardownRef.current?.()
      teardownRef.current = null
      if (!node || !enabledRef.current) return

      const onTouchStart = (e: TouchEvent) => {
        if (e.touches.length > 1) return
        const t = e.touches[0]
        const s = state.current
        s.startX = t.clientX
        s.startY = t.clientY
        s.tracking = true
        s.axis = "undecided"
        s.offset = 0
        s.armed = false
      }

      const onTouchMove = (e: TouchEvent) => {
        const s = state.current
        if (!s.tracking || e.touches.length > 1 || s.axis === "vertical") return
        const t = e.touches[0]
        const dx = t.clientX - s.startX
        const dy = t.clientY - s.startY
        const absX = Math.abs(dx)
        const absY = Math.abs(dy)

        if (s.axis === "undecided") {
          const axis = classifyAxis(absX, absY)
          if (axis === "undecided") return
          s.axis = axis
          if (axis === "horizontal") setSwiping(true)
          else return
        }

        // Own the gesture: stop the page scrolling vertically while we swipe.
        e.preventDefault()

        // Left only (rightward drag rests at 0); damped so the row trails the finger.
        const pull = Math.max(0, -dx) * DRAG_RESISTANCE
        const distance = rubberBand(pull, MAX_PULL_PX, RUBBER_BAND_FACTOR)
        s.offset = -distance
        setOffset(-distance)

        const nowArmed = distance >= TRIGGER_PX
        if (nowArmed !== s.armed) {
          s.armed = nowArmed
          setArmed(nowArmed)
          // A tick of haptic the moment it arms so the trigger is felt, not just seen.
          if (nowArmed) vibrate(10)
        }
      }

      const onTouchEnd = () => {
        const s = state.current
        if (!s.tracking) return
        if (s.armed) {
          s.committedAt = Date.now()
          onReplyRef.current()
        }
        settle()
      }

      node.addEventListener("touchstart", onTouchStart, { passive: true })
      node.addEventListener("touchmove", onTouchMove, { passive: false })
      node.addEventListener("touchend", onTouchEnd)
      node.addEventListener("touchcancel", settle)
      teardownRef.current = () => {
        node.removeEventListener("touchstart", onTouchStart)
        node.removeEventListener("touchmove", onTouchMove)
        node.removeEventListener("touchend", onTouchEnd)
        node.removeEventListener("touchcancel", settle)
      }
    },
    [settle]
  )

  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (Date.now() - state.current.committedAt < CLICK_SUPPRESSION_MS) {
      e.preventDefault()
      e.stopPropagation()
    }
  }, [])

  const progress = Math.max(0, Math.min(1, Math.abs(offset) / TRIGGER_PX))

  return { ref, offset, progress, armed, swiping, onClickCapture }
}
