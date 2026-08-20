import { useEffect, useLayoutEffect, useRef, useState } from "react"

import { Dialog } from "./Dialog"
import { MAX_SCALE, useImageZoom } from "./hooks/useImageZoom"

interface LightboxImage {
  src: string
  alt: string
}

interface LightboxProps {
  images: LightboxImage[]
  initialIndex?: number
  isOpen: boolean
  onClose: () => void
}

// Horizontal swipe threshold and dominance ratio: a gesture only counts as a
// swipe if it moves at least this many px horizontally AND is more horizontal
// than vertical, so vertical scrolls on the thumb strip don't trigger nav.
const SWIPE_THRESHOLD_PX = 40

function touchDistance(touches: React.TouchList): number {
  return Math.hypot(touches[0].clientX - touches[1].clientX, touches[0].clientY - touches[1].clientY)
}

// Callers that re-open the lightbox at a different image should give this
// component a `key` tied to the open index so each open is a fresh mount —
// useState only honors `initialIndex` on first mount.
export function Lightbox({ images, initialIndex = 0, isOpen, onClose }: LightboxProps) {
  const [index, setIndex] = useState(initialIndex)
  const [thumbnailsHeight, setThumbnailsHeight] = useState(0)
  const thumbnailsRef = useRef<HTMLDivElement | null>(null)
  const imageRef = useRef<HTMLImageElement | null>(null)
  const touchStartRef = useRef<{ x: number; y: number } | null>(null)
  const pinchRef = useRef<{ distance: number; scale: number } | null>(null)
  const panPointRef = useRef<{ x: number; y: number } | null>(null)
  // Anchor initial focus on a stable element rather than a tabbable-index,
  // which shifts as the prev/next and zoom buttons appear and disappear.
  const downloadRef = useRef<HTMLAnchorElement | null>(null)
  const zoom = useImageZoom(imageRef)

  useEffect(() => {
    if (!isOpen || images.length <= 1) return
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowLeft") setIndex(i => Math.max(0, i - 1))
      else if (e.key === "ArrowRight") setIndex(i => Math.min(images.length - 1, i + 1))
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [isOpen, images.length])

  useEffect(() => {
    if (!isOpen) return
    const thumbnails = thumbnailsRef.current
    if (!thumbnails) return
    const active = thumbnails.children[index] as HTMLElement | undefined
    active?.scrollIntoView?.({ behavior: "smooth", inline: "center", block: "nearest" })
  }, [index, isOpen])

  // Track the thumbnails' height so the image box can reserve exactly that space
  // below itself, keeping them clear of the mobile home indicator without
  // hard-coding their dimensions. useLayoutEffect measures before paint so the
  // box never flashes at full height.
  useLayoutEffect(() => {
    const thumbnails = thumbnailsRef.current
    if (!thumbnails) return
    const measure = () => setThumbnailsHeight(thumbnails.offsetHeight)
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(thumbnails)
    return () => observer.disconnect()
  }, [isOpen, images.length])

  // A fresh image (navigation) or a fresh open should always start unzoomed.
  // resetZoom is stable (useCallback over a ref-backed chain), so listing it
  // doesn't re-run this on every render.
  const { reset: resetZoom } = zoom
  useEffect(() => {
    resetZoom()
  }, [index, isOpen, resetZoom])

  if (images.length === 0) return null
  const safeIndex = Math.min(Math.max(0, index), images.length - 1)
  const current = images[safeIndex]
  const hasMultiple = images.length > 1
  const atStart = safeIndex === 0
  const atEnd = safeIndex === images.length - 1

  function onTouchStart(e: React.TouchEvent) {
    if (e.touches.length === 2) {
      pinchRef.current = { distance: touchDistance(e.touches), scale: zoom.scale }
      touchStartRef.current = null
      return
    }
    const t = e.touches[0]
    touchStartRef.current = { x: t.clientX, y: t.clientY }
    if (zoom.isZoomed) panPointRef.current = { x: t.clientX, y: t.clientY }
  }

  function onTouchMove(e: React.TouchEvent) {
    if (e.touches.length === 2 && pinchRef.current) {
      const ratio = touchDistance(e.touches) / pinchRef.current.distance
      zoom.setScale(pinchRef.current.scale * ratio)
      return
    }
    if (zoom.isZoomed && panPointRef.current && e.touches.length === 1) {
      const t = e.touches[0]
      zoom.panBy(t.clientX - panPointRef.current.x, t.clientY - panPointRef.current.y)
      panPointRef.current = { x: t.clientX, y: t.clientY }
    }
  }

  function onTouchEnd(e: React.TouchEvent) {
    if (pinchRef.current) {
      pinchRef.current = null
      return
    }
    const start = touchStartRef.current
    touchStartRef.current = null
    panPointRef.current = null
    // Swipe-to-navigate is disabled while zoomed — there, one finger pans.
    if (!start || !hasMultiple || zoom.isZoomed) return
    const t = e.changedTouches[0]
    const dx = t.clientX - start.x
    const dy = t.clientY - start.y
    if (Math.abs(dx) < SWIPE_THRESHOLD_PX || Math.abs(dx) <= Math.abs(dy)) return
    if (dx < 0) setIndex(i => Math.min(images.length - 1, i + 1))
    else setIndex(i => Math.max(0, i - 1))
  }

  // Mouse drag-pan; touch panning is handled by the touch handlers above.
  function onPointerDown(e: React.PointerEvent) {
    if (e.pointerType !== "mouse" || !zoom.isZoomed) return
    e.preventDefault()
    imageRef.current?.setPointerCapture?.(e.pointerId)
    panPointRef.current = { x: e.clientX, y: e.clientY }
  }

  function onPointerMove(e: React.PointerEvent) {
    if (e.pointerType !== "mouse" || !panPointRef.current) return
    zoom.panBy(e.clientX - panPointRef.current.x, e.clientY - panPointRef.current.y)
    panPointRef.current = { x: e.clientX, y: e.clientY }
  }

  function onPointerUp(e: React.PointerEvent) {
    if (e.pointerType !== "mouse") return
    panPointRef.current = null
  }

  return (
    <Dialog
      isOpen={isOpen}
      onClose={onClose}
      className="relative flex flex-col items-center gap-2"
      initialFocus={downloadRef}
      ariaLabel={hasMultiple ? `Image gallery (${images.length} images)` : "Image viewer"}
    >
      {/* Clicking the empty letterbox area (the container itself, not a child)
          dismisses — without this, only the thin strip outside the box closes. */}
      <div
        className="relative w-[90vw] flex items-center justify-center overflow-hidden"
        style={{
          touchAction: "none",
          // Shrink by the measured thumbnails height (plus the bottom inset) so
          // the image box and its thumbnails together stay within the visible
          // viewport instead of slipping under the mobile home indicator.
          height: hasMultiple ? `calc(80dvh - ${thumbnailsHeight}px - var(--safe-area-inset-bottom))` : "80dvh",
        }}
        onClick={e => {
          if (e.target === e.currentTarget) onClose()
        }}
        onWheel={e => zoom.zoomBy(-e.deltaY * 0.002)}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
      >
        <img
          ref={imageRef}
          src={current.src}
          alt={current.alt}
          draggable={false}
          onDoubleClick={zoom.toggle}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          style={{
            transform: zoom.transform,
            cursor: zoom.isZoomed ? "grab" : "default",
            touchAction: "none",
            // Promote to its own layer so Safari repaints the whole image on
            // zoom instead of leaving 1px seam artifacts from partial repaints.
            willChange: "transform",
            backfaceVisibility: "hidden",
          }}
          className="max-w-full max-h-full object-contain block select-none"
        />
        {hasMultiple && (
          <div className="absolute top-[calc(0.5rem+var(--safe-area-inset-top))] left-2 px-2 py-0.5 rounded bg-black/60 text-white text-xs">
            {safeIndex + 1} / {images.length}
          </div>
        )}
        {hasMultiple && !atStart && (
          <button
            type="button"
            aria-label="Previous image"
            className="btn sm:btn-sm btn-circle absolute left-2 top-1/2 -translate-y-1/2"
            onClick={() => setIndex(i => Math.max(0, i - 1))}
          >
            ‹
          </button>
        )}
        {hasMultiple && !atEnd && (
          <button
            type="button"
            aria-label="Next image"
            className="btn sm:btn-sm btn-circle absolute right-2 top-1/2 -translate-y-1/2"
            onClick={() => setIndex(i => Math.min(images.length - 1, i + 1))}
          >
            ›
          </button>
        )}
        <div className="absolute top-[calc(0.5rem+var(--safe-area-inset-top))] right-2 flex items-center gap-2">
          {/* On touch, pinch and double-tap cover zoom, so the explicit
              controls are hidden on small screens to reduce clutter. */}
          <div className="hidden sm:flex items-center gap-1">
            <button
              type="button"
              aria-label="Zoom out"
              className="btn sm:btn-sm btn-circle"
              onClick={zoom.zoomOut}
              disabled={!zoom.isZoomed}
            >
              <span className="material-symbols-outlined text-base">zoom_out</span>
            </button>
            <button
              type="button"
              aria-label="Zoom in"
              className="btn sm:btn-sm btn-circle"
              onClick={zoom.zoomIn}
              disabled={zoom.scale >= MAX_SCALE}
            >
              <span className="material-symbols-outlined text-base">zoom_in</span>
            </button>
          </div>
          <a
            ref={downloadRef}
            href={current.src}
            download
            aria-label="Download"
            className="btn sm:btn-sm btn-circle"
            onClick={e => e.stopPropagation()}
          >
            <span className="material-symbols-outlined text-base">download</span>
          </a>
          <button type="button" aria-label="Close" className="btn sm:btn-sm btn-circle" onClick={onClose}>
            ✕
          </button>
        </div>
      </div>
      {hasMultiple && (
        <div
          ref={thumbnailsRef}
          role="tablist"
          aria-label="Image thumbnails"
          className="max-w-[90vw] flex gap-1 overflow-x-auto px-1 py-1 rounded bg-black/40"
        >
          {images.map((image, i) => {
            const isActive = i === safeIndex
            return (
              <button
                key={i}
                type="button"
                role="tab"
                aria-selected={isActive}
                aria-label={`Show image ${i + 1}`}
                onClick={() => setIndex(i)}
                className={`shrink-0 w-14 h-14 sm:w-12 sm:h-12 rounded overflow-hidden block transition-opacity ${
                  isActive ? "ring-2 ring-white opacity-100" : "opacity-60 hover:opacity-100"
                }`}
              >
                <img src={image.src} alt="" loading="lazy" className="w-full h-full object-cover block" />
              </button>
            )
          })}
        </div>
      )}
    </Dialog>
  )
}
