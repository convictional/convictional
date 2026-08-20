import { useEffect } from "react"

import { lockScroll, unlockScroll } from "~/shared/scrollLock"

// Thin React binding over the shared scroll lock (~/shared/scrollLock): acquire
// on mount, release on unmount. The ref counting and DOM work live there so
// non-React callers can share the same lock state.
export function useScrollLock(enabled: boolean = true) {
  useEffect(() => {
    if (!enabled || typeof document === "undefined") return
    lockScroll()
    return unlockScroll
  }, [enabled])
}
