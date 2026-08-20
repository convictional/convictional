import { useCallback, useEffect, useRef, useState } from "react"

const HIGHLIGHT_DURATION_MS = 2000

// The comment id named by a `#comment-<id>` deep-link hash, or null when the hash
// targets no comment. The single source of truth for parsing the convention; the
// hash listener and other scroll sites read it through here.
export function commentIdFromHash(hash: string): string | null {
  const match = /^#comment-(.+)$/.exec(hash)
  return match ? match[1] : null
}

// Whether a hash targets a comment deep link. Scroll sites that should yield to the
// hash listener gate on this rather than re-testing the `#comment-` prefix themselves.
export function hashTargetsComment(hash: string = window.location.hash): boolean {
  return commentIdFromHash(hash) !== null
}

// The DOM node for a deep-linkable comment, located by the `data-comment-id`
// attribute its row renders. The single place the selector convention lives, so
// the hash listener and click-to-scroll callers find comments the same way.
export function findCommentElement(id: string): HTMLElement | null {
  return document.querySelector(`[data-comment-id="${CSS.escape(id)}"]`)
}

export interface UseScrollToHashCommentResult {
  // The comment currently flashing its highlight, or null.
  highlightedId: string | null
  // Scroll to a comment and flash its highlight. Used by the hash listener and
  // by click-to-scroll affordances (post's WhatsNewPanel rows, decision banner).
  scrollToComment: (id: string) => void
}

// Scrolls to and flashes the comment named by a `#comment-<id>` hash — the deep-link
// convention shared across postShow and emailThreadShow. A comment's row marks itself
// with `data-comment-id={id}`; this finds it by that attribute, scrolls it into view,
// and returns the id to highlight so the caller can flag the matching row. A hash (or
// `scrollToComment` call) naming an unknown/inaccessible comment no-ops.
//
// `ready` gates the initial scroll for lists whose comments load asynchronously (email
// threads). It defaults to true for callers whose comments are present on mount.
export function useScrollToHashComment(ready: boolean = true): UseScrollToHashCommentResult {
  const [highlightedId, setHighlightedId] = useState<string | null>(null)
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const scrollToComment = useCallback((id: string) => {
    const el = findCommentElement(id)
    if (!el) return
    el.scrollIntoView({ behavior: "smooth", block: "center" })
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current)
    setHighlightedId(id)
    highlightTimerRef.current = setTimeout(() => setHighlightedId(null), HIGHLIGHT_DURATION_MS)
  }, [])

  useEffect(() => {
    if (!ready) return
    let rafId = 0
    const handleHash = () => {
      const id = commentIdFromHash(window.location.hash)
      // Defer one frame so a freshly-rendered comment is in the DOM before lookup
      // (mount + hashchange both route through here).
      if (id) rafId = requestAnimationFrame(() => scrollToComment(id))
    }
    handleHash()
    window.addEventListener("hashchange", handleHash)
    return () => {
      window.removeEventListener("hashchange", handleHash)
      if (rafId) cancelAnimationFrame(rafId)
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current)
    }
  }, [ready, scrollToComment])

  return { highlightedId, scrollToComment }
}
