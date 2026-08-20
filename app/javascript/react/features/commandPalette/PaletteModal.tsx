import { type ReactNode, type RefObject, useRef } from "react"

import { useScrollLock } from "~/react/ui/hooks/useScrollLock"

interface PaletteModalProps {
  isOpen: boolean
  onClose: () => void
  onMouseMove: (event: { clientX: number; clientY: number }) => void
  children: ReactNode
  rootRef?: RefObject<HTMLDivElement | null>
}

export function PaletteModal({ isOpen, onClose, onMouseMove, children, rootRef }: PaletteModalProps) {
  const dialogRef = useRef<HTMLDivElement>(null)

  useScrollLock(isOpen)

  if (!isOpen) return null

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      tabIndex={-1}
      data-test-id="command-palette"
      className="fixed inset-0 z-50"
      onMouseMove={onMouseMove}
    >
      <div className="overlay-backdrop fixed inset-0" onClick={onClose} aria-hidden="true" />
      <div className="fixed top-20 left-1/2 -translate-x-1/2 w-full max-w-2xl px-4">
        <div ref={rootRef} className="floating-card w-full overflow-hidden !p-0 !rounded-3xl">
          {children}
        </div>
      </div>
    </div>
  )
}
