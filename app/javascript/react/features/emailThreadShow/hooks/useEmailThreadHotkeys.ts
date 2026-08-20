import { useCallback, useEffect, useState } from "react"

interface UseEmailThreadHotkeysResult {
  helpOpen: boolean
  openHelp: () => void
  closeHelp: () => void
}

// Most thread hotkeys (r, a, f, e, b, u) are wired via `data-hotkey`
// attributes that useHotkeyInstall picks up. Shift+? is the exception — it
// opens the help dialog, which has no obvious target element to attach a
// data-hotkey to — so this hook listens for it directly.
export function useEmailThreadHotkeys(): UseEmailThreadHotkeysResult {
  const [helpOpen, setHelpOpen] = useState(false)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return
      // Ignore keystrokes inside editable surfaces — the global hotkey
      // library uses the same gate.
      const target = event.target as HTMLElement | null
      if (target && (target.isContentEditable || target.matches("input, textarea, select"))) return
      if (event.key === "?" && event.shiftKey) {
        event.preventDefault()
        setHelpOpen(prev => !prev)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  const openHelp = useCallback(() => setHelpOpen(true), [])
  const closeHelp = useCallback(() => setHelpOpen(false), [])

  return { helpOpen, openHelp, closeHelp }
}
