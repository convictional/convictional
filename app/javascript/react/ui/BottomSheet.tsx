import { FloatingPortal } from "@floating-ui/react"
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState, type ReactNode } from "react"

import { FLOATING_PORTAL_ROOT_ID } from "./floatingPortalRoot"
import { useScrollLock } from "./hooks/useScrollLock"

interface BottomSheetProps {
  title?: ReactNode
  ariaLabel?: string
  /** Invoked once the sheet has finished animating closed and should be unmounted. */
  onClose: () => void
  closeAriaLabel?: string
  /**
   * `passthrough` (default) — renders nothing at `md:` and above so the caller
   * can render its own desktop UI in place of the sheet.
   * `docked` — switches to a floating right-docked card at `md:` and above.
   */
  desktop?: "passthrough" | "docked"
  /** Element rendered at the start of the header, before the title. */
  headerStart?: ReactNode
  children: ReactNode
}

export interface BottomSheetHandle {
  /** Begin the close animation. `onClose` fires when it completes. */
  close: () => void
}

// Drag past this many pixels and the sheet dismisses on touch end.
const DRAG_DISMISS_THRESHOLD = 80

export const BottomSheet = forwardRef<BottomSheetHandle, BottomSheetProps>(function BottomSheet(
  { title, ariaLabel, onClose, closeAriaLabel = "Close", desktop = "passthrough", headerStart, children },
  ref
) {
  const isDocked = desktop === "docked"
  const backdropRef = useRef<HTMLDivElement>(null)
  const sheetRef = useRef<HTMLElement>(null)
  const [closing, setClosing] = useState(false)

  // Trigger the close animation (slide-down on mobile, slide-out to the right on
  // desktop docked); the animationend listener calls `onClose` once it finishes.
  const requestClose = useCallback(() => {
    setClosing(true)
  }, [])

  useImperativeHandle(ref, () => ({ close: requestClose }), [requestClose])

  // Fire `onClose` once the slide-down (close) animation finishes. Attached as a
  // native listener on the sheet element rather than via React's onAnimationEnd:
  // the sheet renders inside a FloatingPortal, and React's synthetic animation-
  // event delegation doesn't reliably reach portaled nodes (notably under jsdom
  // in tests). A native listener on the element itself is unaffected.
  useEffect(() => {
    const node = sheetRef.current
    if (!node) return
    const handler = (e: AnimationEvent) => {
      // Animation events bubble — only react to the sheet's own animation.
      if (e.target !== node) return
      if (closing) onClose()
    }
    node.addEventListener("animationend", handler)
    return () => node.removeEventListener("animationend", handler)
  }, [closing, onClose])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") requestClose()
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [requestClose])

  // Lock page scroll while the sheet is shown on mobile. On desktop with
  // `desktop="docked"`, the panel is non-modal — leave the page scrollable.
  // Read matchMedia in an effect, not render, to keep rendering pure.
  const [lockScroll, setLockScroll] = useState(false)
  useEffect(() => {
    setLockScroll(typeof window.matchMedia === "function" && window.matchMedia("(max-width: 767px)").matches)
  }, [])
  useScrollLock(lockScroll)

  // --- Drag-to-dismiss ---
  const dragStartY = useRef<number | null>(null)
  const [dragOffset, setDragOffset] = useState(0)

  const handleTouchStart = useCallback((e: React.TouchEvent) => {
    dragStartY.current = e.touches[0].clientY
  }, [])

  const handleTouchMove = useCallback((e: React.TouchEvent) => {
    if (dragStartY.current === null) return
    const dy = e.touches[0].clientY - dragStartY.current
    setDragOffset(Math.max(0, dy))
  }, [])

  const handleTouchEnd = useCallback(() => {
    if (dragOffset > DRAG_DISMISS_THRESHOLD) {
      requestClose()
    } else {
      setDragOffset(0)
    }
    dragStartY.current = null
  }, [dragOffset, requestClose])

  // Only dismiss when the press *originated* on the backdrop. The synthetic
  // click iOS fires when a long-press finger lifts has no preceding mousedown on
  // the backdrop (the finger went down on the bubble, before the backdrop
  // existed), so this ignores that stray click regardless of timing.
  //
  // Track the origin on a window listener rather than the backdrop's own
  // onMouseDown: a press that starts on the backdrop but releases elsewhere
  // (sliding onto the panel, say) never fires the backdrop's click, so an
  // element-scoped flag would stay stuck `true` and a later stray synthetic
  // click on the backdrop would wrongly dismiss. Recomputing on every press
  // keeps it fresh.
  const pressedOnBackdrop = useRef(false)
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      pressedOnBackdrop.current = e.target === backdropRef.current
    }
    window.addEventListener("mousedown", handler)
    return () => window.removeEventListener("mousedown", handler)
  }, [])

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === backdropRef.current && pressedOnBackdrop.current) requestClose()
    pressedOnBackdrop.current = false
  }

  const sheetAnimation = closing
    ? isDocked
      ? "max-md:animate-slide-down md:animate-panel-out"
      : "animate-slide-down"
    : isDocked
      ? "max-md:animate-slide-up md:animate-panel-in"
      : "animate-slide-up"

  return (
    <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
      <div
        ref={backdropRef}
        className={[
          "fixed inset-0 z-[60] bg-black/40 backdrop-blur-xs transition-opacity duration-300",
          closing ? "opacity-0" : "opacity-100",
          isDocked ? "md:hidden" : "",
        ].join(" ")}
        onClick={handleBackdropClick}
        aria-hidden="true"
      />
      <aside
        ref={sheetRef}
        className={[
          "fixed z-[70] flex flex-col overflow-hidden",
          "inset-x-0 bottom-0 bg-base-200 rounded-t-2xl border-t border-base-300 max-h-[85dvh]",
          sheetAnimation,
          isDocked
            ? "md:inset-auto md:top-3 md:right-3 md:bottom-3 md:left-auto md:w-80 md:max-h-none md:rounded-xl md:border md:border-base-300"
            : "md:hidden",
        ].join(" ")}
        style={{
          transform: dragOffset > 0 ? `translateY(${dragOffset}px)` : undefined,
          transition: dragOffset > 0 ? "none" : undefined,
        }}
        role="dialog"
        aria-modal="true"
        aria-label={ariaLabel ?? (typeof title === "string" ? title : undefined)}
        data-comment-portal
      >
        {/* Drag handle — swipe down (or tap) to dismiss. Hidden on docked desktop. */}
        <div
          className={[
            "flex justify-center py-3 cursor-grab active:cursor-grabbing touch-none shrink-0",
            isDocked ? "md:hidden" : "",
          ].join(" ")}
          onTouchStart={handleTouchStart}
          onTouchMove={handleTouchMove}
          onTouchEnd={handleTouchEnd}
          onClick={requestClose}
        >
          <div className="w-10 h-1 rounded-full bg-base-content/20" />
        </div>

        {(title !== undefined || headerStart) && (
          <header className="flex items-center gap-2 px-3 pb-2 md:pt-2 shrink-0">
            {headerStart}
            {title !== undefined && <h2 className="flex-1 text-base font-semibold">{title}</h2>}
            <button
              type="button"
              onClick={requestClose}
              aria-label={closeAriaLabel}
              className={`btn btn-ghost btn-sm btn-square ${title === undefined ? "ml-auto" : ""}`}
            >
              <span className="material-symbols-outlined text-lg leading-none">close</span>
            </button>
          </header>
        )}
        {children}
      </aside>
    </FloatingPortal>
  )
})
