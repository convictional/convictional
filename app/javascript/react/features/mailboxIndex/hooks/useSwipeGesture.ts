import { useCallback, useRef, useState } from "react"

import { CLICK_SUPPRESSION_MS, classifyAxis, rubberBand } from "~/react/shared/swipePhysics"

// The comments inside this hook are load-bearing — they document non-obvious
// physics and OS-interaction behavior. Do not edit them while refactoring.

const SWIPE_THRESHOLD = 80
const RUBBER_BAND_FACTOR = 0.55
const VELOCITY_WINDOW_MS = 80
const FLICK_VELOCITY_PX_PER_MS = 0.5
const FLICK_MIN_DISTANCE_PX = 40

interface GestureState {
  startX: number
  startY: number
  isTouchTracking: boolean
  isSwipeActive: boolean
  gestureAxis: "undecided" | "horizontal" | "vertical"
  recentlySwipedAt: number
  lastX: number
  lastT: number
  lastVelocity: number
  // Latest committed swipe distance — kept on the gesture ref so handlers can
  // read it without depending on the render-cycle state mirror.
  swipeX: number
}

function initialState(): GestureState {
  return {
    startX: 0,
    startY: 0,
    isTouchTracking: false,
    isSwipeActive: false,
    gestureAxis: "undecided",
    recentlySwipedAt: 0,
    lastX: 0,
    lastT: 0,
    lastVelocity: 0,
    swipeX: 0,
  }
}

export interface SwipeHandlers {
  onTouchStart: (e: React.TouchEvent) => void
  onTouchMove: (e: React.TouchEvent) => void
  onTouchEnd: () => void
  onTouchCancel: () => void
  onClickCapture: (e: React.MouseEvent) => void
}

export interface SwipeGestureResult {
  swipeX: number
  swipeDistance: number
  swipeProgress: number
  swipeDirection: "left" | "right" | "none"
  isSwiping: boolean
  handlers: SwipeHandlers
}

interface UseSwipeGestureArgs {
  enabled: boolean
  onCommit: () => void
}

export function useSwipeGesture({ enabled, onCommit }: UseSwipeGestureArgs): SwipeGestureResult {
  // swipeX is duplicated as state (for transform updates) and on the gesture
  // ref (for synchronous reads inside onTouchEnd). Update both together.
  const [swipeX, setSwipeX] = useState(0)
  const [isSwipeActive, setIsSwipeActive] = useState(false)
  const stateRef = useRef<GestureState>(initialState())

  const reset = useCallback(() => {
    stateRef.current.gestureAxis = "undecided"
    stateRef.current.swipeX = 0
    setSwipeX(0)
  }, [])

  const onTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (!enabled) return
      if (e.touches.length > 1) return
      const touch = e.touches[0]
      const s = stateRef.current
      s.startX = touch.clientX
      s.startY = touch.clientY
      s.isTouchTracking = true
      s.gestureAxis = "undecided"
      s.lastX = touch.clientX
      s.lastT = performance.now()
      s.lastVelocity = 0
    },
    [enabled]
  )

  const onTouchMove = useCallback((e: React.TouchEvent) => {
    const s = stateRef.current
    if (!s.isTouchTracking || e.touches.length > 1) return
    if (s.gestureAxis === "vertical") return

    const touch = e.touches[0]
    const dx = s.startX - touch.clientX
    const dy = s.startY - touch.clientY
    const absX = Math.abs(dx)
    const absY = Math.abs(dy)

    if (s.gestureAxis === "undecided") {
      const axis = classifyAxis(absX, absY)
      if (axis === "undecided") return
      s.gestureAxis = axis
      if (axis === "horizontal") {
        s.isSwipeActive = true
        setIsSwipeActive(true)
      } else {
        return
      }
    }

    // 1:1 finger tracking up to the threshold; iOS-style rubber band beyond.
    const distance = rubberBand(absX, SWIPE_THRESHOLD, RUBBER_BAND_FACTOR)
    const next = dx > 0 ? -distance : distance
    s.swipeX = next
    setSwipeX(next)

    // Per-frame velocity (px/ms, positive = moving right). If the finger paused longer than the
    // window, treat the gap as a reset so the resumed motion isn't averaged with stale samples.
    const now = performance.now()
    const dtSample = now - s.lastT
    s.lastVelocity = dtSample > 0 && dtSample <= VELOCITY_WINDOW_MS ? (touch.clientX - s.lastX) / dtSample : 0
    s.lastX = touch.clientX
    s.lastT = now
  }, [])

  const onTouchEnd = useCallback(() => {
    const s = stateRef.current
    if (!s.isTouchTracking) return

    const wasActive = s.isSwipeActive
    s.isTouchTracking = false
    s.isSwipeActive = false
    setIsSwipeActive(false)

    if (!wasActive) {
      s.gestureAxis = "undecided"
      return
    }

    const velocity = s.lastVelocity
    const distanceAbs = Math.abs(s.swipeX)
    const swipingLeft = s.swipeX < 0
    const continuingSwipe = swipingLeft ? velocity < 0 : velocity > 0
    const flickCommit =
      continuingSwipe && Math.abs(velocity) >= FLICK_VELOCITY_PX_PER_MS && distanceAbs >= FLICK_MIN_DISTANCE_PX
    const distanceCommit = distanceAbs >= SWIPE_THRESHOLD

    if (flickCommit || distanceCommit) {
      // Lock out the synthetic click that follows a committing touch sequence.
      s.recentlySwipedAt = Date.now()
      onCommit()
    } else {
      reset()
    }
  }, [onCommit, reset])

  const onTouchCancel = useCallback(() => {
    // The OS stole the touch (incoming call, system gesture). Never commit — always reset.
    const s = stateRef.current
    s.isTouchTracking = false
    s.isSwipeActive = false
    setIsSwipeActive(false)
    reset()
  }, [reset])

  const onClickCapture = useCallback((e: React.MouseEvent) => {
    const s = stateRef.current
    if (s.isSwipeActive || Date.now() - s.recentlySwipedAt < CLICK_SUPPRESSION_MS) {
      e.preventDefault()
      e.stopPropagation()
    }
  }, [])

  const swipeDistance = Math.abs(swipeX)
  const swipeProgress = Math.max(0, Math.min(1, swipeDistance / SWIPE_THRESHOLD))
  const swipeDirection: "left" | "right" | "none" = swipeX === 0 ? "none" : swipeX < 0 ? "left" : "right"

  return {
    swipeX,
    swipeDistance,
    swipeProgress,
    swipeDirection,
    isSwiping: isSwipeActive,
    handlers: {
      onTouchStart,
      onTouchMove,
      onTouchEnd,
      onTouchCancel,
      onClickCapture,
    },
  }
}
