import type { Placement } from "@floating-ui/react"
import {
  FloatingPortal,
  autoUpdate,
  flip,
  offset,
  shift,
  useDismiss,
  useFloating,
  useFocus,
  useHover,
  useInteractions,
  useRole,
  useTransitionStyles,
} from "@floating-ui/react"
import type { ReactNode } from "react"
import { useState } from "react"

import { FLOATING_PORTAL_ROOT_ID } from "./floatingPortalRoot"

interface TooltipProps {
  content: ReactNode
  placement?: Placement
  delay?: number
  className?: string
  children: ReactNode
}

export function Tooltip({ content, placement = "top", delay = 400, className, children }: TooltipProps) {
  const [isOpen, setIsOpen] = useState(false)

  const { refs, floatingStyles, context } = useFloating({
    open: isOpen,
    onOpenChange: setIsOpen,
    placement,
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })
  const { setReference, setFloating } = refs

  const hover = useHover(context, { move: false, delay: { open: delay, close: 50 } })
  const focus = useFocus(context)
  const dismiss = useDismiss(context)
  const role = useRole(context, { role: "tooltip" })
  const { getReferenceProps, getFloatingProps } = useInteractions([hover, focus, dismiss, role])

  const { isMounted, styles: transitionStyles } = useTransitionStyles(context, {
    duration: 100,
    initial: { opacity: 0 },
  })

  if (!content) return <>{children}</>

  return (
    <>
      <span ref={setReference} {...getReferenceProps()} className={className}>
        {children}
      </span>
      {/* Mount inside the persistent layout root so the portal subRoot survives
          page swaps — otherwise it lives on document.body, gets wiped, and
          subsequent renders portal into a detached node. */}
      <FloatingPortal id={FLOATING_PORTAL_ROOT_ID}>
        {isMounted && (
          <div
            ref={setFloating}
            style={{ ...floatingStyles, ...transitionStyles }}
            {...getFloatingProps()}
            className="z-50 pointer-events-none @mobile:hidden"
          >
            <div className="tooltip-card px-2 py-1.5 text-xs max-w-64 animate-tooltip-pop">{content}</div>
          </div>
        )}
      </FloatingPortal>
    </>
  )
}
