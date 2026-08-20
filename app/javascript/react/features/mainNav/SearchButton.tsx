import { useEffect, useState } from "react"

import { Tooltip } from "~/react/ui/Tooltip"

// Trigger button only — the palette body lives in the React island mounted at
// `#react-command-palette` (see app/javascript/react/features/commandPalette/mount.tsx).
// Click dispatches the toggle event; opened/closed events from the palette
// drive the active style. Cmd+K is owned by the palette itself via
// useGlobalHotkey, so SearchButton stays out of the keystroke path.
export function SearchButton() {
  const [isOpen, setIsOpen] = useState(false)

  useEffect(() => {
    const onOpen = () => setIsOpen(true)
    const onClose = () => setIsOpen(false)
    window.addEventListener("command-palette:opened", onOpen)
    window.addEventListener("command-palette:closed", onClose)
    return () => {
      window.removeEventListener("command-palette:opened", onOpen)
      window.removeEventListener("command-palette:closed", onClose)
    }
  }, [])

  const handleClick = () => {
    window.dispatchEvent(new CustomEvent("command-palette:toggle"))
  }

  return (
    <Tooltip content="Search ⌘K" placement="bottom">
      <button
        type="button"
        onClick={handleClick}
        aria-label="Search"
        className={`flex items-center gap-2 pl-3 pr-2 py-1 rounded-full transition-all cursor-pointer ${
          isOpen
            ? "text-base-content bg-base-300 border border-base-400"
            : "text-base-content hover:text-primary border border-transparent"
        }`}
      >
        <span className="material-symbols-outlined text-sm">search</span>
      </button>
    </Tooltip>
  )
}
