import { useEffect } from "react"

// Disable CSS Scroll Anchoring on the document scroll container while the
// island is mounted. WebKit ships scroll-anchoring on by default since Feb
// 2026 and treats a focused composer (a contenteditable) as the spec-priority
// anchor; the algorithm then drags scrollY backwards when content above it
// re-renders. Memoizing rendered items and suppressing nav transitions during
// programmatic scrolls close the trigger surface, and this effect makes the
// bug class structurally impossible.
export function useDisableDocumentScrollAnchor() {
  useEffect(() => {
    const prev = document.body.style.overflowAnchor
    document.body.style.overflowAnchor = "none"
    return () => {
      document.body.style.overflowAnchor = prev
    }
  }, [])
}
