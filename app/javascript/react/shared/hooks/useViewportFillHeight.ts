import { useLayoutEffect } from "react"
import type { RefObject } from "react"

// Stretches an element to fill from its own top down to the bottom of the
// dynamic viewport (minHeight = calc(100dvh - documentTop)). A bottom-pinned
// (sticky) child — e.g. a message/comment composer — then sits at the viewport
// bottom even when the content above is too short to scroll; taller content
// overflows and the sticky child pins during scroll as usual.
//
// Recomputes only when the element's own layout shifts (a header resizing) or
// the window resizes. Mobile address-bar transitions need no observer since
// 100dvh already tracks the dynamic viewport.
//
// `ready` re-runs the setup once the target actually mounts — islands that gate
// the element behind a loading skeleton render it only after data arrives, so a
// stable-ref-only effect would fire once (before the element exists) and never
// reattach. Pass the island's loaded flag; defaults to true for always-mounted
// callers.
export function useViewportFillHeight(ref: RefObject<HTMLElement | null>, ready = true) {
  useLayoutEffect(() => {
    const el = ref.current
    if (!el || !ready) return
    let rafId = 0
    let lastTop = NaN
    const update = () => {
      rafId = 0
      // Document-relative, not viewport-relative: once auto-scroll moves the
      // element's top above the viewport, getBoundingClientRect().top goes
      // negative and `calc(100dvh - (-X))` would inflate the element, opening a
      // gap between the last content and the sticky child.
      const top = el.getBoundingClientRect().top + window.scrollY
      if (top === lastTop) return
      lastTop = top
      el.style.minHeight = `calc(100dvh - ${top}px)`
    }
    const schedule = () => {
      if (rafId) return
      rafId = requestAnimationFrame(update)
    }
    update()
    // minHeight (not top/margin) can't feed back into `top`, so observing the
    // element itself won't loop.
    const observer = new ResizeObserver(schedule)
    observer.observe(el)
    window.addEventListener("resize", schedule)
    return () => {
      observer.disconnect()
      window.removeEventListener("resize", schedule)
      if (rafId) cancelAnimationFrame(rafId)
    }
  }, [ref, ready])
}
