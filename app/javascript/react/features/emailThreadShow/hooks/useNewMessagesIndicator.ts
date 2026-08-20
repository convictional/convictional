import { useCallback, useEffect, useRef, useState } from "react"

const NEAR_BOTTOM_THRESHOLD_PX = 50

// Scroll to the page bottom after the browser has laid out the newly appended
// item. Callers append a comment (a React state update) and then ask to scroll;
// reading scrollHeight before that commit lays out lands at the pre-append
// bottom — the top of the new item — leaving the sticky composer over it.
// Two frames, not one: a single frame is enough in Chrome, but Safari can run
// the callback before layout and still read the stale height. Target the scroll
// maximum (scrollHeight - innerHeight), not scrollHeight, which Safari can
// extend past the true bottom (mirrors chat's scrollToBottomEdge).
function scrollToBottomNextFrame() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.scrollTo({ top: document.documentElement.scrollHeight - window.innerHeight, behavior: "smooth" })
    })
  })
}

interface UseNewMessagesIndicatorOptions {
  // Initial autoScroll state. Defaults to true; pass `false` when the thread
  // has unread content so the page doesn't immediately yank the user to the
  // bottom past the unread divider.
  initiallyNearBottom?: boolean
}

interface UseNewMessagesIndicatorResult {
  hasNewMessages: boolean
  // Whether the viewport is at the bottom of the page. The island uses this
  // to decide whether to auto-scroll on send.
  autoScroll: boolean
  // Call after appending a new timeline item. If the user is at the bottom
  // this auto-scrolls; otherwise it sets the indicator. Lets the consumer
  // own the decision of "is this a new item I should react to?" without the
  // hook having to diff arrays.
  notifyNewItem: () => void
  dismiss: () => void
  // Scroll to the bottom, re-enable autoScroll, and clear the indicator.
  scrollToNewMessage: () => void
}

// Tracks the auto-scroll / new-messages state for the email thread show
// island. Responds to scroll position via a scroll listener and notifies
// explicitly via notifyNewItem() when new messages arrive, allowing the
// consumer to control which items trigger the indicator.
export function useNewMessagesIndicator({
  initiallyNearBottom = true,
}: UseNewMessagesIndicatorOptions = {}): UseNewMessagesIndicatorResult {
  const [autoScroll, setAutoScroll] = useState(initiallyNearBottom)
  const [hasNewMessages, setHasNewMessages] = useState(false)

  // Latch the latest autoScroll into a ref so notifyNewItem can read the
  // most recent value across the event/commit boundary without being
  // re-created (and breaking callers that capture it).
  const autoScrollRef = useRef(autoScroll)
  useEffect(() => {
    autoScrollRef.current = autoScroll
  }, [autoScroll])

  useEffect(() => {
    let rafId = 0
    const onScroll = () => {
      if (rafId !== 0) return
      rafId = window.requestAnimationFrame(() => {
        rafId = 0
        // scrollHeight is a layout-forcing read; do it inside rAF, not in
        // the scroll event handler that fires hundreds of times during
        // momentum scroll.
        const near =
          document.documentElement.scrollHeight - window.scrollY - window.innerHeight < NEAR_BOTTOM_THRESHOLD_PX
        setAutoScroll(prev => {
          if (prev === near) return prev
          // Returning to bottom clears any "new messages" indicator.
          if (near) setHasNewMessages(false)
          return near
        })
      })
    }
    window.addEventListener("scroll", onScroll, { passive: true })
    return () => {
      window.removeEventListener("scroll", onScroll)
      if (rafId !== 0) window.cancelAnimationFrame(rafId)
    }
  }, [])

  const notifyNewItem = useCallback(() => {
    if (autoScrollRef.current) {
      scrollToBottomNextFrame()
    } else {
      setHasNewMessages(true)
    }
  }, [])

  const dismiss = useCallback(() => setHasNewMessages(false), [])

  const scrollToNewMessage = useCallback(() => {
    scrollToBottomNextFrame()
    setHasNewMessages(false)
  }, [])

  return { hasNewMessages, autoScroll, notifyNewItem, dismiss, scrollToNewMessage }
}
