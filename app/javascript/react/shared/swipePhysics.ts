// Axis-lock and resistance primitives for building horizontal swipe gestures.

// Movement must clear this before an axis is locked, so a tap doesn't register.
export const AXIS_LOCK_SLOP_PX = 8
// Horizontal travel must dominate vertical by this ratio to own the gesture;
// otherwise the touch is left to scroll the page.
export const AXIS_LOCK_RATIO = 1.2
// Swallow the synthetic click that trails a committing touch so it can't also
// activate whatever sits under the finger (a link, a button).
export const CLICK_SUPPRESSION_MS = 300

export type GestureAxis = "undecided" | "horizontal" | "vertical"

// Stays "undecided" until movement clears the slop, then locks the dominant axis.
export function classifyAxis(absX: number, absY: number): GestureAxis {
  if (Math.max(absX, absY) < AXIS_LOCK_SLOP_PX) return "undecided"
  return absX > absY * AXIS_LOCK_RATIO ? "horizontal" : "vertical"
}

// iOS-style rubber band: 1:1 tracking up to `knee`, then progressive resistance
// so the row trails the finger past it instead of keeping pace. Higher `factor`
// is looser; the shortfall from 1:1 saturates at knee / factor px.
export function rubberBand(value: number, knee: number, factor: number): number {
  if (value <= knee) return value
  const overshoot = value - knee
  return knee + overshoot * (1 - 1 / (1 + (overshoot / knee) * factor))
}
