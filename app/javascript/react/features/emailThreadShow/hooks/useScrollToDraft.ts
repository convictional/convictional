import { useEffect } from "react"
import type { RefObject } from "react"

interface UseScrollToDraftOptions {
  composerRef: RefObject<HTMLElement | null>
  // Offset to account for the sticky header / nav. Defaults to 150px.
  headerOffsetPx?: number
  // Re-runs when this key changes — typically the draft message id so each
  // new draft creation (including the replace-after-409 path) triggers
  // exactly one scroll.
  scrollKey: string | null
}

// Scrolls to the reply/forward composer after the actor starts a draft, with
// the sticky header offset baked in. Keyed on the draft message id so each
// new draft creation triggers exactly one scroll.
export function useScrollToDraft({ composerRef, headerOffsetPx = 150, scrollKey }: UseScrollToDraftOptions): void {
  useEffect(() => {
    if (!scrollKey) return
    // 150ms delay allows the timeline to commit its layout before we measure.
    const timeoutId = window.setTimeout(() => {
      const target = composerRef.current
      if (!target) return
      const rect = target.getBoundingClientRect()
      const finalPosition = Math.max(0, rect.top + window.scrollY - headerOffsetPx)
      window.scrollTo({ top: finalPosition, behavior: "smooth" })
    }, 150)

    return () => window.clearTimeout(timeoutId)
  }, [scrollKey, composerRef, headerOffsetPx])
}
