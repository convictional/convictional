import { eventToHotkeyString, normalizeHotkey } from "@github/hotkey"
import { useEffect } from "react"

const SEARCH_HOTKEY = normalizeHotkey("Mod+k")

// Capture-phase, window-level Cmd+K listener.
//
// Window level (not data-hotkey) because @github/hotkey ignores events from
// editable targets, which would block the shortcut for users typing in the
// chat composer or any input. Capture phase because ProseMirror plugins in
// the chat/doc editors install their own keydown handlers that may
// stopPropagation — listening in the capture phase guarantees we see the
// event before any descendant can swallow it.
export function useGlobalHotkey(onHotkey: () => void): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (eventToHotkeyString(event) === SEARCH_HOTKEY) {
        event.preventDefault()
        onHotkey()
      }
    }
    window.addEventListener("keydown", handler, { capture: true })
    return () => window.removeEventListener("keydown", handler, { capture: true })
  }, [onHotkey])
}
