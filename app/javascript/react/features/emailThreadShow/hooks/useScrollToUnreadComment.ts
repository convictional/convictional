import { useEffect, useRef } from "react"

import { findCommentElement, hashTargetsComment } from "~/react/shared/hooks/useScrollToHashComment"

// Upper bound on how long to keep re-centering after load. Email bodies size
// within a few seconds; this is only a stop cap so a document that keeps
// reflowing can't hold the viewport indefinitely. Re-centering itself is driven
// by the ResizeObserver below (real growth), not by a timer.
const SETTLE_WINDOW_MS = 3000

// Centers the first unread comment on initial load and re-centers it while the
// expanded email-body iframes above it grow. Those iframes start at a small
// placeholder height and resize asynchronously via ResizeObserver (EmailMessageBody);
// with document scroll anchoring disabled globally (useDisableDocumentScrollAnchor)
// that growth would otherwise drift the comment — and its "N new comments"
// divider — down behind the sticky composer. A trailing comment also can't be
// top-aligned (scrollIntoView "start" clamps to max scroll), so we center it.
//
// The message initial scroll (useInitialThreadScroll) does not need this: every
// message above its target renders collapsed, so nothing above it grows.
//
// Fires once per (read-state, comment) target, yields to a #comment- deep link,
// and stops on the first user gesture, a deep-link navigation, or the settle cap.
export function useScrollToUnreadComment(commentId: string | null, scrollKey: string | null): void {
  const scrolledForKey = useRef<string | null>(null)

  useEffect(() => {
    if (!commentId || !scrollKey) return
    const key = `${scrollKey}::${commentId}`
    if (scrolledForKey.current === key) return
    if (hashTargetsComment()) return // yield to useScrollToHashComment
    const element = findCommentElement(commentId)
    if (!element) return // not rendered yet; a later render re-runs this effect
    scrolledForKey.current = key

    const center = () => element.scrollIntoView({ block: "center", behavior: "instant" })
    center()

    // Re-center on each real layout growth (an iframe finishing its size) — the
    // ResizeObserver fires only when document height actually changes, so this
    // reacts to the growth signal instead of polling every animation frame.
    const observer = new ResizeObserver(center)
    observer.observe(document.body)

    let stopped = false
    const stop = () => {
      if (stopped) return
      stopped = true
      observer.disconnect()
      clearTimeout(timer)
      // pointerdown covers scrollbar drags and a click on an in-bubble ReplyQuote;
      // hashchange covers a #comment- deep link arriving mid-window. Both drive
      // their own scroll that the re-center would otherwise fight.
      window.removeEventListener("wheel", stop)
      window.removeEventListener("touchmove", stop)
      window.removeEventListener("pointerdown", stop)
      window.removeEventListener("keydown", stop)
      window.removeEventListener("hashchange", stop)
    }
    const timer = setTimeout(stop, SETTLE_WINDOW_MS)
    window.addEventListener("wheel", stop, { passive: true })
    window.addEventListener("touchmove", stop, { passive: true })
    window.addEventListener("pointerdown", stop, { passive: true })
    window.addEventListener("keydown", stop)
    window.addEventListener("hashchange", stop)

    return stop
  }, [commentId, scrollKey])
}
