import { useCallback, useRef, useState } from "react"
import type { RefObject } from "react"

const MIN_SCALE = 1
const MAX_SCALE = 5
const STEP = 0.5
const TOGGLE_SCALE = 2

interface Offset {
  x: number
  y: number
}

export interface ImageZoom {
  scale: number
  offset: Offset
  isZoomed: boolean
  transform: string
  setScale: (scale: number) => void
  zoomIn: () => void
  zoomOut: () => void
  zoomBy: (delta: number) => void
  toggle: () => void
  reset: () => void
  panBy: (dx: number, dy: number) => void
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

// Drives wheel/pinch zoom and drag-pan for a single image. The caller owns the
// event wiring (so it can coexist with swipe-to-navigate); this hook owns the
// state, clamping, and the resulting CSS transform.
export function useImageZoom(imageRef: RefObject<HTMLElement | null>): ImageZoom {
  const [scale, setScaleState] = useState(MIN_SCALE)
  const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 })
  const scaleRef = useRef(MIN_SCALE)

  // At scale s the image overflows its fitted box by (s-1)*size, half each side;
  // clamping pan to that keeps the image from being dragged out of view.
  const clampOffset = useCallback(
    (next: Offset, atScale: number): Offset => {
      const el = imageRef.current
      const maxX = el ? ((atScale - 1) * el.clientWidth) / 2 : 0
      const maxY = el ? ((atScale - 1) * el.clientHeight) / 2 : 0
      return { x: clamp(next.x, -maxX, maxX), y: clamp(next.y, -maxY, maxY) }
    },
    [imageRef]
  )

  const setScale = useCallback(
    (raw: number) => {
      const next = clamp(raw, MIN_SCALE, MAX_SCALE)
      scaleRef.current = next
      setScaleState(next)
      setOffset(prev => (next === MIN_SCALE ? { x: 0, y: 0 } : clampOffset(prev, next)))
    },
    [clampOffset]
  )

  const zoomBy = useCallback((delta: number) => setScale(scaleRef.current + delta), [setScale])
  const zoomIn = useCallback(() => setScale(scaleRef.current + STEP), [setScale])
  const zoomOut = useCallback(() => setScale(scaleRef.current - STEP), [setScale])
  const reset = useCallback(() => setScale(MIN_SCALE), [setScale])
  const toggle = useCallback(() => setScale(scaleRef.current > MIN_SCALE ? MIN_SCALE : TOGGLE_SCALE), [setScale])

  const panBy = useCallback(
    (dx: number, dy: number) => {
      setOffset(prev => clampOffset({ x: prev.x + dx, y: prev.y + dy }, scaleRef.current))
    },
    [clampOffset]
  )

  return {
    scale,
    offset,
    isZoomed: scale > MIN_SCALE,
    transform: `translate(${offset.x}px, ${offset.y}px) scale(${scale})`,
    setScale,
    zoomIn,
    zoomOut,
    zoomBy,
    toggle,
    reset,
    panBy,
  }
}

export { MAX_SCALE, MIN_SCALE }
