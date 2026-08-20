import { useEffect, useRef, type RefObject } from "react"

interface ScrollIntoViewOnEditOptions {
  // scrollIntoView alignment. "nearest" (default) only scrolls when the element is
  // hidden; "center" forces it to the middle, clearing an on-screen obstruction
  // like the mobile keyboard that "nearest" would leave the form pinned behind.
  block?: ScrollLogicalPosition
  // Delay before scrolling, e.g. to let the mobile keyboard finish opening and the
  // viewport settle before measuring. Defaults to 0 (scroll on the next tick).
  delayMs?: number
}

// Scroll an inline form into view when it opens so it clears the sticky bottom
// composer (or, on mobile, the keyboard). Attach the returned ref to the element;
// with the default block: "nearest" + a `scroll-mb-*` margin the scroll only fires
// when the form's bottom is hidden and is a no-op when it's already fully visible.
export function useScrollIntoViewOnEdit<T extends HTMLElement>(
  active: boolean,
  { block = "nearest", delayMs = 0 }: ScrollIntoViewOnEditOptions = {}
): RefObject<T | null> {
  const ref = useRef<T | null>(null)
  useEffect(() => {
    if (!active) return
    const scroll = () => ref.current?.scrollIntoView({ block, behavior: "smooth" })
    if (delayMs === 0) {
      scroll()
      return
    }
    const timer = window.setTimeout(scroll, delayMs)
    return () => clearTimeout(timer)
  }, [active, block, delayMs])
  return ref
}
