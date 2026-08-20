import { FloatingPortal, autoUpdate, flip, offset, shift, useFloating } from "@floating-ui/react"
import { type RefObject, useEffect, useLayoutEffect, useRef } from "react"

import { FLOATING_PORTAL_ROOT_ID } from "~/react/ui/floatingPortalRoot"

interface LinkDialogProps {
  // The toolbar button the popover anchors to. Positioned with floating-ui so
  // the menu flips/shifts to stay on-screen — the link button sits near the
  // right edge of the toolbar, where a plain left-aligned dropdown clipped off.
  anchorRef: RefObject<HTMLElement | null>
  defaultUrl: string
  onApply: (href: string) => void
  onCancel: () => void
}

export function LinkDialog({ anchorRef, defaultUrl, onApply, onCancel }: LinkDialogProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  const { refs, floatingStyles } = useFloating({
    open: true,
    placement: "bottom-end",
    middleware: [offset(4), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })
  const { setReference, setFloating } = refs

  // Anchor to the toolbar button. Reading the ref in a layout effect (not during
  // render) keeps positioning computed before paint, so the popover never flashes
  // at the top-left corner.
  useLayoutEffect(() => {
    setReference(anchorRef.current)
  }, [setReference, anchorRef])

  // The popover renders in a portal at the document root, so a plain autoFocus
  // would scroll the page to bring the input into view. Focus without scrolling,
  // matching the GIF picker.
  useEffect(() => {
    inputRef.current?.focus({ preventScroll: true })
  }, [])

  const handleApply = () => {
    const href = inputRef.current?.value
    if (href) onApply(href)
  }

  return (
    <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
      <div ref={setFloating} style={floatingStyles} className="floating-card !p-3 z-50 w-64">
        <input
          ref={inputRef}
          type="text"
          placeholder="URL"
          className="input input-sm w-full mb-2"
          defaultValue={defaultUrl}
          onKeyDown={e => {
            if (e.key === "Enter") {
              e.preventDefault()
              handleApply()
            }
            if (e.key === "Escape") onCancel()
          }}
        />
        <div className="flex justify-end gap-1">
          <button type="button" className="btn btn-ghost btn-xs" onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn btn-primary btn-xs" onClick={handleApply}>
            Apply
          </button>
        </div>
      </div>
    </FloatingPortal>
  )
}
