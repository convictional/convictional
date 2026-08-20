import { useCallback, useRef } from "react"

import { hashTargetsComment } from "~/react/shared/hooks/useScrollToHashComment"

// Returns a callback ref that scrolls the initial target message to the top on
// commit — the first unread message, or the newest message when the thread is
// fully read. Firing on the node's DOM commit (no wall-clock timer guessing
// layout readiness — the old approach's flake source) means top-aligning works
// regardless of email-iframe height, so no scrollHeight read is needed. Attach
// the returned ref to the scroll target node.
//
// scrollKey tags the thread + read-state: the once-per-key guard keeps this a
// strictly initial scroll, so realtime arrivals on the same key never retrigger it.
export function useInitialThreadScroll(scrollKey: string | null): (node: HTMLElement | null) => void {
  const scrolledForKey = useRef<string | null>(null)
  return useCallback(
    (node: HTMLElement | null) => {
      if (!node || !scrollKey) return
      if (scrolledForKey.current === scrollKey) return // initial scroll only; live arrivals don't retrigger
      if (hashTargetsComment()) return // yield to useScrollToHashComment
      scrolledForKey.current = scrollKey
      node.scrollIntoView({ block: "start", behavior: "instant" })
    },
    [scrollKey]
  )
}
