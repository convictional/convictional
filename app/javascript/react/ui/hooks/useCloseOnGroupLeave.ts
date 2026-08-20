import { useEffect } from "react"

// Keep the dropdown open while the cursor is over the trigger's `.group`
// ancestor or over the floating element. We track the cursor position
// directly rather than using `mouseleave` because the floating element's
// visual extent (drop shadow, rounded corners) is larger than its hit target
// and the transit gap between trigger and dropdown is outside both — both
// cases make mouseleave fire while the user thinks they're still "on" the
// dropdown.
const SAFE_BUFFER_PX = 32

export function useCloseOnGroupLeave(
  isOpen: boolean,
  close: () => void,
  triggerRef: { readonly current: unknown },
  floatingRef: { readonly current: unknown }
): void {
  useEffect(() => {
    if (!isOpen) return
    const trigger = triggerRef.current
    if (!(trigger instanceof HTMLElement)) return
    const group = trigger.closest(".group")
    if (!group) return

    let timer: number | null = null
    let frame: number | null = null
    let pointerX = 0
    let pointerY = 0
    const cancelClose = () => {
      if (timer !== null) {
        clearTimeout(timer)
        timer = null
      }
    }
    const isInside = (rect: DOMRect, x: number, y: number, buffer: number) =>
      x >= rect.left - buffer && x <= rect.right + buffer && y >= rect.top - buffer && y <= rect.bottom + buffer

    const evaluate = () => {
      frame = null
      const floating = floatingRef.current instanceof HTMLElement ? floatingRef.current : null
      const overGroup = isInside(group.getBoundingClientRect(), pointerX, pointerY, 0)
      const overFloating = floating
        ? isInside(floating.getBoundingClientRect(), pointerX, pointerY, SAFE_BUFFER_PX)
        : false
      if (overGroup || overFloating) {
        cancelClose()
      } else if (timer === null) {
        timer = window.setTimeout(close, 300)
      }
    }

    // Coalesce pointermove bursts so we read layout at most once per frame.
    const handlePointerMove = (event: PointerEvent) => {
      pointerX = event.clientX
      pointerY = event.clientY
      if (frame === null) frame = requestAnimationFrame(evaluate)
    }

    document.addEventListener("pointermove", handlePointerMove)

    return () => {
      cancelClose()
      if (frame !== null) cancelAnimationFrame(frame)
      document.removeEventListener("pointermove", handlePointerMove)
    }
  }, [isOpen, close, triggerRef, floatingRef])
}
