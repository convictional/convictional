import { useCallback, useEffect, useRef, useState } from "react"

import { useScrollLock } from "~/react/ui/hooks/useScrollLock"

const TRANSITION_MS = 150

export function useZenMode() {
  const [active, setActive] = useState(false)
  const [exiting, setExiting] = useState(false)
  const exitTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const zenMode = active || exiting

  const exit = useCallback(() => {
    setActive(false)
    setExiting(true)
    if (exitTimer.current) clearTimeout(exitTimer.current)
    exitTimer.current = setTimeout(() => setExiting(false), TRANSITION_MS)
  }, [])

  const toggleZenMode = useCallback(() => {
    if (active) {
      exit()
    } else {
      if (exitTimer.current) clearTimeout(exitTimer.current)
      setExiting(false)
      setActive(true)
    }
  }, [active, exit])

  useScrollLock(zenMode)

  useEffect(() => {
    if (!active) return
    // Capture phase so we fire before ProseMirror's Escape handler (which blurs the editor)
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") exit()
    }
    window.addEventListener("keydown", handleKeyDown, true)
    return () => window.removeEventListener("keydown", handleKeyDown, true)
  }, [active, exit])

  useEffect(() => {
    return () => {
      if (exitTimer.current) clearTimeout(exitTimer.current)
    }
  }, [])

  return { zenMode, exiting, toggleZenMode }
}
