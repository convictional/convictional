import { useCallback, useEffect, useRef, useState } from "react"

import { useWorkspaceVisitRecording } from "~/react/shared/hooks/useVisitRecording"

const VISIT_CATCH_UP_DEBOUNCE_MS = 1000

interface UseNewCommentsIndicatorOptions {
  // Workspace whose visit is caught up when a new comment arrives while the user
  // reads. Null disables the catch-up (e.g. when the post id hasn't loaded yet).
  workspaceId: string | null
}

interface UseNewCommentsIndicatorResult {
  hasNew: boolean
  // Whether the new comment sits above the viewport (true) or below it (false).
  // Drives the pill's up/down arrow.
  isAbove: boolean
  // Call when a comment arrives from the channel. Pass the comment's DOM element
  // when known so the indicator can skip already-visible comments and scroll
  // precisely; omit it to fall back to bottom-of-page semantics.
  notifyNewComment: (element?: Element | null) => void
  dismiss: () => void
  scrollToNew: () => void
  // Record the visit immediately. Call once after the initial show fetch resolves
  // so the page's last_visit_at (and thus "what's new") reflects the pre-arrival
  // visit before we bump it — the island owns this instead of an on-load form post.
  recordVisit: () => void
}

function isElementVisible(el: Element): boolean {
  const rect = el.getBoundingClientRect()
  return rect.top < window.innerHeight && rect.bottom > 0
}

// Tracks the "new comments while you're scrolled away" pill plus the debounced
// workspace-visit catch-up. The consumer's channel handler drives it explicitly
// via notifyNewComment() instead of observing the DOM.
export function useNewCommentsIndicator({
  workspaceId,
}: UseNewCommentsIndicatorOptions): UseNewCommentsIndicatorResult {
  const [hasNew, setHasNew] = useState(false)
  const [isAbove, setIsAbove] = useState(false)
  const firstNewElementRef = useRef<Element | null>(null)
  const visitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Self-no-ops while workspaceId is null (the post id hasn't loaded yet).
  const recordVisit = useWorkspaceVisitRecording(workspaceId)

  // While the pill is up, clear it once the tracked comment scrolls into view,
  // and otherwise keep the arrow direction in sync with where the comment sits
  // relative to the viewport (it may cross the fold as the user scrolls).
  useEffect(() => {
    if (!hasNew) return
    const onScroll = () => {
      const el = firstNewElementRef.current
      if (!el) return
      if (isElementVisible(el)) {
        setHasNew(false)
        firstNewElementRef.current = null
      } else {
        setIsAbove(el.getBoundingClientRect().bottom < 0)
      }
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => window.removeEventListener("scroll", onScroll)
  }, [hasNew])

  // Catch-up records a plain visit — no last_event_id (only the goal endpoint
  // carries one).
  const scheduleVisitCatchUp = useCallback(() => {
    if (visitTimerRef.current) clearTimeout(visitTimerRef.current)
    visitTimerRef.current = setTimeout(() => recordVisit(), VISIT_CATCH_UP_DEBOUNCE_MS)
  }, [recordVisit])

  useEffect(() => {
    return () => {
      if (visitTimerRef.current) clearTimeout(visitTimerRef.current)
    }
  }, [])

  const notifyNewComment = useCallback(
    (element?: Element | null) => {
      scheduleVisitCatchUp()
      if (element && isElementVisible(element)) return
      if (!firstNewElementRef.current && element) {
        firstNewElementRef.current = element
        setIsAbove(element.getBoundingClientRect().bottom < 0)
      }
      setHasNew(true)
    },
    [scheduleVisitCatchUp]
  )

  const dismiss = useCallback(() => setHasNew(false), [])

  const scrollToNew = useCallback(() => {
    const el = firstNewElementRef.current
    if (el?.isConnected) {
      el.scrollIntoView({ behavior: "smooth", block: "center" })
    } else {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" })
    }
    firstNewElementRef.current = null
    setHasNew(false)
  }, [])

  return { hasNew, isAbove, notifyNewComment, dismiss, scrollToNew, recordVisit }
}
