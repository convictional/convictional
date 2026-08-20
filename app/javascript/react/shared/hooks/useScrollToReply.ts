import { useCallback, useEffect, useRef, useState } from "react"

import type { MessageWindowResponse } from "~/react/shared/types"
import { showFlash } from "~/shared/flash"

function waitForRender(): Promise<void> {
  return new Promise(resolve => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
  })
}

// Delay to let layout settle after transitions (e.g. auto-hiding nav in ChatShow)
function waitForSettle(): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, 250))
}

/**
 * Returns a handler for clicking a reply preview, plus a ref that MessageList
 * checks to suppress normal pagination while the scroll-to-reply jump is in
 * flight.
 *
 * If the target message is already in the DOM it scrolls immediately. Otherwise
 * it calls jumpToMessage() to load a bounded window AROUND the target (replacing
 * the list, so a quoted message at any depth is reachable), then scrolls to it.
 */
export function useScrollToReply(jumpToMessage: (messageId: string) => Promise<MessageWindowResponse | null>) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const highlightedRef = useRef<HTMLElement | null>(null)
  const activeRef = useRef(false)
  const [scrollingToId, setScrollingToId] = useState<string | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const scrollToReply = useCallback(
    async (targetId: string) => {
      if (activeRef.current) return

      const elementId = `chat-message-${targetId}`
      let el = document.getElementById(elementId)
      let loadedWindow = false

      if (!el) {
        activeRef.current = true
        setScrollingToId(targetId)
        const result = await jumpToMessage(targetId)
        if (!result) {
          activeRef.current = false
          setScrollingToId(null)
          showFlash("Couldn't find the original message.")
          return
        }
        // One frame for the replaced window to commit before the element exists.
        await waitForRender()
        el = document.getElementById(elementId)
        loadedWindow = true
      }

      if (!el) {
        activeRef.current = false
        setScrollingToId(null)
        showFlash("Couldn't find the original message.")
        return
      }

      if (loadedWindow) {
        // Initial scroll to get close — this may trigger the auto-hiding nav
        // to show/hide, which shifts content and adjusts the scroll position.
        el.scrollIntoView({ behavior: "instant", block: "center" })
        // Wait for nav transitions and browser layout adjustments to settle,
        // then re-scroll to the correct position.
        await waitForSettle()
        el.scrollIntoView({ behavior: "instant", block: "center" })
      } else {
        el.scrollIntoView({ behavior: "smooth", block: "center" })
      }

      // Let the scroll event from scrollIntoView propagate before lifting
      // pagination suppression, otherwise the scroll handler may fire an
      // unwanted loadMore while the container is near the top.
      await waitForRender()
      activeRef.current = false
      setScrollingToId(null)

      if (timerRef.current) {
        clearTimeout(timerRef.current)
        highlightedRef.current?.classList.remove("chat-message-highlight")
      }
      el.classList.add("chat-message-highlight")
      highlightedRef.current = el
      timerRef.current = setTimeout(() => {
        highlightedRef.current?.classList.remove("chat-message-highlight")
        highlightedRef.current = null
        timerRef.current = null
      }, 1500)
    },
    [jumpToMessage]
  )

  return { scrollToReply, scrollingToReplyRef: activeRef, scrollingToId }
}
