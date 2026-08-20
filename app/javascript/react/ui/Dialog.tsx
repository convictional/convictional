import {
  FloatingFocusManager,
  FloatingOverlay,
  FloatingPortal,
  useDismiss,
  useFloating,
  useInteractions,
  useRole,
} from "@floating-ui/react"
import type { ReactNode, RefObject } from "react"

import { FLOATING_PORTAL_ROOT_ID } from "./floatingPortalRoot"
import { useScrollLock } from "./hooks/useScrollLock"

interface DialogProps {
  isOpen: boolean
  onClose: () => void
  labelledBy?: string
  ariaLabel?: string
  className?: string
  // The overlay defaults to the z-50 modal band; a consumer overrides this only
  // when its overlay must paint above other modal surfaces (e.g. the global
  // confirmation dialog invoked from within another modal).
  overlayZIndexClassName?: string
  testId?: string
  initialFocus?: number | RefObject<HTMLElement | null>
  children: ReactNode
}

// Modal dialog primitive built on @floating-ui/react. We intentionally avoid
// the native <dialog> element (and daisyUI's `.modal` class, which is tied to
// it) so the floating-ui focus manager and dismiss handling stay in charge of
// open state, focus return, and Esc / outside-press behavior in one place.
export function Dialog({
  isOpen,
  onClose,
  labelledBy,
  ariaLabel,
  className,
  overlayZIndexClassName = "z-50",
  testId,
  initialFocus,
  children,
}: DialogProps) {
  const { refs, context } = useFloating({
    open: isOpen,
    onOpenChange: open => {
      if (!open) onClose()
    },
  })

  const dismiss = useDismiss(context, { escapeKey: true, outsidePress: true })
  const role = useRole(context, { role: "dialog" })

  const { getFloatingProps } = useInteractions([dismiss, role])
  const { setFloating } = refs

  // Not FloatingOverlay's `lockScroll`: its scrollbar padding fights the stable gutter.
  useScrollLock(isOpen)

  if (!isOpen) return null

  return (
    <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
      <FloatingOverlay className={`overlay-backdrop ${overlayZIndexClassName} flex items-center justify-center`}>
        <FloatingFocusManager context={context} initialFocus={initialFocus} returnFocus>
          <div
            ref={setFloating}
            aria-labelledby={labelledBy}
            aria-label={ariaLabel}
            data-testid={testId}
            className={className}
            {...getFloatingProps()}
          >
            {children}
          </div>
        </FloatingFocusManager>
      </FloatingOverlay>
    </FloatingPortal>
  )
}
