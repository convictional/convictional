import { useCallback, useEffect, useRef, useState } from "react"

const LONG_PRESS_THRESHOLD = 500
// Wait a beat before the press-in shrink starts so a quick tap or the start of
// a scroll doesn't twitch the element. The bubble's transition duration is set
// to LONG_PRESS_THRESHOLD minus this so the shrink still lands at the trigger.
const PRESS_FEEDBACK_DELAY = 180
// Pop the tonal highlight slightly before the trigger so the color reads as
// anticipating the toggle rather than lagging it.
const HIGHLIGHT_LEAD = 70
// Keep the highlight on briefly after firing so it carries into the overlay.
const HIGHLIGHT_HOLD = 350

export function useLongPress(onLongPress: () => void) {
  const timers = useRef<number[]>([])
  const hasFired = useRef(false)
  // isPressing drives the press-in feedback (e.g. a shrink); highlight drives a
  // tonal emphasis timed to land just before the trigger. Both are kept out of
  // the spread `handlers` object so they aren't forwarded onto the DOM element.
  const [isPressing, setIsPressing] = useState(false)
  const [highlight, setHighlight] = useState(false)

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout)
    timers.current = []
  }, [])

  const cancelPress = useCallback(() => {
    clearTimers()
    setIsPressing(false)
    setHighlight(false)
  }, [clearTimers])

  useEffect(() => clearTimers, [clearTimers])

  const onTouchStart = useCallback(() => {
    window.getSelection()?.removeAllRanges()
    hasFired.current = false
    clearTimers()
    timers.current.push(window.setTimeout(() => setIsPressing(true), PRESS_FEEDBACK_DELAY))
    timers.current.push(window.setTimeout(() => setHighlight(true), LONG_PRESS_THRESHOLD - HIGHLIGHT_LEAD))
    timers.current.push(
      window.setTimeout(() => {
        hasFired.current = true
        setIsPressing(false)
        onLongPress()
        // Let the highlight linger past the trigger; the post-fire timeout owns
        // clearing it (touchend's fired branch deliberately leaves it running).
        timers.current.push(window.setTimeout(() => setHighlight(false), HIGHLIGHT_HOLD))
      }, LONG_PRESS_THRESHOLD)
    )
  }, [onLongPress, clearTimers])

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (hasFired.current) {
        // Press already triggered: suppress the synthetic click and drop the
        // shrink, but let the lingering highlight finish on its own timer.
        e.preventDefault()
        setIsPressing(false)
        return
      }
      cancelPress()
    },
    [cancelPress]
  )

  const onTouchMove = useCallback(() => {
    cancelPress()
  }, [cancelPress])

  const onContextMenu = useCallback((e: React.MouseEvent) => {
    if (hasFired.current) {
      e.preventDefault()
    }
  }, [])

  return { handlers: { onTouchStart, onTouchEnd, onTouchMove, onContextMenu }, isPressing, highlight }
}
